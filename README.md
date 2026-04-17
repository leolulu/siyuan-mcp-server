# 思源笔记 MCP 服务器 (官方 SDK 版)

本项目提供了一个基于官方SDK构建的思源笔记 MCP (Model Context Protocol) 服务器。它允许 AI Agent 通过一套标准化的工具与您的思源笔记知识库进行交互。

该服务器充当一座桥梁，将 MCP 的工具调用转换为对思源笔记 API 的请求，提供强大的读写能力，并内置统一的前台通知机制。

## 为什么用MCP，不用Skill

因为MCP可以控制Agent操作的权限和范围，例如可以将笔记中的敏感信息打码脱敏后返回，Agent接触不到真实的敏感信息。并且通过强制的通知机制，让Agent对笔记的所有操作透明化。

而使用Skill的话，Agent会对笔记有100%的权限，能够读取所有源内容，并且可以对笔记做任意删除操作，有较高的的风险。并且Agent对笔记的操作审计只能依赖其自省，当Agent智能不足，或出现上下文迷失时，很容易出问题。

当然想用Skill的方式操纵思源笔记也很简单，让Agent读一下`doc(read only)`目录下的API和数据结构文档，它就会明白如何使用官方的SDK对笔记进行增删查改。但总的来说我不推荐这么做，有数据隐私和安全风险。

## 功能特性

- **基于官方 SDK 构建**: 确保了兼容性并遵循最佳实践。
- **`FastMCP` 集成**: 使用高级的 `FastMCP` 服务器，兼具简洁与强大。
- **生命周期管理**: 通过 `lifespan` 机制安全地管理 `SiyuanAPI` 客户端的生命周期。
- **装饰器驱动的工具**: 使用 `@mcp.tool()` 装饰器，工具定义清晰简洁。
- **完整的读写能力**: 提供笔记本/文档/内容块的查询、创建、更新、移动等全流程操作。
- **兼具高层与底层工具**: 同时提供易于使用的高级查询工具和功能强大的底层 `execute_sql` 工具，以实现最大灵活性。
- **前台通知工具**: 提供 `push_message` 和 `push_error_message`，用于写操作的结果反馈与错误提示。
- **敏感数据自动打码**: 自动检测并打码返回内容中的敏感信息（如 API 密钥、令牌、密码等），保护用户隐私和数据安全。

## 环境要求

- **Python 3.10+**（仅开发时需要，使用 uvx 运行时无需）
- **uv**（推荐使用，用于 `uvx` 命令）
- 思源笔记桌面客户端正在运行
- 思源笔记 API Token（在思源笔记设置中获取）

### 环境变量

| 变量名 | 必填 | 默认值 | 说明 |
|--------|------|--------|------|
| `SIYUAN_API_TOKEN` | 是 | - | 思源笔记 API Token |
| `SIYUAN_API_URL` | 否 | `http://127.0.0.1:6806` | 思源笔记 API 地址，支持自定义远程地址 |

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
        "SIYUAN_API_TOKEN": "your_token_here",
        "SIYUAN_API_URL": "http://127.0.0.1:6806"
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
      "args": ["siyuan-mcp-server==0.28.0"],
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

所有工具均在 `src/siyuan_mcp_server/__init__.py` 文件中定义。

### 查询工具（只读）

-   **`find_notebooks`**: 查找并列出笔记本。
-   **`find_documents`**: 根据笔记本、标题和日期等条件查找文档。
-   **`search_blocks`**: 根据关键词、父块、块类型和日期等条件搜索内容块。
-   **`get_block_content`**: 获取指定块的完整 Markdown 内容。
-   **`get_blocks_content`**: 批量获取多个块的完整内容，比多次调用 `get_block_content` 更高效。
-   **`execute_sql`**: 直接对数据库执行只读的 `SELECT` 查询。

### 写入工具

-   **`create_document`**: 通过 Markdown 创建文档（内置成功/失败通知）。
-   **`update_block`**: 更新指定块内容（内置成功/失败通知）。
-   **`delete_block`**: 删除指定块（内置成功/失败通知）。
-   **`insert_block`**: 在指定锚点位置插入块（内置成功/失败通知）。
-   **`prepend_block`**: 插入前置子块（内置成功/失败通知）。
-   **`append_block`**: 插入后置子块（内置成功/失败通知）。
-   **`move_block`**: 移动块到指定位置（内置成功/失败通知）。默认按"逻辑块组"执行，避免父块与内容脱离（标题按分节范围，其它块按子树后代）。

### 通知工具

-   **`push_message`**: 推送前台普通消息（用于写操作结果提示）。
-   **`push_error_message`**: 推送前台错误消息（用于写操作异常提示）。

### 文件操作工具（只读）

-   **`list_files`**: 列出指定路径下的文件和文件夹。
-   **`get_file`**: 读取指定文件的内容（文本文件会进行敏感信息打码）。
-   **`get_file_base64`**: 读取指定文件内容并以 Base64 编码返回。

### 历史快照工具（只读）

-   **`list_history_entries`**: 列出历史快照目录下的文件和文件夹。
-   **`get_history_file`**: 读取历史快照文件的内容。
-   **`get_block_changes`**: 查询指定时间范围内新增或修改的内容块清单。
-   **`get_block_diffs`**: 查询指定时间范围内修改的内容块，并返回前后对比差异。


## 块移动安全规程（重要）

为避免"父块移动了但内容没跟着走"的错位问题，`move_block` 建议遵循以下规则：

- 把目标部分视为"逻辑块组"，不要只移动父块本身：
  - 标题块（h1-h6）：分节范围 = 从标题开始，直到下一个同级或更高级标题之前的所有块。
  - 其他块：子树块组 = 目标块 + 全部后代。
- 若目标是标题分节调整顺序，使用标题块作为 `block_id`。
- 每移动一个块后都应重新读取当前结构，再决定下一步锚点，避免基于过期结构连续操作。
- `allow_heading_only_move` 已废弃；传 `true` 会被拒绝，以避免部分移动。
- 若目标是"稳定挂到某个父块下"，优先使用 `append_block` / `prepend_block`，或仅传 `parent_id`。

## 删除文档注意事项（重要）

- 本 MCP Server 不提供"删除文档（文档树节点）"能力；请在思源客户端手动删除文档。
- `delete_block(block_id)` 仅用于删除非文档块；当传入文档块 ID 时会直接拒绝。

## 写入流程通知约定

所有写入操作（创建、更新、移动等）均内置了统一的通知机制：

- 操作成功时调用 **`push_message`**，向前台反馈结果。
- 操作失败时调用 **`push_error_message`**，向前台反馈错误原因。
- 建议消息中包含动作对象与结果状态（例如：`文档创建成功: xxx`、`块更新失败: 权限不足`）。
- 写入工具默认按步骤推送通知：接收请求 -> 参数校验 -> 接口调用 -> 操作完成。
- 错误通知覆盖参数校验错误、接口调用错误、处理阶段错误，确保异常可见。

## 未来计划

- [ ] 添加更多高级查询工具
- [ ] 添加更多写入操作（文件附件管理等）
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

---

## 开发规范（必读）

为保证后续开发行为一致，请在修改工具逻辑前先阅读：

- `dev doc/开发规范.md`

该规范重点约束：

- 写操作工具的通知链路必须走统一入口（不要在各 tool 内分散拼接文案）。
- 通知文案必须是用户可读表达，强调"当前环节 + 发生了什么"。
- 块操作的参数优先级、docstring 编写标准、变更验证步骤。

如果你的改动涉及写操作流程或提示文案，提交前应逐条对照该规范自检。
