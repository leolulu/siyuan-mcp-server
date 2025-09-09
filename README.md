# 思源笔记 MCP Server

这是一个为思源笔记（SiYuan）提供的 MCP (Model Context Protocol) 服务器，允许通过 MCP 协议与思源笔记进行交互。

## 功能特性

- 📚 **笔记本管理**: 列出、创建、删除、配置笔记本
- 🔍 **文档搜索**: 根据标题搜索文档，支持模糊匹配
- 📄 **文档操作**: 读取、创建、重命名、删除文档
- 🗂️ **文件系统**: 遍历目录、读取文件
- 🔧 **SQL查询**: 执行自定义SQL查询
- 📁 **资源管理**: 上传资源文件
- 🔔 **通知系统**: 推送消息和错误通知
- ℹ️ **系统信息**: 获取版本、时间等系统信息

## 使用要求

- 思源笔记运行在本地（默认端口 6806）
- 支持 MCP 协议的客户端（如 Claude Code、cline、roocode 等）
- 从思源笔记设置中获取的 API Token

## MCP 配置

在你的 MCP 客户端的配置文件中添加以下内容。请确保将 `command` 中的路径修改为 `siyuan_mcp_server.py` 文件的实际绝对路径，并将 `SIYUAN_API_TOKEN` 替换为你的思源笔记 API Token。

```json
{
  "mcpServers": {
    "siyuan": {
      "command": "uv",
      "args": ["run", "/path/to/siyuan_mcp_server.py"],
      "env": {
        "SIYUAN_API_TOKEN": "your_api_token_here",
        "SIYUAN_BASE_URL": "http://127.0.0.1:6806"
      }
    }
  }
}
```

**配置说明:**

- `command`: 启动 MCP Server 的命令。这里使用 `uv` 来运行 Python 脚本。
- `args`: 传递给 `command` 的参数。第一个参数是 `run`，第二个是 `siyuan_mcp_server.py` 的 **绝对路径**。
- `env`: 环境变量。
    - `SIYUAN_API_TOKEN`: **必需**。你的思源笔记 API Token。
    - `SIYUAN_BASE_URL`: **可选**。如果你的思源笔记运行在非默认地址，请修改此项。

### 获取思源笔记 API Token

1. 打开思源笔记
2. 进入 **设置** → **关于**
3. 复制 **API Token**

## 可用工具

### 笔记本管理
- `list_notebooks`: 列出所有笔记本
- `get_notebook_conf`: 获取笔记本配置

### 文档搜索与读取
- `search_documents_by_title`: 根据标题搜索文档
- `get_document_by_id`: 根据ID获取文档内容
- `get_document_by_path`: 根据路径获取文档
- `list_all_documents`: 列出笔记本下的所有文档

### 文档操作
- `create_document_with_markdown`: 通过Markdown创建文档

### 高级功能
- `execute_sql_query`: 执行SQL查询
- `upload_asset_file`: 上传资源文件
- `read_directory`: 读取目录内容

### 系统功能
- `get_system_info`: 获取系统信息
- `push_notification`: 推送通知消息

## 使用示例

### 搜索文档
```json
{
  "name": "search_documents_by_title",
  "arguments": {
    "title": "Python教程",
    "notebook_id": "20210817205410-2kvfpfn",
    "limit": 5
  }
}
```

### 读取文档内容
```json
{
  "name": "get_document_by_id",
  "arguments": {
    "id": "20210914223645-oj2vnx2"
  }
}
```

### 创建新文档
```json
{
  "name": "create_document_with_markdown",
  "arguments": {
    "notebook": "20210817205410-2kvfpfn",
    "path": "/新建文档",
    "markdown": "# 新文档\n\n这是一个通过MCP创建的文档。"
  }
}
```

### 列出所有文档
```json
{
  "name": "list_all_documents",
  "arguments": {
    "notebook_id": "20210817205410-2kvfpfn",
    "order_by": "updated",
    "limit": 50
  }
}
```

## 许可证

MIT License

## 贡献

欢迎提交 Issue 和 Pull Request！
