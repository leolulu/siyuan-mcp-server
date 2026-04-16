import base64
import difflib
import json
import os
import re
from typing import Any, Dict, List, Optional, Tuple

import requests
from mcp.server.fastmcp import FastMCP

from .tools import is_siyuan_timestamp, mask_sensitive_data, parse_and_mask_kramdown


def _post_to_siyuan_api(
    endpoint: str, json_data: Optional[Dict[str, Any]] = None
) -> Any:
    """发送 POST 请求到思源笔记 API

    Args:
        endpoint: API 端点，例如 '/api/query/sql'
        json_data: 要发送的 JSON 数据

    Returns:
        API 响应的数据部分

    Raises:
        ValueError: 如果 SIYUAN_API_TOKEN 环境变量未设置
        ConnectionError: 如果无法连接到思源笔记 API
        Exception: 如果 API 返回错误
    """
    # 验证环境变量中的 Token
    api_token = os.getenv("SIYUAN_API_TOKEN")
    if not api_token:
        raise ValueError("SIYUAN_API_TOKEN environment variable not set.")

    # 获取 API 基础 URL
    base_url = os.getenv("SIYUAN_API_URL", "http://127.0.0.1:6806").rstrip("/")

    # 配置请求头
    headers = {
        "Authorization": f"Token {api_token}",
        "Content-Type": "application/json",
    }

    # 发送请求
    url = f"{base_url}{endpoint}"
    try:
        response = requests.post(url, json=json_data, headers=headers)
        response.raise_for_status()
        api_response = response.json()
        if api_response.get("code") != 0:
            raise Exception(f"Siyuan API Error: {api_response.get('msg')}")
        return api_response.get("data")
    except requests.exceptions.RequestException as e:
        raise ConnectionError(f"Failed to connect to Siyuan API: {e}") from e


def _push_notification(endpoint: str, msg: str, timeout: int = 20000) -> Dict[str, Any]:
    """推送前台通知消息。"""
    if not isinstance(msg, str) or not msg.strip():
        raise ValueError("msg must be a non-empty string")
    if isinstance(timeout, bool) or not isinstance(timeout, int) or timeout <= 0:
        raise ValueError("timeout must be a positive integer in milliseconds")

    result = _post_to_siyuan_api(endpoint, {"msg": msg, "timeout": timeout})
    if not isinstance(result, dict):
        raise TypeError(
            f"Expected a dict from notification API, but got {type(result)}"
        )
    return result


def _push_message(title: str, msg: str, timeout: int = 20000) -> Dict[str, Any]:
    """内部统一的成功通知入口（供写操作 tool 调用）。"""
    title_text = title.strip() if isinstance(title, str) else ""
    combined = f"{title_text}：{msg}" if title_text else msg
    return _push_notification("/api/notification/pushMsg", combined, timeout)


def _push_error_message(title: str, msg: str, timeout: int = 7000) -> Dict[str, Any]:
    """内部统一的失败通知入口（供写操作 tool 调用）。"""
    title_text = title.strip() if isinstance(title, str) else ""
    combined = f"{title_text}：{msg}" if title_text else msg
    return _push_notification("/api/notification/pushErrMsg", combined, timeout)


def _best_effort_push_notification(
    endpoint: str, msg: str, timeout: int = 7000
) -> Optional[str]:
    """尽力推送通知，失败时返回错误信息而不是抛异常。"""
    try:
        _push_notification(endpoint, msg, timeout)
        return None
    except Exception as e:
        return str(e)


def _shorten(text: str, max_len: int = 120) -> str:
    normalized = text.replace("\n", "\\n")
    if len(normalized) <= max_len:
        return normalized
    return normalized[:max_len] + "..."


_ACTION_LABELS = {
    "create_document": "创建文档",
    "update_block": "更新内容",
    "delete_block": "删除内容",
    "insert_block": "插入内容",
    "prepend_block": "前置插入子块",
    "append_block": "后置插入子块",
    "move_block": "移动内容",
}

_STAGE_LABELS = {
    "接收请求": "已收到请求",
    "参数校验通过": "参数检查通过",
    "调用接口": "正在和思源交互",
    "创建完成": "创建完成",
    "更新完成": "更新完成",
    "删除完成": "删除完成",
    "插入完成": "插入完成",
    "移动完成": "移动完成",
    "处理请求": "处理请求",
}

_DETAIL_KEY_LABELS = {
    "notebook_id": "笔记本",
    "path": "路径",
    "markdown_chars": "文档长度",
    "document_id": "文档 ID",
    "block_id": "块 ID",
    "parent_id": "父块 ID",
    "previous_id": "前一个块 ID",
    "next_id": "后一个块 ID",
    "data_type": "内容格式",
    "data_chars": "内容长度",
    "data_preview": "内容预览",
    "operations": "变更数量",
    "anchors": "定位信息",
    "endpoint": "接口",
    "allow_heading_only_move": "允许仅移动标题",
    "moved_blocks": "移动块数",
}


def _humanize_action(action: str) -> str:
    return _ACTION_LABELS.get(action, action.replace("_", " ").strip() or "当前操作")


def _humanize_stage(stage: str) -> str:
    text = stage.strip()
    match = re.match(r"^步骤(\d+)/(\d+)\s*(.*)$", text)
    if not match:
        return _STAGE_LABELS.get(text, text or "处理中")

    current, total, raw_stage = match.groups()
    stage_name = _STAGE_LABELS.get(raw_stage.strip(), raw_stage.strip() or "处理中")
    return f"第 {current}/{total} 步，{stage_name}"


def _humanize_detail(detail: str) -> str:
    text = detail.strip()
    if not text:
        return ""

    items: List[str] = [part.strip() for part in text.split(",") if part.strip()]
    normalized: List[str] = []
    for item in items:
        if "=" not in item:
            normalized.append(item)
            continue

        key, value = item.split("=", 1)
        label = _DETAIL_KEY_LABELS.get(key.strip(), key.strip().replace("_", " "))
        shown_value = value.strip() or "未提供"
        if shown_value == "-":
            shown_value = "未提供"
        normalized.append(f"{label}：{shown_value}")

    return _shorten("；".join(normalized), 220)


def _humanize_error(error: Exception) -> str:
    if isinstance(error, ValueError):
        prefix = "输入内容不符合要求"
    elif isinstance(error, ConnectionError):
        prefix = "暂时无法连接思源"
    elif isinstance(error, TypeError):
        prefix = "返回数据格式异常"
    else:
        prefix = "处理过程中出现异常"

    raw = str(error).strip()
    if not raw:
        return prefix
    return f"{prefix}（{_shorten(raw, 120)}）"


def _validate_block_data_type(data_type: str) -> None:
    if data_type not in {"markdown", "dom"}:
        raise ValueError("data_type must be 'markdown' or 'dom'")


def _sql_escape(value: str) -> str:
    return value.replace("'", "''")


def _get_block_metadata(block_id: str) -> Optional[Dict[str, Any]]:
    sanitized_id = _sql_escape(block_id)
    query = f"SELECT id, root_id, parent_id, type, subtype, sort, created FROM blocks WHERE id = '{sanitized_id}' LIMIT 1"
    result = _post_to_siyuan_api("/api/query/sql", {"stmt": query})
    if not isinstance(result, list) or not result:
        return None
    first = result[0]
    if not isinstance(first, dict):
        return None
    return first


def _get_block_content_preview(block_id: str, max_len: int = 30) -> str:
    """获取块的内容预览（用于语义化通知）。"""
    try:
        content_dict = get_block_content(block_id)
        content = content_dict.get("kramdown", "")
        text = content.replace("\n", " ").strip().lstrip("#").strip()
        return _shorten(text, max_len) if text else '空白块'
    except Exception:
        return '未知块'



