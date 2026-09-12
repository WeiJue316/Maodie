# CLAUDE.md

本文件为 Claude Code (claude.ai/code) 提供在此代码仓库中工作的指导。

## 项目概览

`project_class` 是一个 **Python ReAct Agent**，从单一 CLI 演进为「CLI + Web 仪表盘」双形态，能力包括：工具调用、多 Agent 协作、MCP Client、Skills 系统、双层记忆系统。

- **CLI**：`python main.py`（交互式），`python main.py --message "..."`（单条）
- **Web**：`python main.py --web --port 8000` 起后端 API，配合 `frontend/` React 仪表盘
- 一键启动：`start.bat`（同时拉起前后端并打开浏览器）

> ⚠️ **公开仓库安全约定**：本仓库目标是公开的，**禁止提交任何密钥/token/密码**。`config.yaml` 含 MCP 令牌，已 gitignore（见「配置」一节）。API Key 一律走 `.env` 或 `${ENV_VAR}` 插值。

## 运行环境

需要 **Python 3.10+**（项目实测使用 3.11.14）。本机推荐解释器：

```
D:\Anaconda\envs\py100\python.exe   # Python 3.11, conda env 名 "py100"
```

系统默认的 `D:\Anaconda\python.exe` 是 3.7.3，其 OpenSSL 无法完成对 MiniMax/MiMo API 的 TLS 握手，会报 `Connection error.`，**不要使用**。

入口脚本 `main.py` 顶部已加版本自检，低于 3.10 会直接退出并提示切换。

## 构建和测试命令

```bash
# 运行所有测试
pytest tests/ -v

# 运行单个测试文件
pytest tests/test_config.py -v

# 运行测试并生成覆盖率报告
pytest tests/ --cov=agent --cov-report=term-missing
```

前端依赖：`cd frontend && npm install`；开发时 `npx vite --host`（port 5173）。

## 启动 Web（前后端）

`start.bat` 会：杀掉 8000/5173 占用 → 起后端（main.py --web）→ 起前端（vite）→ 打开浏览器。

- 后端 API：http://localhost:8000 ，接口文档 http://localhost:8000/docs
- 前端：http://localhost:5173

## 核心架构

```
用户输入 → Session.messages (追加) → AgentLoop.run()
  → LLM.chat(messages, tools)
    → 有 tool_calls? → execute_tool() → 追加工具结果 → 再次 LLM.chat()
    → 无 tool_calls? → 返回最终回答
```

**核心文件：**
- `agent/loop.py` — ReAct 循环：调用 LLM、执行工具、管理迭代次数上限
- `agent/tools.py` — 通过 `@tool` 装饰器注册工具；`ToolContext` 持有运行时状态（work_dir、session_id）。内置工具：`read_file`、`write_file`、`list_dir`、`change_dir`、`shell`、`search_files`、`search_memory`、`spawn_agent`、`check_agent_status`
- `agent/session.py` — `SessionManager` 将会话以 JSON 持久化到 `.sessions/`。Session ID：`YYYYMMDD-HHMMSS-<6位十六进制>`
- `agent/config.py` — 加载 config.yaml，支持环境变量覆盖（AGENT_API_KEY、AGENT_BASE_URL、AGENT_MODEL、AGENT_WORK_DIR）；`${ENV_VAR}` 插值
- `agent/llm.py` — OpenAI 兼容 LLM 客户端，支持流式与非流式
- `agent/web.py` + `agent/api/` — FastAPI 后端：sessions.py / skills.py / mcp.py / memory.py / orchestrator.py / tools.py / config.py
- `main.py` — 程序入口；`--message` 单条，`--resume`/`--session` 恢复会话，`--web --port` 起 Web

