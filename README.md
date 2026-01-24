# 思源笔记 MCP 服务器 (官方 SDK 版)

本项目提供了一个基于官方 MCP Python SDK 构建的思源笔记 MCP (Model Context Protocol) 服务器。它允许 AI Agent 通过一套标准化的工具与您的思源笔记知识库进行交互。

该服务器充当一座桥梁，将 MCP 的工具调用转换为对思源笔记 API 的请求，专注于提供强大的只读查询能力。

## 功能特性

- **基于官方 SDK 构建**: 确保了兼容性并遵循最佳实践。
- **`FastMCP` 集成**: 使用高级的 `FastMCP` 服务器，兼具简洁与强大。
- **生命周期管理**: 通过 `lifespan` 机制安全地管理 `SiyuanAPI` 客户端的生命周期。
- **装饰器驱动的工具**: 使用 `@mcp.tool()` 装饰器，工具定义清晰简洁。
- **兼具高层与底层工具**: 同时提供易于使用的高级查询工具和功能强大的底层 `execute_sql` 工具，以实现最大灵活性。
- **敏感数据自动打码**: 自动检测并打码返回内容中的敏感信息（如 API 密钥、令牌、密码等），保护用户隐私和数据安全。

## 环境要求

- **Python 3.10+**（仅开发时需要，使用 uvx 运行时无需）
- **uv**（推荐使用，用于 `uvx` 命令）
- 思源笔记桌面客户端正在运行
- 思源笔记 API Token（在思源笔记设置中获取）

### 安装 uv

如果尚未安装 uv：

```bash
# macOS/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"

# 或使用包管理器
pip install uv
```

## 安装与配置

1.  **克隆仓库:**
    ```bash
    git clone <repository-url>
    cd siyuan-mcp-server
    ```

2.  **安装依赖:**
    我们推荐使用 `uv`。
    ```bash
    uv sync
    ```


## 如何运行

### 方式一：使用 uvx（推荐，无需安装）

这是最简单的方式，无需预先安装，`uvx` 会自动从 PyPI 下载并运行。

**Claude Desktop 配置**:

```json
{
  "mcpServers": {
    "siyuan": {
      "command": "uvx",
      "args": ["siyuan-mcp-server"],
      "env": {
        "SIYUAN_API_TOKEN": "your_token_here"
      }
    }
  }
}
```

**指定版本**:

```json
{
  "mcpServers": {
    "siyuan": {
      "command": "uvx",
      "args": ["siyuan-mcp-server==0.3.0"],
      "env": {
        "SIYUAN_API_TOKEN": "your_token_here"
      }
    }
  }
}
```

**uvx 的优势**:
- ✅ 无需预先安装包
- ✅ 自动版本管理
- ✅ 隔离的临时环境
- ✅ 自动依赖管理
- ✅ 快速启动（利用 uv 的缓存）

### 方式二：本地开发运行

在开发期间，可以使用 `uv run` 直接运行本地代码：

**Claude Desktop 配置**:

```json
{
  "mcpServers": {
    "siyuan": {
      "command": "uv",
      "args": ["run", "siyuan_mcp_server"],
      "cwd": "/path/to/siyuan-mcp-server",
      "env": {
        "SIYUAN_API_TOKEN": "your_token_here"
      }
    }
  }
}
```

**说明**:
- `cwd` 指向项目根目录
- `uv run` 会使用项目的虚拟环境
- 代码修改后无需重新构建

## 已实现的工具

所有工具均在 `siyuan_mcp_server.py` 文件中定义。

-   **`find_notebooks`**: 查找并列出笔记本。
-   **`find_documents`**: 根据笔记本、标题和日期等条件查找文档。
-   **`search_blocks`**: 根据关键词、父块、块类型和日期等条件搜索内容块。
-   **`get_block_content`**: 获取指定块的完整 Markdown 内容。
-   **`get_blocks_content`**: 批量获取多个块的完整内容，比多次调用 `get_block_content` 更高效。
-   **`execute_sql`**: 直接对数据库执行只读的 `SELECT` 查询。

## 未来计划

- [ ] 添加更多高级查询工具
- [ ] 支持写入操作（创建/更新文档）
- [ ] 添加单元测试

## 安全特性

本项目内置了敏感数据保护机制，通过 `tools.py` 中的 `mask_sensitive_data` 函数实现：

- **自动检测敏感信息**: 能够识别多种格式的敏感数据，包括：
  - AWS Access Key ID 和 Secret Access Key
  - GitHub Personal Access Token
  - JWT Token
  - UUID
  - API Key
  - OAuth tokens
  - Private Key
  - 数据库连接字符串中的密码
  - Base64 编码的密钥
  - 十六进制密钥
  - 其他通用密钥格式

- **智能打码策略**: 采用中间部分打码的方式，保留字符串的开头和结尾部分，便于识别但不泄露完整信息。

- **全面保护**: 在所有返回用户数据的内容中自动应用打码处理，包括：
  - 块内容搜索结果
  - 块详细内容
  - SQL 查询结果
