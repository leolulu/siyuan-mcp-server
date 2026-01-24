import base64
import difflib
import json
import os
import re
from typing import Any, Dict, List, Optional, Tuple

import requests
from mcp.server.fastmcp import FastMCP

from .tools import is_siyuan_timestamp, mask_sensitive_data, parse_and_mask_kramdown


def _post_to_siyuan_api(endpoint: str, json_data: Optional[Dict[str, Any]] = None) -> Any:
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

    # 配置请求头
    headers = {
        "Authorization": f"Token {api_token}",
        "Content-Type": "application/json",
    }

    # 发送请求
    url = f"http://127.0.0.1:6806{endpoint}"
    try:
        response = requests.post(url, json=json_data, headers=headers)
        response.raise_for_status()
        api_response = response.json()
        if api_response.get("code") != 0:
            raise Exception(f"Siyuan API Error: {api_response.get('msg')}")
        return api_response.get("data")
    except requests.exceptions.RequestException as e:
        raise ConnectionError(f"Failed to connect to Siyuan API: {e}")


# 创建 MCP 服务器实例
mcp = FastMCP("siyuan-mcp-server")


@mcp.tool()
def find_notebooks(name: Optional[str] = None, limit: int = 10) -> list:
    """查找并列出思源笔记中的笔记本。

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
        notebooks = [nb for nb in notebooks if name.lower() in nb.get("name", "").lower()]

    # 限制返回结果数量
    return notebooks[:limit]


@mcp.tool()
def find_documents(
    notebook_id: Optional[str] = None,
    title: Optional[str] = None,
    created_after: Optional[str] = None,
    updated_after: Optional[str] = None,
    limit: int = 10,
) -> list:
    """在指定的笔记本中查找文档，支持多种过滤条件。

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
) -> list:
    """根据关键词、类型等多种条件在思源笔记中搜索内容块。

    这是最核心和最灵活的查询工具。

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
    sql_query = "SELECT id, content, type, subtype, hpath FROM blocks WHERE content LIKE ?"
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

    Args:
        block_ids (List[str]): 块 ID 列表

    Returns:
        List[Dict[str, Any]]: 包含每个块内容的字典列表
    """
    results = []
    for block_id in block_ids:
        try:
            result = _post_to_siyuan_api("/api/block/getBlockKramdown", {"id": block_id})
            if isinstance(result, dict):
                # 对 kramdown 字段进行智能敏感信息打码，保留思源属性中的ID
                if "kramdown" in result and isinstance(result["kramdown"], str):
                    result["kramdown"] = parse_and_mask_kramdown(result["kramdown"])
                results.append(result)
            else:
                results.append({"id": block_id, "error": f"Unexpected type: {type(result)}"})
        except Exception as e:
            results.append({"id": block_id, "error": str(e)})
    return results


@mcp.tool()
def execute_sql(query: str) -> List[Dict[str, Any]]:
    """直接对数据库执行只读的 SELECT 查询。

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
def list_files(path: str) -> list:
    """列出指定路径下的文件和文件夹（只读）。

    常用于探索 '/data' 目录结构，例如查看 '/data/history' 下的快照。

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

    Args:
        path: 文件路径，例如 '/data/history/2023/01/...'。

    Returns:
        str: 文件内容（文本）或二进制数据提示。
    """
    # 验证环境变量中的 Token
    api_token = os.getenv("SIYUAN_API_TOKEN")
    if not api_token:
        raise ValueError("SIYUAN_API_TOKEN environment variable not set.")

    headers = {
        "Authorization": f"Token {api_token}",
        "Content-Type": "application/json",
    }

    url = "http://127.0.0.1:6806/api/file/getFile"
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
        raise ConnectionError(f"Failed to get file: {e}")


@mcp.tool()
def get_file_base64(path: str) -> str:
    """读取指定文件内容并以 Base64 返回（只读）。

    适用于二进制文件，例如历史快照中的 msgpack。

    Args:
        path: 文件路径，例如 '/history/.../blocks.msgpack'。

    Returns:
        str: Base64 编码的文件内容（已打码）。
    """
    api_token = os.getenv("SIYUAN_API_TOKEN")
    if not api_token:
        raise ValueError("SIYUAN_API_TOKEN environment variable not set.")

    headers = {
        "Authorization": f"Token {api_token}",
        "Content-Type": "application/json",
    }

    url = "http://127.0.0.1:6806/api/file/getFile"
    try:
        response = requests.post(url, json={"path": path}, headers=headers)
        response.raise_for_status()
        try:
            text = response.content.decode("utf-8")
        except UnicodeDecodeError:
            raise ValueError("Binary content cannot be safely masked for base64 export.")

        masked = mask_sensitive_data(text)
        return base64.b64encode(masked.encode("utf-8")).decode("ascii")
    except requests.exceptions.RequestException as e:
        raise ConnectionError(f"Failed to get file: {e}")


@mcp.tool()
def list_history_entries(path: str = "/history") -> list:
    """列出历史快照目录下的文件和文件夹。

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

    headers = {
        "Authorization": f"Token {api_token}",
        "Content-Type": "application/json",
    }

    url = "http://127.0.0.1:6806/api/file/getFile"
    try:
        response = requests.post(url, json={"path": path}, headers=headers)
        response.raise_for_status()
        return response.content.decode("utf-8")
    except UnicodeDecodeError:
        raise ValueError("Binary content cannot be decoded as UTF-8 text.")
    except requests.exceptions.RequestException as e:
        raise ConnectionError(f"Failed to get file: {e}")


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
    candidates.sort(key=lambda item: (item[0], kind_priority.get(item[1], 0)), reverse=True)
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

    fields = ["id", "root_id", "hpath", "path", "type", "subtype", "created", "updated", "content"]
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
        in_created_range = created >= start_time and (not end_time or created <= end_time)
        in_updated_range = updated >= start_time and (not end_time or updated <= end_time)

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
