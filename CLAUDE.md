# CLAUDE.md

本文件为 Claude Code (claude.ai/code) 提供在此代码仓库中工作的指导。

## 运行环境

需要 **Python 3.10+**（项目实测使用 3.11.14）。本机推荐解释器：

```
D:\Anaconda\envs\py100\python.exe   # Python 3.11, conda env 名 "py100"
```

系统默认的 `D:\Anaconda\python.exe` 是 3.7.3，其 OpenSSL 1.1.1c 无法完成对 MiniMax API 的 TLS 握手，会报 `[错误] Agent 出错：Connection error.`，**不要使用**。

入口脚本 `main.py` 顶部已加版本自检，低于 3.10 会直接退出并提示切换。

## 构建和测试命令

```bash
# 运行所有测试
pytest tests/ -v

# 运行单个测试文件
pytest tests/test_tools.py -v

# 运行测试并生成覆盖率报告
pytest tests/ --cov=agent --cov-report=term-missing
```

## 架构

这是一个 Python ReAct Agent CLI，集成了会话持久化和 OpenAI Function Calling 工具调用。

### 核心流程

```
用户输入 → Session.messages (追加) → AgentLoop.run()
  → LLM.chat(messages, tools)
    → 有 tool_calls? → execute_tool() → 追加工具结果 → 再次 LLM.chat()
    → 无 tool_calls? → 返回最终回答
```

**核心文件：**
- `agent/loop.py` — ReAct 循环：调用 LLM、执行工具、管理迭代次数上限
- `agent/tools.py` — 通过 `@tool` 装饰器注册工具；`ToolContext` 持有运行时状态（work_dir、session_id）。内置工具：`read_file`、`write_file`、`list_dir`、`change_dir`、`shell`、`search_files`、`search_memory`
- `agent/session.py` — `SessionManager` 将会话以 JSON 格式持久化到 `.sessions/`。Session ID 格式：`YYYYMMDD-HHMMSS-<6位十六进制>`
- `agent/config.py` — 加载 config.yaml，支持环境变量覆盖（AGENT_API_KEY、AGENT_BASE_URL、AGENT_MODEL、AGENT_WORK_DIR）
- `agent/llm.py` — OpenAI 兼容的 LLM 客户端，支持流式和非流式模式
- `agent/memory.py` — 长期记忆管理（MEMORY.md 读写）
- `agent/observation.py` — Observation 结构化记忆存储（SQLite + FTS5）
- `agent/vectordb.py` — ChromaDB 向量检索层（可选，依赖 chromadb + fastembed）
- `agent/memory_search.py` — 混合检索编排（向量 + FTS5）+ relevance 追踪 + 自动晋升
- `agent/extractor.py` — LLM 驱动的 Observation 提取器（Session 结束时触发）
- `main.py` — 程序入口；`--message` 单条消息模式，`--resume`/`--session` 恢复会话

### 配置优先级

YAML 默认值 → `.env` 文件 → 环境变量（最高优先级）

### ToolContext

`ToolContext.work_dir` 是可变的 — `change_dir` 工具会修改它，影响后续工具的路径解析。所有工具都将其作为第二个参数接收。

### 会话持久化

会话保存为 `.sessions/<id>.json`，索引保存在 `.sessions/index.json`。`AgentLoop` 会原地修改 `session.messages`；如果 `auto_save=true`，每轮对话后都会调用 `SessionManager.save_session()`。

### CLI 斜杠命令

`/help`、`/exit`、`/quit`、`/session new|list|load|info`、`/history`、`/clear`、`/tools`、`/cd`、`/config`
`/memory`、`/memory stats`、`/memory search <q>`、`/memory extract`、`/memory today`、`/memory day <date>`

### 设计文档

所有设计文档统一存放在 `docs/design/` 目录：
- `docs/design/DESIGN.md` — 项目整体设计文档
- `docs/design/mcp_design.md` — MCP Client 集成设计