def _get_root_block_rows(root_id: str) -> List[Dict[str, Any]]:
    sanitized_root_id = _sql_escape(root_id)
    query = (
        "SELECT id, parent_id, type, subtype, sort, created FROM blocks "
        f"WHERE root_id = '{sanitized_root_id}' ORDER BY sort ASC, created ASC, id ASC"
    )
    result = _post_to_siyuan_api("/api/query/sql", {"stmt": query})
    if not isinstance(result, list):
        raise TypeError(f"Expected a list from SQL query, but got {type(result)}")

    rows: List[Dict[str, Any]] = []
    for row in result:
        if not isinstance(row, dict):
            continue
        rows.append(row)
    return rows


def _get_direct_child_rows(parent_id: str) -> List[Dict[str, Any]]:
    sanitized_parent_id = _sql_escape(parent_id)
    query = (
        "SELECT id, parent_id, type, subtype, sort, created FROM blocks "
        + f"WHERE parent_id = '{sanitized_parent_id}' ORDER BY sort ASC, created ASC, id ASC"
    )
    result = _post_to_siyuan_api("/api/query/sql", {"stmt": query})
    if not isinstance(result, list):
        raise TypeError(f"Expected a list from SQL query, but got {type(result)}")

    rows: List[Dict[str, Any]] = []
    for row in result:
        if not isinstance(row, dict):
            continue
        rows.append(row)
    return rows


def _get_child_blocks_rows(block_id: str) -> List[Dict[str, Any]]:
    result = _post_to_siyuan_api("/api/block/getChildBlocks", {"id": block_id})
    if not isinstance(result, list):
        raise TypeError(f"Expected a list from getChildBlocks, but got {type(result)}")

    rows: List[Dict[str, Any]] = []
    for row in result:
        if isinstance(row, dict):
            rows.append(row)
    return rows


def _build_children_index(rows: List[Dict[str, Any]]) -> Dict[str, List[str]]:
    children_index: Dict[str, List[str]] = {}
    for row in rows:
        block_id = row.get("id")
        if not isinstance(block_id, str) or not block_id:
            continue

        raw_parent_id = row.get("parent_id")
        parent_id = raw_parent_id if isinstance(raw_parent_id, str) else ""
        if parent_id not in children_index:
            children_index[parent_id] = []
        children_index[parent_id].append(block_id)
    return children_index


def _collect_preorder_ids(
    root_id: str,
    children_index: Dict[str, List[str]],
    row_order_ids: List[str],
) -> List[str]:
    ordered: List[str] = []
    visited = set()
    stack: List[str] = [root_id]

    while stack:
        current = stack.pop()
        if current in visited:
            continue
        visited.add(current)
        ordered.append(current)

        children = children_index.get(current, [])
        for child in reversed(children):
            stack.append(child)

    for block_id in row_order_ids:
        if block_id in visited:
            continue
        visited.add(block_id)
        ordered.append(block_id)

    return ordered


def _parse_heading_level(subtype: Any) -> Optional[int]:
    if not isinstance(subtype, str):
        return None
    text = subtype.strip().lower()
    if not text.startswith("h"):
        return None
    raw = text[1:]
    if not raw.isdigit():
        return None
    level = int(raw)
    if level < 1 or level > 6:
        return None
    return level


def _collect_heading_section_ids(block_id: str) -> List[str]:
    metadata = _get_block_metadata(block_id)
    if not metadata:
        raise ValueError(f"block_id not found: {block_id}")

    if metadata.get("type") != "h":
        return [block_id]

    level = _parse_heading_level(metadata.get("subtype"))
    if level is None:
        level = 6

    raw_parent_id = metadata.get("parent_id")
    parent_id = raw_parent_id if isinstance(raw_parent_id, str) else ""
    if not parent_id:
        return [block_id]

    rows = _get_child_blocks_rows(parent_id)
    child_ids: List[str] = []
    type_by_id: Dict[str, str] = {}
    level_by_id: Dict[str, Optional[int]] = {}
    for row in rows:
        row_id = row.get("id")
        if not isinstance(row_id, str) or not row_id:
            continue
        child_ids.append(row_id)
        row_type = row.get("type")
        type_by_id[row_id] = row_type if isinstance(row_type, str) else ""
        subtype_value = row.get("subType")
        if subtype_value is None:
            subtype_value = row.get("subtype")
        level_by_id[row_id] = _parse_heading_level(subtype_value)

    try:
        start = child_ids.index(block_id)
    except ValueError:
        return [block_id]

    section_ids: List[str] = []
    for next_id in child_ids[start:]:
        if section_ids and type_by_id.get(next_id) == "h":
            next_level = level_by_id.get(next_id)
            if next_level is not None and next_level <= level:
                break
        section_ids.append(next_id)

    return section_ids or [block_id]


def _move_section_group_after(
    group_top_level_ids: List[str],
    previous_id: Optional[str],
    parent_id: str,
) -> Tuple[List[str], List[Dict[str, Any]]]:
    if not group_top_level_ids:
        raise ValueError("group_top_level_ids cannot be empty")
    if not isinstance(parent_id, str) or not parent_id.strip():
        raise ValueError("parent_id must be a non-empty string for section move")
    if previous_id and previous_id in group_top_level_ids:
        raise ValueError("previous_id cannot point to a block inside the moving group")

    operations: List[Dict[str, Any]] = []
    moved_ids: List[str] = []

    # Chain the anchor to keep the moved group contiguous.
    anchor_id: Optional[str] = previous_id

    failures: Dict[str, str] = {}
    for idx, current_id in enumerate(group_top_level_ids):
        try:
            if idx == 0:
                current_ops = _move_block_once(
                    current_id, previous_id=anchor_id, parent_id=parent_id
                )
            else:
                current_ops = _move_block_once(current_id, previous_id=anchor_id)
            moved_ids.append(current_id)
            operations.extend(current_ops)
            anchor_id = current_id
            failures.pop(current_id, None)
        except Exception as e:  # noqa: PERF203
            failures[current_id] = str(e)

    if failures:
        failed_ids = ", ".join(failures.keys())
        failure_details = "; ".join(
            f"{block_id}={reason}" for block_id, reason in failures.items()
        )
        raise RuntimeError(
            "Partial section move detected; "
            + f"failed block IDs: {failed_ids}; "
            + f"details: {failure_details}"
        )

    return moved_ids, operations


def _collect_subtree_ids(
    block_id: str, children_index: Dict[str, List[str]]
) -> List[str]:
    ordered: List[str] = []
    stack: List[str] = [block_id]
    visited = set()

    while stack:
        current = stack.pop()
        if current in visited:
            continue
        visited.add(current)
        ordered.append(current)

        children = children_index.get(current, [])
        for child in reversed(children):
            stack.append(child)

    return ordered


def _move_block_once(
    block_id: str, previous_id: Optional[str] = None, parent_id: Optional[str] = None
) -> List[Dict[str, Any]]:
    payload: Dict[str, str] = {"id": block_id}
    if previous_id:
        payload["previousID"] = previous_id
    if parent_id:
        payload["parentID"] = parent_id

    result = _post_to_siyuan_api("/api/block/moveBlock", payload)
    if result is None:
        return []
    if not isinstance(result, list):
        raise TypeError(
            f"Expected a list or null from moveBlock, but got {type(result)}"
        )
    return result


def _move_block_group(
    block_id: str, previous_id: Optional[str], parent_id: Optional[str]
) -> Tuple[List[str], List[Dict[str, Any]]]:
    metadata = _get_block_metadata(block_id)
    if not metadata:
        raise ValueError(f"block_id not found: {block_id}")

    root_id_raw = metadata.get("root_id")
    root_id = root_id_raw if isinstance(root_id_raw, str) else ""
    if not root_id:
        if previous_id == block_id:
            raise ValueError("previous_id cannot be the same as block_id")
        if parent_id == block_id:
            raise ValueError("parent_id cannot be the same as block_id")
        return [block_id], _move_block_once(block_id, previous_id, parent_id)

    rows = _get_root_block_rows(root_id)
    children_index = _build_children_index(rows)
    subtree_ids = _collect_subtree_ids(block_id, children_index)
    subtree_set = set(subtree_ids)

    if previous_id and previous_id in subtree_set:
        raise ValueError(
            "previous_id cannot point to a block inside the moving subtree"
        )
    if parent_id and parent_id in subtree_set:
        raise ValueError("parent_id cannot point to a block inside the moving subtree")

    operations = _move_block_once(block_id, previous_id, parent_id)
    return subtree_ids, operations


