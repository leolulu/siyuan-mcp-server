"""
思源笔记API客户端
封装思源笔记的REST API接口
"""

import asyncio
import json
import logging
import os
from typing import Any, Dict, List, Optional, Union

import aiohttp

logger = logging.getLogger(__name__)


class SiyuanClient:
    """思源笔记API客户端"""
    
    def __init__(self, base_url: str = "http://127.0.0.1:6806", api_token: Optional[str] = None):
        """
        初始化客户端
        
        Args:
            base_url: 思源笔记服务地址
            api_token: API token，如果未提供则从环境变量SIYUAN_API_TOKEN获取
        """
        self.base_url = base_url.rstrip('/')
        self.api_token = api_token or os.getenv('SIYUAN_API_TOKEN')
        if not self.api_token:
            error_msg = "未提供API token，请手动提供或设置环境变量 SIYUAN_API_TOKEN"
            logger.error(error_msg)
            raise ValueError(error_msg)
        
        self.session = None
    
    async def __aenter__(self):
        """异步上下文管理器入口"""
        self.session = aiohttp.ClientSession()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器出口"""
        if self.session:
            await self.session.close()
    
    async def _request(self, endpoint: str, data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        发送HTTP请求
        
        Args:
            endpoint: API端点
            data: 请求数据
            
        Returns:
            响应数据
        """
        if not self.session:
            self.session = aiohttp.ClientSession()
        
        url = f"{self.base_url}{endpoint}"
        headers = {
            "Content-Type": "application/json",
        }
        
        if self.api_token:
            headers["Authorization"] = f"Token {self.api_token}"
        
        try:
            async with self.session.post(url, json=data, headers=headers) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    error_text = await response.text()
                    logger.error(f"请求失败: {url}, 状态码: {response.status}, 响应: {error_text}")
                    raise Exception(f"HTTP {response.status}: {error_text}")
        except aiohttp.ClientError as e:
            logger.error(f"网络请求失败: {url}, 错误: {str(e)}")
            raise Exception(f"网络请求失败: {str(e)}")
    
    async def list_notebooks(self) -> Dict[str, Any]:
        """列出所有笔记本"""
        return await self._request("/api/notebook/lsNotebooks")
    
    async def get_notebook_conf(self, notebook: str) -> Dict[str, Any]:
        """
        获取笔记本配置
        
        Args:
            notebook: 笔记本ID
        """
        return await self._request("/api/notebook/getNotebookConf", {"notebook": notebook})
    
    async def open_notebook(self, notebook: str) -> Dict[str, Any]:
        """
        打开笔记本
        
        Args:
            notebook: 笔记本ID
        """
        return await self._request("/api/notebook/openNotebook", {"notebook": notebook})
    
    async def close_notebook(self, notebook: str) -> Dict[str, Any]:
        """
        关闭笔记本
        
        Args:
            notebook: 笔记本ID
        """
        return await self._request("/api/notebook/closeNotebook", {"notebook": notebook})
    
    async def create_notebook(self, name: str) -> Dict[str, Any]:
        """
        创建笔记本
        
        Args:
            name: 笔记本名称
        """
        return await self._request("/api/notebook/createNotebook", {"name": name})
    
    async def remove_notebook(self, notebook: str) -> Dict[str, Any]:
        """
        删除笔记本
        
        Args:
            notebook: 笔记本ID
        """
        return await self._request("/api/notebook/removeNotebook", {"notebook": notebook})
    
    async def search_documents_by_title(self, title: str, notebook_id: Optional[str] = None, limit: int = 10) -> Dict[str, Any]:
        """
        根据标题搜索文档
        
        Args:
            title: 文档标题
            notebook_id: 笔记本ID（可选）
            limit: 返回结果数量限制
        """
        if notebook_id:
            stmt = f"SELECT id, content, created, updated, hpath FROM blocks WHERE type = 'doc' AND content LIKE '%{title}%' AND box = '{notebook_id}' LIMIT {limit}"
        else:
            stmt = f"SELECT id, content, created, updated, hpath FROM blocks WHERE type = 'doc' AND content LIKE '%{title}%' LIMIT {limit}"
        
        return await self.execute_sql_query(stmt)
    
    async def get_document_by_id(self, doc_id: str) -> Dict[str, Any]:
        """
        根据文档ID获取文档内容
        
        Args:
            doc_id: 文档ID
        """
        return await self._request("/api/export/exportMdContent", {"id": doc_id})
    
    async def get_document_ids_by_path(self, path: str, notebook: str) -> Dict[str, Any]:
        """
        根据人类可读路径获取文档 IDs

        Args:
            path: 文档路径
            notebook: 笔记本ID
        """
        return await self._request(
            "/api/filetree/getIDsByHPath", {"path": path, "notebook": notebook}
        )
    
    async def list_all_documents(self, notebook_id: str, order_by: str = "updated", limit: int = 100) -> Dict[str, Any]:
        """
        列出笔记本下的所有文档
        
        Args:
            notebook_id: 笔记本ID
            order_by: 排序字段
            limit: 返回结果数量限制
        """
        stmt = f"SELECT id, content, created, updated, hpath FROM blocks WHERE type = 'doc' AND box = '{notebook_id}' ORDER BY {order_by} DESC LIMIT {limit}"
        return await self.execute_sql_query(stmt)
    
    async def execute_sql_query(self, stmt: str) -> Dict[str, Any]:
        """
        执行SQL查询
        
        Args:
            stmt: SQL语句
        """
        return await self._request("/api/query/sql", {"stmt": stmt})
    
    async def create_document_with_markdown(self, notebook: str, path: str, markdown: str = "") -> Dict[str, Any]:
        """
        通过Markdown创建文档
        
        Args:
            notebook: 笔记本ID
            path: 文档路径
            markdown: Markdown内容
        """
        return await self._request("/api/filetree/createDocWithMd", {
            "notebook": notebook,
            "path": path,
            "markdown": markdown
        })
    
    async def rename_document(self, notebook: str, path: str, title: str) -> Dict[str, Any]:
        """
        重命名文档
        
        Args:
            notebook: 笔记本ID
            path: 文档路径
            title: 新标题
        """
        return await self._request("/api/filetree/renameDoc", {
            "notebook": notebook,
            "path": path,
            "title": title
        })
    
    async def remove_document(self, notebook: str, path: str) -> Dict[str, Any]:
        """
        删除文档
        
        Args:
            notebook: 笔记本ID
            path: 文档路径
        """
        return await self._request("/api/filetree/removeDoc", {
            "notebook": notebook,
            "path": path
        })
    
    async def upload_asset_file(self, file_path: str, assets_dir_path: str = "/assets/") -> Dict[str, Any]:
        """
        上传资源文件
        
        Args:
            file_path: 本地文件路径
            assets_dir_path: 资源文件存放路径
        """
        if not os.path.exists(file_path):
            raise Exception(f"文件不存在: {file_path}")
        
        if not self.session:
            self.session = aiohttp.ClientSession()
        
        url = f"{self.base_url}/api/asset/upload"
        headers = {}
        
        if self.api_token:
            headers["Authorization"] = f"Token {self.api_token}"
        
        # 准备multipart表单数据
        data = aiohttp.FormData()
        data.add_field('assetsDirPath', assets_dir_path)
        
        with open(file_path, 'rb') as f:
            data.add_field('file[]', f, filename=os.path.basename(file_path))
            
            async with self.session.post(url, data=data, headers=headers) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    error_text = await response.text()
                    raise Exception(f"HTTP {response.status}: {error_text}")
    
    async def get_system_info(self, info_type: str = "version") -> Dict[str, Any]:
        """
        获取系统信息
        
        Args:
            info_type: 信息类型 (version, current_time, boot_progress)
        """
        endpoints = {
            "version": "/api/system/version",
            "current_time": "/api/system/currentTime",
            "boot_progress": "/api/system/bootProgress"
        }
        
        endpoint = endpoints.get(info_type, "/api/system/version")
        return await self._request(endpoint)
    
    async def read_directory(self, path: str) -> Dict[str, Any]:
        """
        读取目录内容
        
        Args:
            path: 目录路径
        """
        return await self._request("/api/file/readDir", {"path": path})
    
    async def get_file(self, path: str) -> bytes:
        """
        获取文件内容
        
        Args:
            path: 文件路径
        """
        if not self.session:
            self.session = aiohttp.ClientSession()
        
        url = f"{self.base_url}/api/file/getFile"
        headers = {}
        
        if self.api_token:
            headers["Authorization"] = f"Token {self.api_token}"
        
        params = {"path": path}
        
        async with self.session.get(url, headers=headers, params=params) as response:
            if response.status == 200:
                return await response.read()
            else:
                error_text = await response.text()
                raise Exception(f"HTTP {response.status}: {error_text}")
    
    async def push_notification(self, message: str, timeout: int = 7000) -> Dict[str, Any]:
        """
        推送通知消息
        
        Args:
            message: 消息内容
            timeout: 显示时间（毫秒）
        """
        return await self._request("/api/notification/pushMsg", {
            "msg": message,
            "timeout": timeout
        })
    
    async def push_error_message(self, message: str, timeout: int = 7000) -> Dict[str, Any]:
        """
        推送错误消息
        
        Args:
            message: 错误消息
            timeout: 显示时间（毫秒）
        """
        return await self._request("/api/notification/pushErrMsg", {
            "msg": message,
            "timeout": timeout
        })
    
    async def flush_transaction(self) -> Dict[str, Any]:
        """提交事务"""
        return await self._request("/api/sqlite/flushTransaction")
    
    async def close(self):
        """关闭客户端"""
        if self.session:
            await self.session.close()