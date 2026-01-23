import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import mcp
import requests
from mcp.server.fastmcp import Context, FastMCP
from mcp.server.session import ServerSession

from .tools import mask_sensitive_data


# --- 1. Siyuan API Wrapper ---
class SiyuanAPI:
    def __init__(self, api_token: str, base_url: str = "http://127.0.0.1:6806"):
        self.base_url = base_url
        self.api_token = api_token
        self.headers = {
            "Authorization": f"Token {self.api_token}",
            "Content-Type": "application/json",
        }

    def _post(self, endpoint: str, json_data: Optional[Dict[str, Any]] = None) -> Any:
        url = f"{self.base_url}{endpoint}"
        try:
            response = requests.post(url, json=json_data, headers=self.headers)
            response.raise_for_status()
            api_response = response.json()
            if api_response.get("code") != 0:
                raise Exception(f"Siyuan API Error: {api_response.get('msg')}")
            return api_response.get("data")
        except requests.exceptions.RequestException as e:
            raise ConnectionError(f"Failed to connect to Siyuan API: {e}")

    def execute_sql(self, query: str) -> List[Dict[str, Any]]:
        if not query.strip().upper().startswith("SELECT"):
            raise ValueError("Only SELECT statements are allowed for security reasons.")
        payload = {"stmt": query}
        result = self._post("/api/query/sql", payload)
        if not isinstance(result, list):
            raise TypeError(f"Expected a list from SQL query, but got {type(result)}")
        return result

    def get_block_kramdown(self, block_id: str) -> Dict[str, Any]:
        result = self._post("/api/block/getBlockKramdown", {"id": block_id})
        if not isinstance(result, dict):
            raise TypeError(
                f"Expected a dict for block content, but got {type(result)}"
            )
        return result

    def list_notebooks(self) -> List[Dict[str, Any]]:
        """获取笔记本列表"""
        result = self._post("/api/notebook/lsNotebooks")
        if not isinstance(result, dict) or "notebooks" not in result:
            raise TypeError(
                f"Expected a dict with 'notebooks' key, but got {type(result)}"
            )
        return result["notebooks"]

    def get_blocks_kramdown(self, block_ids: List[str]) -> List[Dict[str, Any]]:
        """批量获取多个块的内容"""
        results = []
        for block_id in block_ids:
            try:
                result = self.get_block_kramdown(block_id)
                results.append(result)
            except Exception as e:
                # 如果某个块获取失败，记录错误但继续处理其他块
                results.append({"id": block_id, "error": str(e)})
        return results

    def read_dir(self, path: str) -> List[Dict[str, Any]]:
        """列出目录下的文件"""
        result = self._post("/api/file/readDir", {"path": path})
        if not isinstance(result, list):
            raise TypeError(f"Expected a list from readDir, but got {type(result)}")
        return result

    def get_file_bytes(self, path: str) -> bytes:
        """获取文件内容的原始字节"""
        url = f"{self.base_url}/api/file/getFile"
        try:
            response = requests.post(url, json={"path": path}, headers=self.headers)
            if response.status_code == 202:
                try:
                    res_json = response.json()
                    raise Exception(f"Siyuan API Error: {res_json.get('msg')}")
                except ValueError:
                    raise Exception("Siyuan API returned 202 Error")
            response.raise_for_status()
            return response.content
        except requests.exceptions.RequestException as e:
            raise ConnectionError(f"Failed to get file: {e}")


# --- 2. Application Context ---
@dataclass
class AppContext:
    siyuan_api: SiyuanAPI


# --- 3. Lifespan Management ---
@asynccontextmanager
async def app_lifespan(server: FastMCP) -> AsyncIterator[AppContext]:
    api_token = os.getenv("SIYUAN_API_TOKEN")
    if not api_token:
        raise ValueError("SIYUAN_API_TOKEN environment variable not set.")

    siyuan_api = SiyuanAPI(api_token=api_token)
    try:
        print("Siyuan API client initialized.")
        yield AppContext(siyuan_api=siyuan_api)
    finally:
        print("Siyuan MCP Server shutting down.")


# --- 4. MCP Server Instance ---
mcp = FastMCP("siyuan-mcp-server", lifespan=app_lifespan)