def _get_direct_children_ids(parent_id: str) -> List[str]:
    sanitized_parent_id = _sql_escape(parent_id)
    query = (
        "SELECT id FROM blocks "
        f"WHERE parent_id = '{sanitized_parent_id}' "
        "ORDER BY sort ASC, created ASC, id ASC"
    )
    result = _post_to_siyuan_api("/api/query/sql", {"stmt": query})
    if not isinstance(result, list):
        raise TypeError(f"Expected a list from SQL query, but got {type(result)}")

    ids: List[str] = []
    for row in result:
        if not isinstance(row, dict):
            continue
        row_id = row.get("id")
        if isinstance(row_id, str) and row_id:
            ids.append(row_id)
    return ids


def _restore_children(parent_id: str, child_ids: List[str]) -> List[Dict[str, Any]]:
    operations: List[Dict[str, Any]] = []
    previous_child_id: Optional[str] = None

    for child_id in child_ids:
        if previous_child_id:
            operations.extend(
                _move_block_once(
                    child_id, previous_id=previous_child_id, parent_id=parent_id
                )
            )
        else:
            operations.extend(_move_block_once(child_id, parent_id=parent_id))
        previous_child_id = child_id

    return operations


# 创建 MCP 服务器实例
mcp = FastMCP("siyuan-mcp-server")


@mcp.tool()
def find_notebooks(name: Optional[str] = None, limit: int = 10) -> List[Dict[str, Any]]:
    """查找并列出思源笔记中的笔记本。

    适用场景:
        - 快速获取所有笔记本 ID 以便后续写入/查询工具使用。
        - 通过名称关键字做轻量筛选。

    使用方法:
        - name: 可选，大小写不敏感的包含匹配。
        - limit: 返回数量上限，默认 10。

    注意事项:
        - 返回结果为笔记本原始信息（含 id/name/icon/closed 等字段）。
        - 若需要精确匹配名称，请在调用方自行做二次过滤。

    Args:
        name (Optional[str]): 用于模糊搜索笔记本的名称。如果省略，则列出所有笔记本。
        limit (int): 返回结果的最大数量，默认为 10。

    Returns:
        list: 包含笔记本信息的字典列表，每个字典包含 'name' 和 'id'。
    """
    result = _post_to_siyuan_api("/api/notebook/lsNotebooks")
    if not isinstance(result, dict) or "notebooks" not in result:
        raise TypeError(f"Expected a dict with 'notebooks' key, but got {type(result)}")
    notebooks = result["notebooks"]

    # 如果指定了名称，则进行过滤
    if name:
        notebooks = [
            nb for nb in notebooks if name.lower() in nb.get("name", "").lower()
        ]

    # 限制返回结果数量
    return notebooks[:limit]


@mcp.tool()
def find_documents(
    notebook_id: Optional[str] = None,
    title: Optional[str] = None,
    created_after: Optional[str] = None,
    updated_after: Optional[str] = None,
    limit: int = 10,
) -> List[Dict[str, Any]]:
    """在指定的笔记本中查找文档，支持多种过滤条件。

    适用场景:
        - 按笔记本、标题、创建/更新时间筛选文档块（type='d'）。

    使用方法:
        - notebook_id: 指定笔记本范围。
        - title: 对文档名称字段做 LIKE 模糊匹配。
        - created_after / updated_after: 传入 YYYYMMDDHHMMSS。

    注意事项:
        - 本工具按 blocks.name 过滤标题，不按 hpath 过滤。
        - 若需要更复杂条件（例如按 hpath 前缀），请使用 execute_sql。

    Args:
        notebook_id (Optional[str]): 在哪个笔记本中查找。如果省略，则在所有打开的笔记本中查找。
        title (Optional[str]): 根据文档标题进行模糊匹配。
        created_after (Optional[str]): 查找在此日期之后创建的文档，格式为 'YYYYMMDDHHMMSS'。
        updated_after (Optional[str]): 查找在此日期之后更新的文档，格式为 'YYYYMMDDHHMMSS'。
        limit (int): 返回结果的最大数量，默认为 10。

    Returns:
        list: 包含文档信息的字典列表，每个字典包含 'name', 'id', 和 'hpath'。
    """
    query = "SELECT name, id, hpath FROM blocks WHERE type = 'd'"
    conditions = []
    if notebook_id:
        sanitized_id = notebook_id.replace("'", "''")
        conditions.append(f"box = '{sanitized_id}'")
    if title:
        sanitized_title = title.replace("'", "''")
        conditions.append(f"name LIKE '%{sanitized_title}%'")
    if created_after:
        sanitized_date = created_after.replace("'", "''")
        conditions.append(f"created > '{sanitized_date}'")
    if updated_after:
        sanitized_date = updated_after.replace("'", "''")
        conditions.append(f"updated > '{sanitized_date}'")
    if conditions:
        query += " AND " + " AND ".join(conditions)
    query += f" LIMIT {limit}"

    # 验证 SQL 只包含 SELECT 语句
    if not query.strip().upper().startswith("SELECT"):
        raise ValueError("Only SELECT statements are allowed for security reasons.")

    result = _post_to_siyuan_api("/api/query/sql", {"stmt": query})
    if not isinstance(result, list):
        raise TypeError(f"Expected a list from SQL query, but got {type(result)}")
    return result


@mcp.tool()
def search_blocks(
    query: str,
    parent_id: Optional[str] = None,
    block_type: Optional[str] = None,
    created_after: Optional[str] = None,
    updated_after: Optional[str] = None,
    limit: int = 20,
) -> List[Dict[str, Any]]:
    """根据关键词、类型等多种条件在思源笔记中搜索内容块。

    这是最核心和最灵活的查询工具。

    适用场景:
        - 全局关键词检索。
        - 按块类型和时间窗口缩小范围。

    使用方法:
        - query: 使用 SQL LIKE 语义匹配 content。
        - parent_id: 按直接父块 ID 过滤。
        - block_type: 例如 p/h/l。

    注意事项:
        - parent_id 仅匹配直接子块，不会递归后代。
        - 返回 content 会做敏感信息打码处理。

    Args:
        query (str): 在块内容中搜索的关键词。
        parent_id (Optional[str]): 在哪个文档或父块下进行搜索。如果省略，则全局搜索。
        block_type (Optional[str]): 限制块的类型，例如 'p' (段落), 'h' (标题), 'l' (列表)。
        created_after (Optional[str]): 查找在此日期之后创建的块，格式为 'YYYYMMDDHHMMSS'。
        updated_after (Optional[str]): 查找在此日期之后更新的块，格式为 'YYYYMMDDHHMMSS'。
        limit (int): 返回结果的最大数量，默认为 20。

    Returns:
        list: 包含块信息的字典列表。
    """
    sql_query = (
        "SELECT id, content, type, subtype, hpath FROM blocks WHERE content LIKE ?"
    )
    params = [f"%{query}%"]
    if parent_id:
        sql_query += " AND parent_id = ?"
        params.append(parent_id)
    if block_type:
        sql_query += " AND type = ?"
        params.append(block_type)
    if created_after:
        sql_query += " AND created > ?"
        params.append(created_after)
    if updated_after:
        sql_query += " AND updated > ?"
        params.append(updated_after)
    sql_query += f" LIMIT {limit}"

    # 替换参数占位符为实际值
    for param in params:
        sanitized_param = str(param).replace("'", "''")
        sql_query = sql_query.replace("?", f"'{sanitized_param}'", 1)

    # 验证 SQL 只包含 SELECT 语句
    if not sql_query.strip().upper().startswith("SELECT"):
        raise ValueError("Only SELECT statements are allowed for security reasons.")

    results = _post_to_siyuan_api("/api/query/sql", {"stmt": sql_query})
    if not isinstance(results, list):
        raise TypeError(f"Expected a list from SQL query, but got {type(results)}")

    # 对搜索结果中的内容进行打码处理
    for result in results:
        if isinstance(result, dict):
            if "content" in result:
                result["content"] = mask_sensitive_data(result["content"])

    return results


