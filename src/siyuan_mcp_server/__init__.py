import os
from typing import Any, Dict, List, Optional

import requests
from mcp.server.fastmcp import FastMCP

from .tools import mask_sensitive_data


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
        raise TypeError(
            f"Expected a dict with 'notebooks' key, but got {type(result)}"
        )
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

    Args:
        block_id (str): 块的 ID

    Returns:
        Dict[str, Any]: 包含块内容的字典
    """
    result = _post_to_siyuan_api("/api/block/getBlockKramdown", {"id": block_id})
    if not isinstance(result, dict):
        raise TypeError(
            f"Expected a dict for block content, but got {type(result)}"
        )
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

    url = f"http://127.0.0.1:6806/api/file/getFile"
    try:
        response = requests.post(url, json={"path": path}, headers=headers)
        if response.status_code == 202:
            try:
                res_json = response.json()
                raise Exception(f"Siyuan API Error: {res_json.get('msg')}")
            except ValueError:
                raise Exception("Siyuan API returned 202 Error")
        response.raise_for_status()
        content_bytes = response.content
    except requests.exceptions.RequestException as e:
        raise ConnectionError(f"Failed to get file: {e}")

    try:
        content = content_bytes.decode("utf-8")
        return mask_sensitive_data(content)
    except UnicodeDecodeError:
        return f"<Binary Data: {len(content_bytes)} bytes>"


def main():
    """MCP 服务器入口函数

    通过 uvx 或 pip install 安装后，可通过命令行直接运行此服务器。
    """
    mcp.run()


if __name__ == "__main__":
    # 运行方式:
    # 1. 设置 SIYUAN_API_TOKEN 环境变量
    # 2. 使用 uv run 直接运行: uv run siyuan_mcp_server.py
    # 3. 安装后使用: siyuan-mcp-server
    main()