# --- 5. Tool Definitions ---
@mcp.tool()
def find_notebooks(
    ctx: Context[ServerSession, AppContext], name: Optional[str] = None, limit: int = 10
) -> list:
    """查找并列出思源笔记中的笔记本。

    Args:
        ctx: MCP 上下文对象，自动注入。
        name (Optional[str]): 用于模糊搜索笔记本的名称。如果省略，则列出所有笔记本。
        limit (int): 返回结果的最大数量，默认为 10。

    Returns:
        list: 包含笔记本信息的字典列表，每个字典包含 'name' 和 'id'。
    """
    api = ctx.request_context.lifespan_context.siyuan_api
    notebooks = api.list_notebooks()

    # 如果指定了名称，则进行过滤
    if name:
        notebooks = [
            nb for nb in notebooks if name.lower() in nb.get("name", "").lower()
        ]

    # 限制返回结果数量
    return notebooks[:limit]


@mcp.tool()
def find_documents(
    ctx: Context[ServerSession, AppContext],
    notebook_id: Optional[str] = None,
    title: Optional[str] = None,
    created_after: Optional[str] = None,
    updated_after: Optional[str] = None,
    limit: int = 10,
) -> list:
    """在指定的笔记本中查找文档，支持多种过滤条件。

    Args:
        ctx: MCP 上下文对象，自动注入。
        notebook_id (Optional[str]): 在哪个笔记本中查找。如果省略，则在所有打开的笔记本中查找。
        title (Optional[str]): 根据文档标题进行模糊匹配。
        created_after (Optional[str]): 查找在此日期之后创建的文档，格式为 'YYYYMMDDHHMMSS'。
        updated_after (Optional[str]): 查找在此日期之后更新的文档，格式为 'YYYYMMDDHHMMSS'。
        limit (int): 返回结果的最大数量，默认为 10。

    Returns:
        list: 包含文档信息的字典列表，每个字典包含 'name', 'id', 和 'hpath'。
    """
    api = ctx.request_context.lifespan_context.siyuan_api
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
    return api.execute_sql(query)


@mcp.tool()
def search_blocks(
    ctx: Context[ServerSession, AppContext],
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
        ctx: MCP 上下文对象，自动注入。
        query (str): 在块内容中搜索的关键词。
        parent_id (Optional[str]): 在哪个文档或父块下进行搜索。如果省略，则全局搜索。
        block_type (Optional[str]): 限制块的类型，例如 'p' (段落), 'h' (标题), 'l' (列表)。
        created_after (Optional[str]): 查找在此日期之后创建的块，格式为 'YYYYMMDDHHMMSS'。
        updated_after (Optional[str]): 查找在此日期之后更新的块，格式为 'YYYYMMDDHHMMSS'。
        limit (int): 返回结果的最大数量，默认为 20。

    Returns:
        list: 包含块信息的字典列表。
    """
    api = ctx.request_context.lifespan_context.siyuan_api
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
    for param in params:
        sanitized_param = str(param).replace("'", "''")
        sql_query = sql_query.replace("?", f"'{sanitized_param}'", 1)
    results = api.execute_sql(sql_query)

    # 对搜索结果中的内容进行打码处理
    for result in results:
        if isinstance(result, dict):
            if "content" in result:
                result["content"] = mask_sensitive_data(result["content"])

    return results


@mcp.tool()
def list_files(ctx: Context[ServerSession, AppContext], path: str) -> list:
    """列出指定路径下的文件和文件夹（只读）。

    常用于探索 '/data' 目录结构，例如查看 '/data/history' 下的快照。

    Args:
        ctx: MCP 上下文对象，自动注入。
        path: 路径，例如 '/data' 或 '/data/history'。

    Returns:
        list: 包含文件和文件夹信息的字典列表。
    """
    api = ctx.request_context.lifespan_context.siyuan_api
    return api.read_dir(path)


@mcp.tool()
def get_file(ctx: Context[ServerSession, AppContext], path: str) -> str:
    """读取指定文件的内容（只读）。

    用于读取历史快照或其他数据文件。

    Args:
        ctx: MCP 上下文对象，自动注入。
        path: 文件路径，例如 '/data/history/2023/01/...'。

    Returns:
        str: 文件内容（文本）或二进制数据提示。
    """
    api = ctx.request_context.lifespan_context.siyuan_api
    content_bytes = api.get_file_bytes(path)
    try:
        content = content_bytes.decode("utf-8")
        return mask_sensitive_data(content)
    except UnicodeDecodeError:
        return f"<Binary Data: {len(content_bytes)} bytes>"


# --- 6. Server Runner ---
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