@mcp.tool()
def get_block_content(block_id: str) -> Dict[str, Any]:
    """获取指定块的完整 Markdown 内容。

    适用场景:
        - 读取单个块的 kramdown 原文并用于审阅或后续处理。

    注意事项:
        - 返回的 kramdown 会进行敏感信息打码。
        - 思源属性标记中的块 ID / 时间戳会被保留，便于定位。

    Args:
        block_id (str): 块的 ID

    Returns:
        Dict[str, Any]: 包含块内容的字典
    """
    result = _post_to_siyuan_api("/api/block/getBlockKramdown", {"id": block_id})
    if not isinstance(result, dict):
        raise TypeError(f"Expected a dict for block content, but got {type(result)}")
    # 对 kramdown 字段进行智能敏感信息打码，保留思源属性中的ID
    if "kramdown" in result and isinstance(result["kramdown"], str):
        result["kramdown"] = parse_and_mask_kramdown(result["kramdown"])
    return result


@mcp.tool()
def get_blocks_content(block_ids: List[str]) -> List[Dict[str, Any]]:
    """批量获取多个块的完整内容。

    适用场景:
        - 一次性拉取多个块内容，减少多次调用开销。

    注意事项:
        - 单个块失败不会中断整体，失败项会返回 error 字段。
        - 返回的 kramdown 与 get_block_content 一样会做敏感信息打码。

    Args:
        block_ids (List[str]): 块 ID 列表

    Returns:
        List[Dict[str, Any]]: 包含每个块内容的字典列表
    """
    results = []
    for block_id in block_ids:
        try:
            result = _post_to_siyuan_api(
                "/api/block/getBlockKramdown", {"id": block_id}
            )
            if isinstance(result, dict):
                # 对 kramdown 字段进行智能敏感信息打码，保留思源属性中的ID
                if "kramdown" in result and isinstance(result["kramdown"], str):
                    result["kramdown"] = parse_and_mask_kramdown(result["kramdown"])
                results.append(result)
            else:
                results.append(
                    {"id": block_id, "error": f"Unexpected type: {type(result)}"}
                )
        except Exception as e:
            results.append({"id": block_id, "error": str(e)})
    return results


@mcp.tool()
def execute_sql(query: str) -> List[Dict[str, Any]]:
    """直接对数据库执行只读的 SELECT 查询。

    适用场景:
        - 需要跨字段、跨表的高级筛选能力。
        - 内置查询工具无法覆盖的复杂检索。

    使用方法:
        - 仅支持 SELECT 语句。
        - 建议显式 LIMIT，避免一次返回过多数据。

    注意事项:
        - 返回的字符串字段会进行敏感信息打码。
        - 如需精确审计原始敏感字段值，不适合使用该工具。

    Args:
        query (str): SQL SELECT 查询语句

    Returns:
        List[Dict[str, Any]]: 查询结果列表

    Raises:
        ValueError: 如果查询不是 SELECT 语句
    """
    if not query.strip().upper().startswith("SELECT"):
        raise ValueError("Only SELECT statements are allowed for security reasons.")

    result = _post_to_siyuan_api("/api/query/sql", {"stmt": query})
    if not isinstance(result, list):
        raise TypeError(f"Expected a list from SQL query, but got {type(result)}")

    # 对查询结果进行打码处理
    for row in result:
        if isinstance(row, dict):
            for key, value in row.items():
                if isinstance(value, str):
                    row[key] = mask_sensitive_data(value)

    return result


@mcp.tool()
def push_message(msg: str, timeout: int = 7000) -> Dict[str, Any]:
    """推送前台消息。

    适用场景:
        - 在写入流程中向前台反馈进度或结果。

    注意事项:
        - msg 必须是非空字符串。
        - timeout 必须是正整数毫秒值。

    Args:
        msg: 消息内容。
        timeout: 消息显示时长（毫秒），默认 7000。

    Returns:
        Dict[str, Any]: 包含消息 id 的字典。
    """
    return _push_notification("/api/notification/pushMsg", msg, timeout)


@mcp.tool()
def push_error_message(msg: str, timeout: int = 7000) -> Dict[str, Any]:
    """推送前台错误消息。

    适用场景:
        - 在参数校验或接口调用失败时向前台反馈错误。

    注意事项:
        - msg 必须是非空字符串。
        - timeout 必须是正整数毫秒值。

    Args:
        msg: 错误消息内容。
        timeout: 消息显示时长（毫秒），默认 7000。

    Returns:
        Dict[str, Any]: 包含消息 id 的字典。
    """
    return _push_notification("/api/notification/pushErrMsg", msg, timeout)


@mcp.tool()
def create_document(notebook_id: str, path: str, markdown: str) -> str:
    """通过 Markdown 创建文档。

    适用场景:
        - 根据固定路径批量创建结构化文档。
        - 快速写入一篇完整 Markdown 文档。

    使用方法:
        - notebook_id: 目标笔记本 ID。
        - path: 以 / 开头的人类可读路径。
        - markdown: 文档 Markdown 正文。

    注意事项:
        - path 必须以 / 开头。
        - 思源 API 对相同 path 重复创建不会覆盖已有文档。
    """
    # 提取文档标题和路径
    title = markdown.split('\n')[0].lstrip('#').strip() if markdown.strip() else '未命名'
    doc_path = path.lstrip('/')

    try:
        if not notebook_id.strip():
            raise ValueError("notebook_id must be a non-empty string")
        if not path.startswith("/"):
            raise ValueError("path must start with '/'")

        result = _post_to_siyuan_api(
            "/api/filetree/createDocWithMd",
            {"notebook": notebook_id, "path": path, "markdown": markdown},
        )
        if not isinstance(result, str):
            raise TypeError(f"Expected a document id string, but got {type(result)}")

        _push_message("创建文档", f"《{title}》已保存到 {doc_path}")
        return result
    except Exception as e:
        _push_error_message("创建文档失败", _humanize_error(e))
        raise


@mcp.tool()
def update_block(
    block_id: str, data: str, data_type: str = "markdown"
) -> List[Dict[str, Any]]:
    """更新块内容。

    适用场景:
        - 已知块 ID 时，直接替换该块内容。

    使用方法:
        - block_id: 目标块 ID。
        - data_type: 仅支持 markdown 或 dom。
        - data: 新内容。

    注意事项:
        - 这是整块替换，不是局部 patch。
        - 修改前请确保 block_id 指向正确块，避免误改。
    """
    try:
        if not block_id.strip():
            raise ValueError("block_id must be a non-empty string")
        _validate_block_data_type(data_type)

        # 获取旧内容用于对比
        old_content_dict = get_block_content(block_id)
        old_content = old_content_dict.get("kramdown", "")
        old_len = len(old_content)
        new_len = len(data)
        diff = new_len - old_len
        change_text = f"+{diff}字" if diff >= 0 else f"{diff}字"

        # 提取前后内容预览（用于通知显示）
        old_preview = _shorten(old_content.replace("\n", " ").strip(), 30)
        new_preview = _shorten(data.replace("\n", " ").strip(), 30)

        result = _post_to_siyuan_api(
            "/api/block/updateBlock",
            {"id": block_id, "data": data, "dataType": data_type},
        )
        if not isinstance(result, list):
            raise TypeError(f"Expected a list from updateBlock, but got {type(result)}")

        _push_message("更新内容", f"「{old_preview}...」→「{new_preview}...」 （{change_text}）")
        return result
    except Exception as e:
        _push_error_message("更新内容失败", _humanize_error(e))
        raise