**已扩展的功能模块：**
- **多 Agent 协作** — `agent/orchestrator.py`。主 Agent 用 `spawn_agent` 异步启动专业子 Agent，`depends_on` 依赖调度，`ThreadPoolExecutor` 并行，`CancellationToken` 协作取消。子 Agent 类型在 `config.yaml` 的 `agents` 段定义（system_prompt/model/tools/max_iterations）
- **MCP Client** — `agent/mcp/`（manager.py / transport.py / bridge.py / schema.py）。支持 streamable_http / sse / stdio 传输；server 列表在 `config.yaml` 的 `mcp_servers` 段
- **Skills 系统** — `agent/skills.py`。从 `agent-skills/` 目录加载技能，`select_skill` 工具按序挑选
- **记忆系统（双层）** — Observation（`agent/observation.py`，SQLite+FTS5）+ 长期记忆 MEMORY.md（`agent/memory.py`），`agent/memory_search.py` 混合检索（向量+全文）并自动晋升，`agent/extractor.py` 会话结束提取 Observation，`agent/vectordb.py` ChromaDB 向量层

### 配置优先级

YAML 默认值 → `.env` 文件 → 环境变量（最高优先级）

### 配置：config.yaml（私有，勿提交）

**`config.yaml` 是本机私有配置，已被 `.gitignore` 排除**，因为其中 `mcp_servers` 的 URL 含用户私有令牌。它不会出现在仓库里。

- 仓库内只提交**无密钥模板** `config.example.yaml`；新环境复制它为 `config.yaml` 再填写
- 任何密钥（API Key、含令牌的 MCP URL）用 `${VAR}` 写在 `.env`，config 读取时自动插值
- 需改动配置时：改 `config.example.yaml` 同步，别只改本机 config.yaml

### ToolContext

`ToolContext.work_dir` 可变 — `change_dir` 工具修改它，影响后续工具路径解析。所有工具都将其作为第二参数接收。多 Agent 场景下额外持有 `orchestrator` 与 `can_spawn_agents`，子 Agent 内硬禁止嵌套 spawn。

### 会话持久化

会话保存 `.sessions/<id>.json`，索引 `.sessions/index.json`。`AgentLoop` 原地修改 `session.messages`；`auto_save=true` 时每轮对话后自动保存。

## CLI 斜杠命令

`/help` `/exit` `/quit` `/session new|list|load|info` `/history` `/clear` `/tools` `/cd` `/config`
`/model` `/chat` `/think` `/mcp` `/skills` `/send` `/cancel`
`/memory` `/memory stats` `/memory search <q>` `/memory extract` `/memory today` `/memory day <date>`

## Web API 端点（agent/api/）

- 会话：`GET/POST /sessions`、`GET/DELETE /sessions/{id}`、`/messages`、`POST /sessions/{id}/chat`
- 技能：`GET /skills/available` `/skills/unavailable` `/{name}` `/{name}/content`
- MCP：`GET /mcp/servers` `/{name}`、`POST /mcp/servers/{name}/reconnect`、`GET /mcp/tools[/{server}]`、`GET /mcp/logs`
- 记忆：`GET/PUT /memory/long-term`、`GET /observations[/today|date/{d}|details]`、`GET/POST /memory/search`、`POST /memory/extract[/{session_id}]`
- 编排：`GET/POST /agents/tasks`、`GET /agents`、`POST /agents/tasks/{task_id}/cancel`
- 工具：`GET /tools/logs`

## 设计文档

`docs/design/`：
- `DESIGN.md` — 项目整体设计
- `mcp_design.md` — MCP Client 集成设计
- `memory-system.md` — 双层记忆系统架构
- `multi_agent_design.md` — 多 Agent 协作设计
- `frontend_design.md` — Web 前端设计

## Git / 提交约定

- 本仓库目标公开，**严禁提交密钥**（见「公开仓库安全约定」）
- `config.yaml`、`.env`、`.sessions/`、`.memory/`、`node_modules/`、`dist/` 均忽略
- 第三方技能 clone（如 `agent-skills/guizang-ppt-skill`）不纳入版本库
- commit message 用英文
- git push 仅用于跨设备同步，不自动执行，等用户明确指示