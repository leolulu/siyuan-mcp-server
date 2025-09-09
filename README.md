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

## 安装要求

- Python 3.10+
- 思源笔记运行在本地（默认端口 6806）
- MCP 客户端（如 Claude Code）
- uv 包管理器

## 快速开始

### 1. 安装 uv（如果还没有安装）

```bash
# Linux/Mac
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows (PowerShell)
powershell -c "irm https://astral.sh/uv/install.sh | iex"
```

### 2. 设置 API Token

```bash
# Linux/Mac
export SIYUAN_API_TOKEN=your_api_token_here

# Windows (CMD)
set SIYUAN_API_TOKEN=your_api_token_here

# Windows (PowerShell)
$env:SIYUAN_API_TOKEN="your_api_token_here"
```

### 3. 获取思源笔记 API Token

1. 打开思源笔记
2. 进入 **设置** → **关于**
3. 复制 **API Token**

### 4. 安装依赖和运行

```bash
# 进入项目目录
cd siyuan-mcp-server

# 一键安装依赖
uv sync

# 运行服务器
uv run python siyuan_mcp_server.py

# 或者安装后直接运行
uv pip install -e .
siyuan-mcp-server
```

## 项目结构

```
siyuan-mcp-server/
├── siyuan_mcp_server.py    # MCP服务器主程序
├── siyuan_client.py        # 思源笔记API客户端
├── pyproject.toml         # 项目配置（包含依赖）
└── README.md             # 说明文档
```

## Claude Code 配置

在 Claude Code 的配置文件中添加：

```json
{
  "mcpServers": {
    "siyuan": {
      "command": "uv",
      "args": ["run", "/path/to/siyuan_mcp_server.py"],
      "env": {
        "SIYUAN_API_TOKEN": "your_api_token_here"
      }
    }
  }
}
```

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

## 配置选项

### 环境变量

- `SIYUAN_API_TOKEN`: 思源笔记API令牌（必需）
- `SIYUAN_BASE_URL`: 思源笔记服务地址（可选，默认：http://127.0.0.1:6806）

## 故障排除

### 1. uv 未安装
```bash
# 检查 uv 是否安装
uv --version

# 如果未安装，按上述步骤安装
```

### 2. API Token 未设置
程序会在启动时检查 API Token，如果未设置会直接报错退出。

### 3. 依赖安装失败
```bash
# 清理缓存并重新安装
uv cache clean
uv sync
```

## 开发说明

### 项目结构

```
├── siyuan_mcp_server.py    # MCP服务器主程序
├── siyuan_client.py        # 思源笔记API客户端
├── pyproject.toml         # 项目配置文件
└── README.md             # 说明文档
```

### 扩展功能

要添加新的工具：

1. 在 `siyuan_client.py` 中添加新的API方法
2. 在 `siyuan_mcp_server.py` 中注册新工具
3. 更新工具列表和文档

## 许可证

MIT License

## 贡献

欢迎提交 Issue 和 Pull Request！

## 更新日志

### v0.1.0
- 初始版本发布
- 支持基本的笔记本和文档操作
- 实现SQL查询功能
- 添加文件系统操作
- 支持资源文件上传
- 使用 uv 包管理器