@mcp.tool()
def delete_block(block_id: str) -> List[Dict[str, Any]]:
    """删除指定块。

    适用场景:
        - 清理错误插入或不再需要的块。

    注意事项:
        - 删除操作具破坏性，调用前建议先用查询工具确认 block_id。
        - 返回值包含操作记录，可用于审计本次删除结果。
    """
    try:
        if not block_id.strip():
            raise ValueError("block_id must be a non-empty string")

        meta = _get_block_metadata(block_id)
        if meta and meta.get("type") == "d":
            raise ValueError(
                "Refusing to delete a document block via delete_block. "
                + "Document deletion is intentionally not exposed via MCP tools; "
                + "please delete it manually in SiYuan."
            )

        # 获取被删除块的内容预览（需要在删除前读取）
        content_dict = get_block_content(block_id)
        content = content_dict.get("kramdown", "")
        preview = _shorten(content.replace("\n", " ").strip(), 50)

        result = _post_to_siyuan_api("/api/block/deleteBlock", {"id": block_id})
        if not isinstance(result, list):
            raise TypeError(f"Expected a list from deleteBlock, but got {type(result)}")

        _push_message("删除内容", f"已删除：{preview or '空白块'}")
        return result
    except Exception as e:
        _push_error_message("删除内容失败", _humanize_error(e))
        raise


