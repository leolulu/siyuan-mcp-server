#!/usr/bin/env python3
"""
思源笔记 MCP Server
提供思源笔记API的MCP工具接口
"""

import asyncio
import json
import logging
import sys
from typing import Any, Dict, List, Optional, Union
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import (
    CallToolRequest,
    CallToolResult,
    ListToolsRequest,
    TextContent,
    Tool,
)
from siyuan_client import SiyuanClient

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 创建MCP服务器实例
server = Server("siyuan-notes-mcp")

# 思源笔记客户端实例
siyuan_client = None


async def initialize_siyuan_client():
    """初始化思源笔记客户端"""
    global siyuan_client
    if siyuan_client is None:
        siyuan_client = SiyuanClient()
    return siyuan_client


@server.list_tools()
async def list_tools() -> List[Tool]:
    """返回可用工具列表"""
    return [
        Tool(
            name="list_notebooks",
            description="列出所有笔记本",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": [],
            },
        ),
        Tool(
            name="get_notebook_conf",
            description="获取笔记本配置",
            inputSchema={
                "type": "object",
                "properties": {
                    "notebook": {
                        "type": "string",
                        "description": "笔记本ID",
                    }
                },
                "required": ["notebook"],
            },
        ),
        Tool(
            name="search_documents_by_title",
            description="根据标题搜索文档",
            inputSchema={
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "文档标题（支持模糊匹配）",
                    },
                    "notebook_id": {
                        "type": "string",
                        "description": "笔记本ID（可选，用于限制搜索范围）",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "返回结果数量限制（默认10）",
                        "default": 10,
                    },
                },
                "required": ["title"],
            },
        ),
        Tool(
            name="get_document_by_id",
            description="根据文档ID获取文档内容",
            inputSchema={
                "type": "object",
                "properties": {
                    "id": {
                        "type": "string",
                        "description": "文档ID",
                    }
                },
                "required": ["id"],
            },
        ),
        Tool(
            name="get_document_by_path",
            description="根据人类可读路径获取文档",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "文档路径（如：/foo/bar）",
                    },
                    "notebook": {
                        "type": "string",
                        "description": "笔记本ID",
                    },
                },
                "required": ["path", "notebook"],
            },
        ),
        Tool(
            name="list_all_documents",
            description="列出笔记本下的所有文档",
            inputSchema={
                "type": "object",
                "properties": {
                    "notebook_id": {
                        "type": "string",
                        "description": "笔记本ID",
                    },
                    "order_by": {
                        "type": "string",
                        "description": "排序字段（created, updated）",
                        "default": "updated",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "返回结果数量限制（默认100）",
                        "default": 100,
                    },
                },
                "required": ["notebook_id"],
            },
        ),
        Tool(
            name="execute_sql_query",
            description="执行SQL查询",
            inputSchema={
                "type": "object",
                "properties": {
                    "stmt": {
                        "type": "string",
                        "description": "SQL查询语句",
                    },
                },
                "required": ["stmt"],
            },
        ),
        Tool(
            name="create_document_with_markdown",
            description="通过Markdown创建文档",
            inputSchema={
                "type": "object",
                "properties": {
                    "notebook": {
                        "type": "string",
                        "description": "笔记本ID",
                    },
                    "path": {
                        "type": "string",
                        "description": "文档路径（如：/foo/bar）",
                    },
                    "markdown": {
                        "type": "string",
                        "description": "Markdown内容",
                    },
                },
                "required": ["notebook", "path"],
            },
        ),
        Tool(
            name="upload_asset_file",
            description="上传资源文件",
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "本地文件路径",
                    },
                    "assets_dir_path": {
                        "type": "string",
                        "description": "资源文件存放路径（默认：/assets/）",
                        "default": "/assets/",
                    },
                },
                "required": ["file_path"],
            },
        ),
        Tool(
            name="get_system_info",
            description="获取系统信息",
            inputSchema={
                "type": "object",
                "properties": {
                    "info_type": {
                        "type": "string",
                        "description": "信息类型（version, current_time, boot_progress）",
                        "default": "version",
                    },
                },
                "required": [],
            },
        ),
        Tool(
            name="read_directory",
            description="读取目录内容",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "目录路径",
                    },
                },
                "required": ["path"],
            },
        ),
        Tool(
            name="push_notification",
            description="推送通知消息",
            inputSchema={
                "type": "object",
                "properties": {
                    "message": {
                        "type": "string",
                        "description": "消息内容",
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "显示时间（毫秒，默认7000）",
                        "default": 7000,
                    },
                },
                "required": ["message"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: Dict[str, Any]) -> CallToolResult:
    """调用工具"""
    client = await initialize_siyuan_client()
    
    try:
        if name == "list_notebooks":
            result = await client.list_notebooks()
            return CallToolResult(
                content=[TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]
            )
        
        elif name == "get_notebook_conf":
            result = await client.get_notebook_conf(arguments["notebook"])
            return CallToolResult(
                content=[TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]
            )
        
        elif name == "search_documents_by_title":
            result = await client.search_documents_by_title(
                title=arguments["title"],
                notebook_id=arguments.get("notebook_id"),
                limit=arguments.get("limit", 10)
            )
            return CallToolResult(
                content=[TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]
            )
        
        elif name == "get_document_by_id":
            result = await client.get_document_by_id(arguments["id"])
            return CallToolResult(
                content=[TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]
            )
        
        elif name == "get_document_by_path":
            result = await client.get_document_by_path(
                path=arguments["path"],
                notebook=arguments["notebook"]
            )
            return CallToolResult(
                content=[TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]
            )
        
        elif name == "list_all_documents":
            result = await client.list_all_documents(
                notebook_id=arguments["notebook_id"],
                order_by=arguments.get("order_by", "updated"),
                limit=arguments.get("limit", 100)
            )
            return CallToolResult(
                content=[TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]
            )
        
        elif name == "execute_sql_query":
            result = await client.execute_sql_query(arguments["stmt"])
            return CallToolResult(
                content=[TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]
            )
        
        elif name == "create_document_with_markdown":
            result = await client.create_document_with_markdown(
                notebook=arguments["notebook"],
                path=arguments["path"],
                markdown=arguments.get("markdown", "")
            )
            return CallToolResult(
                content=[TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]
            )
        
        elif name == "upload_asset_file":
            result = await client.upload_asset_file(
                file_path=arguments["file_path"],
                assets_dir_path=arguments.get("assets_dir_path", "/assets/")
            )
            return CallToolResult(
                content=[TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]
            )
        
        elif name == "get_system_info":
            result = await client.get_system_info(arguments.get("info_type", "version"))
            return CallToolResult(
                content=[TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]
            )
        
        elif name == "read_directory":
            result = await client.read_directory(arguments["path"])
            return CallToolResult(
                content=[TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]
            )
        
        elif name == "push_notification":
            result = await client.push_notification(
                message=arguments["message"],
                timeout=arguments.get("timeout", 7000)
            )
            return CallToolResult(
                content=[TextContent(type="text", text=json.dumps(result, ensure_ascii=False, indent=2))]
            )
        
        else:
            return CallToolResult(
                content=[TextContent(type="text", text=f"未知工具: {name}")]
            )
    
    except Exception as e:
        logger.error(f"工具调用失败: {name}, 参数: {arguments}, 错误: {str(e)}")
        return CallToolResult(
            content=[TextContent(type="text", text=f"错误: {str(e)}")]
        )


async def main():
    """主函数"""
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


if __name__ == "__main__":
    asyncio.run(main())