# 思源笔记 MCP 服务器 (官方 SDK 版)

本项目提供了一个基于官方 MCP Python SDK 构建的思源笔记 MCP (Model Context Protocol) 服务器。它允许 AI Agent 通过一套标准化的工具与您的思源笔记知识库进行交互。

该服务器充当一座桥梁，将 MCP 的工具调用转换为对思源笔记 API 的请求，专注于提供强大的只读查询能力。

## 功能特性

- **基于官方 SDK 构建**: 确保了兼容性并遵循最佳实践。
- **`FastMCP` 集成**: 使用高级的 `FastMCP` 服务器，兼具简洁与强大。
- **生命周期管理**: 通过 `lifespan` 机制安全地管理 `SiyuanAPI` 客户端的生命周期。
- **装饰器驱动的工具**: 使用 `@mcp.tool()` 装饰器，工具定义清晰简洁。
- **兼具高层与底层工具**: 同时提供易于使用的高级查询工具和功能强大的底层 `execute_sql` 工具，以实现最大灵活性。

## 环境要求

- Python 3.8+
- 思源笔记桌面客户端正在运行
- 项目依赖 (可通过 `pyproject.toml` 安装)

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

本项目设计为通过 MCP 客户端（如 Claude Desktop）的 JSON 配置来启动。您需要在客户端的 `servers_config.json` 文件中添加以下配置：

```json
{
  "mcpServers": {
    "siyuan": {
      "command": "uv",
      "args": ["run", "siyuan-mcp-server"],
      "env": {
        "SIYUAN_API_TOKEN": "your_token_here"
      }
    }
  }
}
```

客户端将根据此配置自动启动服务器，并将 `SIYUAN_API_TOKEN` 作为环境变量传递给服务器进程。

## 已实现的工具

所有工具均在 `siyuan_mcp_server/main.py` 文件中定义。

-   **`find_notebooks`**: 查找并列出笔记本。
-   **`find_documents`**: 根据笔记本、标题和日期等条件查找文档。
-   **`search_blocks`**: 根据关键词、父块、块类型和日期等条件搜索内容块。
-   **`get_block_content`**: 获取指定块的完整 Markdown 内容。
-   **`execute_sql`**: 直接对数据库执行只读的 `SELECT` 查询。