@mcp.tool()
def insert_block(
    data: str,
    data_type: str = "markdown",
    next_id: Optional[str] = None,
    previous_id: Optional[str] = None,
    parent_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """插入块（next_id / previous_id / parent_id 至少提供一个）。

    适用场景:
        - 需要按相邻块位置插入（前置/后置锚点）。
        - 需要按父块插入（指定 parent_id）。

    使用方法:
        - next_id: 插入到 next_id 对应块之前。
        - previous_id: 插入到 previous_id 对应块之后。
        - parent_id: 插入为 parent_id 的子块。
        - 三者可同时提供，但思源 API 优先级为 next_id > previous_id > parent_id。

    注意事项:
        - 如果你要"确保挂到某个标题（如 H3）下面"，请显式传 parent_id，
          或直接使用 append_block / prepend_block。
        - 若 next_id/previous_id 与 parent_id 指向不同层级，最终位置会以
          next_id/previous_id 优先，可能出现"看起来没挂到标题下"的情况。

    与 prepend_block/append_block 的区别:
        - prepend_block/append_block 是"父块优先"，强制挂到父块下（开头/末尾）。
        - insert_block 是"相邻优先"，依赖现有块的位置，可能产生层级歧义。

    示例（假设现有结构：父块A -> 子块B -> 子块C）:
        # 插入到 B 之后（中间插入）
        insert_block(data="新块", previous_id="block_b")
        # 结果：A -> B -> 新块 -> C

        # 插入到 B 之前
        insert_block(data="新块", next_id="block_b")
        # 结果：A -> 新块 -> B -> C

        # 作为 A 的子块插入（不推荐，可能被相邻锚点覆盖）
        insert_block(data="新块", parent_id="block_a")
        # 注意：若同时传了 previous_id/next_id，parent_id 会被忽略
    """
    # 获取插入位置的上下文（用语义化预览代替 block_id）
    try:
        _validate_block_data_type(data_type)
        if not (next_id or previous_id or parent_id):
            raise ValueError(
                "At least one of next_id, previous_id, parent_id is required"
            )

        location_desc = "未知位置"
        if parent_id:
            parent_meta = _get_block_metadata(parent_id)
            if parent_meta:
                parent_type = parent_meta.get("type", "")
                if parent_type == "h":
                    title_preview = _get_block_content_preview(parent_id, 20)
                    location_desc = f"添加到标题「{title_preview}」下方"
                else:
                    parent_preview = _get_block_content_preview(parent_id, 20)
                    location_desc = f"添加到「{parent_preview}...」内"
        elif previous_id:
            prev_preview = _get_block_content_preview(previous_id, 20)
            location_desc = f"在「{prev_preview}...」之后"
        elif next_id:
            next_preview = _get_block_content_preview(next_id, 20)
            location_desc = f"在「{next_preview}...」之前"

        content_preview = _shorten(data.replace("\n", " "), 50)
        payload = {
            "data": data,
            "dataType": data_type,
            "nextID": next_id or "",
            "previousID": previous_id or "",
            "parentID": parent_id or "",
        }
        result = _post_to_siyuan_api("/api/block/insertBlock", payload)
        if not isinstance(result, list):
            raise TypeError(f"Expected a list from insertBlock, but got {type(result)}")

        _push_message("插入内容", f"{location_desc}：{content_preview}")
        return result
    except Exception as e:
        _push_error_message("插入内容失败", _humanize_error(e))
        raise


@mcp.tool()
def prepend_block(
    parent_id: str, data: str, data_type: str = "markdown"
) -> List[Dict[str, Any]]:
    """插入前置子块。

    适用场景:
        - 需要稳定地插入到某个父块下（强父子关系）。
        - 例如把列表、段落挂到某个 H2/H3 下。

    使用方法:
        - parent_id 传入目标父块 ID。
        - data 为待插入内容，data_type 支持 markdown 或 dom。

    注意事项:
        - 该工具是"父块优先"的安全写入方式，不依赖 next_id/previous_id。
        - 若需要基于相邻块精确定位，请使用 insert_block。

    与 insert_block 的区别:
        - prepend_block 强制作为父块的第一个子块，层级关系稳定。
        - insert_block 依赖相邻块定位，层级可能因 next_id/previous_id 而变化。

    示例（假设现有结构：父块A -> 子块B -> 子块C）:
        # 插入到 A 的开头（作为第一个子块）
        prepend_block(parent_id="block_a", data="新块")
        # 结果：A -> 新块 -> B -> C
    """
    try:
        if not parent_id.strip():
            raise ValueError("parent_id must be a non-empty string")
        _validate_block_data_type(data_type)

        # 获取父块信息
        parent_meta = _get_block_metadata(parent_id)
        parent_type = parent_meta.get("type", "") if parent_meta else ""
        location_text = "标题" if parent_type == "h" else "块"
        parent_preview = _get_block_content_preview(parent_id, 20)
        content_preview = _shorten(data.replace("\n", " "), 50)

        result = _post_to_siyuan_api(
            "/api/block/prependBlock",
            {"parentID": parent_id, "data": data, "dataType": data_type},
        )
        if not isinstance(result, list):
            raise TypeError(
                f"Expected a list from prependBlock, but got {type(result)}"
            )

        _push_message("前置插入", f"{location_text}「{parent_preview}」开头添加：{content_preview}")
        return result
    except Exception as e:
        _push_error_message("前置插入失败", _humanize_error(e))
        raise


@mcp.tool()
def append_block(
    parent_id: str, data: str, data_type: str = "markdown"
) -> List[Dict[str, Any]]:
    """插入后置子块。

    适用场景:
        - 需要稳定地追加到某个父块末尾（强父子关系）。
        - 例如把有序/无序列表追加到某个 H2/H3 下。

    使用方法:
        - parent_id 传入目标父块 ID。
        - data 为待插入内容，data_type 支持 markdown 或 dom。

    注意事项:
        - 该工具不会使用 next_id/previous_id 锚点，适合避免层级歧义。
        - 若需要插入到父块子节点中间位置，请使用 insert_block 并结合锚点。

    与 insert_block 的区别:
        - append_block 强制作为父块的最后一个子块，层级关系稳定。
        - insert_block 依赖相邻块定位，层级可能因 next_id/previous_id 而变化。

    示例（假设现有结构：父块A -> 子块B -> 子块C）:
        # 插入到 A 的末尾（作为最后一个子块）
        append_block(parent_id="block_a", data="新块")
        # 结果：A -> B -> C -> 新块
    """
    try:
        if not parent_id.strip():
            raise ValueError("parent_id must be a non-empty string")
        _validate_block_data_type(data_type)

        # 获取父块信息
        parent_meta = _get_block_metadata(parent_id)
        parent_type = parent_meta.get("type", "") if parent_meta else ""
        location_text = "标题" if parent_type == "h" else "块"
        parent_preview = _get_block_content_preview(parent_id, 20)
        content_preview = _shorten(data.replace("\n", " "), 50)

        result = _post_to_siyuan_api(
            "/api/block/appendBlock",
            {"parentID": parent_id, "data": data, "dataType": data_type},
        )
        if not isinstance(result, list):
            raise TypeError(f"Expected a list from appendBlock, but got {type(result)}")

        _push_message("后置插入", f"{location_text}「{parent_preview}」末尾添加：{content_preview}")
        return result
    except Exception as e:
        _push_error_message("后置插入失败", _humanize_error(e))
        raise


@mcp.tool()
def move_block(
    block_id: str,
    previous_id: Optional[str] = None,
    parent_id: Optional[str] = None,
    allow_heading_only_move: bool = False,
) -> List[Dict[str, Any]]:
    """移动块（previous_id / parent_id 至少提供一个）。

    适用场景:
        - 调整块顺序（基于 previous_id 锚点）。
        - 调整父子归属（基于 parent_id）。
        - 调整分节或层级结构时，保持相关内容整体移动。

    使用方法:
        - previous_id: 把 block_id 移动到 previous_id 之后。
        - parent_id: 把 block_id 移动到 parent_id 之下。
        - allow_heading_only_move: 兼容旧参数，已废弃；传 true 会报错。

    注意事项:
        - 若 block_id 是标题块（h1-h6），将按“分节范围”移动：
          从该标题开始，直到下一个同级或更高级标题（level <= 当前 level）之前的所有块一起移动。
        - 其他块默认按“子树块组”移动：目标块 + 全部后代，避免父块与子块脱离。
        - 思源 API 对同传 previous_id 和 parent_id 时会优先 previous_id。
        - previous_id / parent_id 不能指向正在移动的子树内部块。

    与 insert_block 的区别:
        - insert_block 是插入一个新块。
        - move_block 是移动已有块的位置。

    安全建议（重要）:
        - 不做“单块父节点移动”，统一执行整组移动，避免父块与内容脱离。
        - 若目标是“稳定挂到某个父块”，优先提供 parent_id。

    示例（假设现有结构：父块A -> 子块B -> 子块C -> 子块D）:
        # 调整顺序：移动 C 到 B 之后（不改变层级）
        move_block(block_id="block_c", previous_id="block_b")
        # 结果：A -> B -> C -> D（顺序不变，因为 C 原本就在 B 之后）

        # 调整层级：移动 C 成为 B 的子块
        move_block(block_id="block_c", parent_id="block_b")
        # 结果：A -> B -> C（现在 C 是 B 的子块）-> D

        # 同时调整顺序和层级
        move_block(block_id="block_c", previous_id="block_b", parent_id="block_a")
        # 注意：API 会优先处理 previous_id，parent_id 可能被忽略
    """
    try:
        if not block_id.strip():
            raise ValueError("block_id must be a non-empty string")
        if not (previous_id or parent_id):
            raise ValueError("At least one of previous_id or parent_id is required")
        if type(allow_heading_only_move) is not bool:
            raise ValueError("allow_heading_only_move must be a boolean")

        if allow_heading_only_move:
            raise ValueError(
                "allow_heading_only_move has been deprecated. "
                + "move_block now always performs group move to prevent partial moves."
            )

        # 获取被移动块的内容预览
        moved_preview = _get_block_content_preview(block_id, 20)
        metadata = _get_block_metadata(block_id)

        # 构建语义化的移动描述
        move_action = "移动到未知位置"
        if previous_id:
            prev_preview = _get_block_content_preview(previous_id, 20)
            move_action = f"移动到「{prev_preview}...」之后"
        elif parent_id:
            parent_meta = _get_block_metadata(parent_id)
            if parent_meta and parent_meta.get("type") == "h":
                parent_preview = _get_block_content_preview(parent_id, 20)
                move_action = f"移动到标题「{parent_preview}」下方"
            else:
                move_action = "移动到块内"

        previous_meta: Optional[Dict[str, Any]] = None
        if previous_id:
            previous_meta = _get_block_metadata(previous_id)
            if not previous_meta:
                raise ValueError(f"previous_id not found: {previous_id}")
            if previous_meta.get("type") == "d":
                raise ValueError(
                    "previous_id cannot be a document block (type='d'); "
                    + "Siyuan moveBlock may silently lose blocks in this case."
                )

        is_heading = bool(metadata and metadata.get("type") == "h")

        if is_heading:
            section_top_level_ids = _collect_heading_section_ids(block_id)
            target_parent_id = parent_id
            if not target_parent_id and metadata:
                raw_parent_id = metadata.get("parent_id")
                target_parent_id = (
                    raw_parent_id if isinstance(raw_parent_id, str) else ""
                )
            if not target_parent_id:
                raise ValueError("parent_id could not be resolved for section move")

            effective_previous_id = previous_id
            if previous_id and previous_meta:
                if previous_meta.get("type") == "h":
                    anchor_section_ids = _collect_heading_section_ids(previous_id)
                    if anchor_section_ids:
                        effective_previous_id = anchor_section_ids[-1]

            if not effective_previous_id:
                try:
                    parent_rows = _get_child_blocks_rows(target_parent_id)
                    parent_ids: List[str] = []
                    for row in parent_rows:
                        row_id = row.get("id")
                        if isinstance(row_id, str) and row_id:
                            parent_ids.append(row_id)

                    for candidate_id in reversed(parent_ids):
                        if candidate_id not in section_top_level_ids:
                            effective_previous_id = candidate_id
                            break
                except Exception:
                    effective_previous_id = None

            if effective_previous_id and effective_previous_id in section_top_level_ids:
                raise ValueError(
                    "previous_id cannot point to a block inside the moving group"
                )

            moved_ids, result = _move_section_group_after(
                section_top_level_ids, effective_previous_id, target_parent_id
            )
            moved_count = len(moved_ids)
        else:
            moved_ids, result = _move_block_group(block_id, previous_id, parent_id)
            moved_count = len(moved_ids)

        _push_message(
            "移动内容", f"「{moved_preview}」已{move_action}（共{moved_count}个块）"
        )
        return result
    except Exception as e:
        _push_error_message("移动内容失败", _humanize_error(e))
        raise


@mcp.tool()
def list_files(path: str) -> List[Dict[str, Any]]:
    """列出指定路径下的文件和文件夹（只读）。

    常用于探索 '/data' 目录结构，例如查看 '/data/history' 下的快照。

    注意事项:
        - 该工具仅读取目录，不会修改任何文件。
        - 返回结果依赖思源工作空间内的实际路径权限。

    Args:
        path: 路径，例如 '/data' 或 '/data/history'。

    Returns:
        list: 包含文件和文件夹信息的字典列表。
    """
    result = _post_to_siyuan_api("/api/file/readDir", {"path": path})
    if not isinstance(result, list):
        raise TypeError(f"Expected a list from readDir, but got {type(result)}")
    return result


@mcp.tool()
def get_file(path: str) -> str:
    """读取指定文件的内容（只读）。

    用于读取历史快照或其他数据文件。

    注意事项:
        - 文本内容会进行敏感信息打码。
        - 若文件为二进制且无法解码为 UTF-8，将返回 '[Binary Data]'。

    Args:
        path: 文件路径，例如 '/data/history/2023/01/...'。

    Returns:
        str: 文件内容（文本）或二进制数据提示。
    """
    # 验证环境变量中的 Token
    api_token = os.getenv("SIYUAN_API_TOKEN")
    if not api_token:
        raise ValueError("SIYUAN_API_TOKEN environment variable not set.")

    base_url = os.getenv("SIYUAN_API_URL", "http://127.0.0.1:6806").rstrip("/")

    headers = {
        "Authorization": f"Token {api_token}",
        "Content-Type": "application/json",
    }

    url = f"{base_url}/api/file/getFile"
    try:
        response = requests.post(url, json={"path": path}, headers=headers)
        response.raise_for_status()

        # 尝试将内容解码为文本
        try:
            content = response.content.decode("utf-8")
            # 对文件内容进行敏感信息打码
            return mask_sensitive_data(content)
        except UnicodeDecodeError:
            return "[Binary Data]"

    except requests.exceptions.RequestException as e:
        raise ConnectionError(f"Failed to get file: {e}") from e


@mcp.tool()
def get_file_base64(path: str) -> str:
    """读取指定文件内容并以 Base64 返回（只读）。

    适用于需要以 Base64 形式返回的 UTF-8 文本文件（例如历史快照里的 JSON）。

    注意事项:
        - 本实现会先按 UTF-8 解码后再打码并进行 Base64 编码。
        - 若文件为纯二进制且无法 UTF-8 解码，将抛出异常（不支持二进制打码）。

    Args:
        path: 文件路径，例如 '/history/.../blocks.msgpack'。

    Returns:
        str: Base64 编码的文件内容（已打码）。
    """
    api_token = os.getenv("SIYUAN_API_TOKEN")
    if not api_token:
        raise ValueError("SIYUAN_API_TOKEN environment variable not set.")

    base_url = os.getenv("SIYUAN_API_URL", "http://127.0.0.1:6806").rstrip("/")

    headers = {
        "Authorization": f"Token {api_token}",
        "Content-Type": "application/json",
    }

    url = f"{base_url}/api/file/getFile"
    try:
        response = requests.post(url, json={"path": path}, headers=headers)
        response.raise_for_status()
        try:
            text = response.content.decode("utf-8")
        except UnicodeDecodeError as e:
            raise ValueError(
                "Binary content cannot be safely masked for base64 export."
            ) from e

        masked = mask_sensitive_data(text)
        return base64.b64encode(masked.encode("utf-8")).decode("ascii")
    except requests.exceptions.RequestException as e:
        raise ConnectionError(f"Failed to get file: {e}") from e


@mcp.tool()
def list_history_entries(path: str = "/history") -> List[Dict[str, Any]]:
    """列出历史快照目录下的文件和文件夹。

    注意事项:
        - path 必须以 '/history' 或 '/data/history' 开头。
        - 该工具用于枚举历史目录，不直接返回快照内容。

    Args:
        path: 历史目录路径，默认为 "/history"。

    Returns:
        list: 历史目录下的条目列表。
    """
    if not (path.startswith("/history") or path.startswith("/data/history")):
        raise ValueError("path must start with /history or /data/history")
    result = _post_to_siyuan_api("/api/file/readDir", {"path": path})
    if not isinstance(result, list):
        raise TypeError(f"Expected a list from readDir, but got {type(result)}")
    return result


@mcp.tool()
def get_history_file(path: str) -> str:
    """读取历史快照文件内容（只读）。

    注意事项:
        - path 必须以 '/history' 或 '/data/history' 开头。
        - 行为与 get_file 一致，文本会做敏感信息打码。

    Args:
        path: 历史快照文件路径，必须以 "/history" 或 "/data/history" 开头。

    Returns:
        str: 历史快照文件内容。
    """
    if not (path.startswith("/history") or path.startswith("/data/history")):
        raise ValueError("path must start with /history or /data/history")
    return get_file(path)


def _get_file_text_raw(path: str) -> str:
    api_token = os.getenv("SIYUAN_API_TOKEN")
    if not api_token:
        raise ValueError("SIYUAN_API_TOKEN environment variable not set.")

    base_url = os.getenv("SIYUAN_API_URL", "http://127.0.0.1:6806").rstrip("/")

    headers = {
        "Authorization": f"Token {api_token}",
        "Content-Type": "application/json",
    }

    url = f"{base_url}/api/file/getFile"
    try:
        response = requests.post(url, json={"path": path}, headers=headers)
        response.raise_for_status()
        return response.content.decode("utf-8")
    except UnicodeDecodeError as e:
        raise ValueError("Binary content cannot be decoded as UTF-8 text.") from e
    except requests.exceptions.RequestException as e:
        raise ConnectionError(f"Failed to get file: {e}") from e


def _load_sy_json_from_path(path: str) -> Dict[str, Any]:
    text = _get_file_text_raw(path)
    return json.loads(text)


def _extract_text_from_node(node: Dict[str, Any]) -> str:
    node_type = node.get("Type")
    if node_type == "NodeText":
        return node.get("Data", "")
    if node_type == "NodeTextMark":
        return node.get("TextMarkTextContent", "")
    return ""


def _walk_block_tree(node: Dict[str, Any], block_map: Dict[str, str]) -> str:
    children = node.get("Children", [])
    if children:
        child_texts = [_walk_block_tree(child, block_map) for child in children]
        aggregated = "".join(child_texts)
    else:
        aggregated = ""

    node_text = _extract_text_from_node(node)
    combined = node_text + aggregated

    node_id = node.get("ID") or node.get("Properties", {}).get("id")
    if node_id:
        block_map[node_id] = combined

    return combined


def _build_block_text_map(doc_json: Dict[str, Any]) -> Dict[str, str]:
    block_map: Dict[str, str] = {}
    _walk_block_tree(doc_json, block_map)
    return block_map


def _parse_history_dir_name(name: str) -> Optional[Tuple[str, str]]:
    match = re.match(r"^(\d{4})-(\d{2})-(\d{2})-(\d{6})-(\w+)$", name)
    if not match:
        return None
    ts = "".join(match.groups()[:4])
    kind = match.group(5)
    return ts, kind


def _select_snapshot(entries: List[Dict[str, Any]], target_time: str) -> Optional[str]:
    candidates = []
    for entry in entries:
        name = entry.get("name")
        if not name:
            continue
        parsed = _parse_history_dir_name(name)
        if not parsed:
            continue
        ts, kind = parsed
        if ts <= target_time:
            candidates.append((ts, kind, name))

    if not candidates:
        return None

    kind_priority = {"update": 3, "sync": 2, "delete": 1}
    candidates.sort(
        key=lambda item: (item[0], kind_priority.get(item[1], 0)), reverse=True
    )
    return candidates[0][2]


def _describe_diff(before: str, after: str) -> Dict[str, Any]:
    matcher = difflib.SequenceMatcher(None, before, after)
    ratio = matcher.ratio()
    insert_chars = 0
    delete_chars = 0
    replace_segments = 0
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "insert":
            insert_chars += j2 - j1
        elif tag == "delete":
            delete_chars += i2 - i1
        elif tag == "replace":
            replace_segments += 1
            insert_chars += j2 - j1
            delete_chars += i2 - i1
    return {
        "similarity": round(ratio, 3),
        "inserted_chars": insert_chars,
        "deleted_chars": delete_chars,
        "replaced_segments": replace_segments,
    }


def _describe_change(before: str, after: str, stats: Dict[str, Any]) -> str:
    if not before and after:
        return "新增"
    if before and not after:
        return "删除"
    inserted = stats.get("inserted_chars", 0)
    deleted = stats.get("deleted_chars", 0)
    if inserted > 0 and deleted == 0:
        return "补充"
    if deleted > 0 and inserted == 0:
        return "删减"
    return "替换"


@mcp.tool()
def get_block_changes(
    start_time: str,
    end_time: Optional[str] = None,
    limit: int = 200,
    include_markdown: bool = False,
) -> Dict[str, Any]:
    """查询指定时间范围内新增或修改的内容块。

    适用场景:
    - 只需要变更清单/索引, 不关心逐块前后差异。
    - 需要快速筛选近期新增或更新的块。

    与 get_block_diffs 的区别:
    - 本函数不做历史快照对比, 不返回 before/after。
    - 返回的是当前块的字段快照(例如 content/markdown)。

    注意事项:
    - deleted 当前恒为空；删除块需要结合历史快照比对才能识别。
    - include_markdown=true 会显著增大返回体量，建议配合 limit 使用。

    Args:
        start_time: 起始时间，格式为 'YYYYMMDDHHMMSS'。
        end_time: 结束时间，格式为 'YYYYMMDDHHMMSS'，可选。
        limit: 最大返回条目数，默认为 200。
        include_markdown: 是否返回 markdown 字段，默认 false。

    Returns:
        Dict[str, Any]: 包含新增与修改块列表以及历史快照可用性信息。
    """
    if not is_siyuan_timestamp(start_time):
        raise ValueError("start_time must be in 'YYYYMMDDHHMMSS' format")
    if end_time and not is_siyuan_timestamp(end_time):
        raise ValueError("end_time must be in 'YYYYMMDDHHMMSS' format")

    time_conditions = []
    created_condition = f"created >= '{start_time}'"
    updated_condition = f"updated >= '{start_time}'"
    if end_time:
        created_condition += f" AND created <= '{end_time}'"
        updated_condition += f" AND updated <= '{end_time}'"
    time_conditions.append(f"({created_condition})")
    time_conditions.append(f"({updated_condition})")
    time_clause = " OR ".join(time_conditions)

    fields = [
        "id",
        "root_id",
        "hpath",
        "path",
        "type",
        "subtype",
        "created",
        "updated",
        "content",
    ]
    if include_markdown:
        fields.append("markdown")
    query = f"SELECT {', '.join(fields)} FROM blocks WHERE {time_clause} ORDER BY updated DESC LIMIT {limit}"

    if not query.strip().upper().startswith("SELECT"):
        raise ValueError("Only SELECT statements are allowed for security reasons.")

    results = _post_to_siyuan_api("/api/query/sql", {"stmt": query})
    if not isinstance(results, list):
        raise TypeError(f"Expected a list from SQL query, but got {type(results)}")

    history_available = True
    history_error = None
    try:
        _post_to_siyuan_api("/api/file/readDir", {"path": "/history"})
    except Exception as e:
        history_available = False
        history_error = str(e)

    added = []
    modified = []
    for row in results:
        if not isinstance(row, dict):
            continue
        created = str(row.get("created", ""))
        updated = str(row.get("updated", ""))
        in_created_range = created >= start_time and (
            not end_time or created <= end_time
        )
        in_updated_range = updated >= start_time and (
            not end_time or updated <= end_time
        )

        item = dict(row)
        for key, value in item.items():
            if isinstance(value, str):
                item[key] = mask_sensitive_data(value)

        if in_created_range:
            added.append(item)
        elif in_updated_range and created < start_time:
            modified.append(item)

    return {
        "range": {"start": start_time, "end": end_time},
        "history_available": history_available,
        "history_error": history_error,
        "added": added,
        "modified": modified,
        "deleted": [],
        "note": "Deleted blocks require history snapshot diff; current API cannot infer deletions without /history.",
    }


@mcp.tool()
def get_block_diffs(
    start_time: str,
    end_time: Optional[str] = None,
    limit: int = 50,
    history_root: str = "/history",
    max_text_length: int = 400,
) -> Dict[str, Any]:
    """查询指定时间范围内修改的内容块并返回前后对比。

    适用场景:
    - 需要审计每个块的具体改动(含 before/after)。
    - 需要变更类型(新增/删减/替换)和差异统计。

    与 get_block_changes 的区别:
    - 本函数会读取历史快照并与当前内容对比。
    - 返回 before/after 文本和 diff 统计, 但更重且依赖 /history。

    注意事项:
    - 依赖 history_root 可读；若历史目录不可访问，将无法完成比对。
    - before/after 为脱敏文本；max_text_length 会对长文本截断。

    Args:
        start_time: 起始时间，格式为 'YYYYMMDDHHMMSS'。
        end_time: 结束时间，格式为 'YYYYMMDDHHMMSS'，可选。
        limit: 最大返回条目数，默认为 50。
        history_root: 历史快照根目录，默认为 '/history'。
        max_text_length: 前后文本最大长度，超出将截断。

    Returns:
        Dict[str, Any]: 包含块变更差异结果。
    """
    if not is_siyuan_timestamp(start_time):
        raise ValueError("start_time must be in 'YYYYMMDDHHMMSS' format")
    if end_time and not is_siyuan_timestamp(end_time):
        raise ValueError("end_time must be in 'YYYYMMDDHHMMSS' format")
    if not history_root.startswith("/"):
        raise ValueError("history_root must be an absolute path")

    created_condition = f"created >= '{start_time}'"
    updated_condition = f"updated >= '{start_time}'"
    if end_time:
        created_condition += f" AND created <= '{end_time}'"
        updated_condition += f" AND updated <= '{end_time}'"

    time_clause = f"({created_condition}) OR ({updated_condition})"
    query = (
        "SELECT id, root_id, box, path, type, subtype, created, updated "
        f"FROM blocks WHERE {time_clause} ORDER BY updated DESC LIMIT {limit}"
    )

    if not query.strip().upper().startswith("SELECT"):
        raise ValueError("Only SELECT statements are allowed for security reasons.")

    rows = _post_to_siyuan_api("/api/query/sql", {"stmt": query})
    if not isinstance(rows, list):
        raise TypeError(f"Expected a list from SQL query, but got {type(rows)}")

    history_entries = _post_to_siyuan_api("/api/file/readDir", {"path": history_root})
    if not isinstance(history_entries, list):
        raise TypeError("Expected history entries list from readDir")

    current_cache: Dict[str, Dict[str, str]] = {}
    history_cache: Dict[Tuple[str, str], Dict[str, str]] = {}
    deleted_candidates: Dict[str, Dict[str, Any]] = {}

    diffs = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        block_id = row.get("id")
        path = row.get("path")
        box = row.get("box")
        updated = str(row.get("updated", ""))
        created = str(row.get("created", ""))

        if not block_id or not path or not box or not updated:
            continue

        snapshot = _select_snapshot(history_entries, updated)
        history_path = None
        if snapshot:
            history_path = f"{history_root}/{snapshot}/{box}{path}"

        current_path = f"/data/{box}{path}"

        if current_path not in current_cache:
            try:
                current_json = _load_sy_json_from_path(current_path)
                current_cache[current_path] = _build_block_text_map(current_json)
            except Exception:
                current_cache[current_path] = {}

        current_map = current_cache.get(current_path, {})
        after_text = current_map.get(block_id)

        before_text = None
        if history_path and snapshot:
            cache_key = (snapshot, history_path)
            if cache_key not in history_cache:
                try:
                    history_json = _load_sy_json_from_path(history_path)
                    history_cache[cache_key] = _build_block_text_map(history_json)
                except Exception:
                    history_cache[cache_key] = {}
            before_text = history_cache.get(cache_key, {}).get(block_id)

            current_ids = set(current_map.keys())
            history_map = history_cache.get(cache_key, {})
            for history_id, history_text in history_map.items():
                if history_id in current_ids:
                    continue
                if not history_text:
                    continue
                if history_id in deleted_candidates:
                    continue
                deleted_candidates[history_id] = {
                    "id": history_id,
                    "box": box,
                    "path": path,
                    "snapshot": snapshot,
                    "before": mask_sensitive_data(history_text),
                    "after": "",
                    "change": "删除",
                }

        if before_text == after_text:
            continue

        if after_text is None and before_text is None:
            continue

        masked_before = mask_sensitive_data(before_text or "")
        masked_after = mask_sensitive_data(after_text or "")

        if max_text_length > 0:
            if len(masked_before) > max_text_length:
                masked_before = masked_before[:max_text_length] + "..."
            if len(masked_after) > max_text_length:
                masked_after = masked_after[:max_text_length] + "..."

        diff_stats = _describe_diff(before_text or "", after_text or "")
        change_desc = _describe_change(before_text or "", after_text or "", diff_stats)

        diffs.append(
            {
                "id": block_id,
                "box": box,
                "path": path,
                "type": row.get("type"),
                "subtype": row.get("subtype"),
                "created": created,
                "updated": updated,
                "snapshot": snapshot,
                "before": masked_before,
                "after": masked_after,
                "diff": diff_stats,
                "change": change_desc,
            }
        )

    return {
        "range": {"start": start_time, "end": end_time},
        "history_root": history_root,
        "count": len(diffs),
        "diffs": diffs,
        "deleted": list(deleted_candidates.values()),
        "note": "Diff is derived by comparing current /data file with the latest history snapshot <= updated time.",
    }


def main() -> None:
    """CLI entrypoint for uv run / project.scripts."""
    mcp.run()


if __name__ == "__main__":
    main()
