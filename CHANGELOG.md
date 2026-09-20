# Changelog

## [0.5.9] - 2026-09-13

### Fixed
- **Web 设置保存后重启即丢失 / 切页面回退默认**：此前 `/api/config` PUT 只改内存（`# TODO: 保存配置到文件`），后端一重启（start.bat 重跑等）就打回 config.yaml 默认值（如 provider=mimo），用户以为保存了却消失。
  - `agent/config.py`：新增 `save_config()` 与 `_apply_runtime_overlay()`，把 Web 可编辑字段持久化到**独立 `.runtime_config.yaml`**（gitignored，本地私有），不改动私有 `config.yaml`（其 mcp URL 令牌与 api key 占位保持原样）；`load_config()` 在环境变量覆盖后叠加运行时文件，优先级最高。
  - `agent/api/config.py`：PUT 改为落盘。全局 api key 仅当本次显式传入才写入，避免固化 `AGENT_API_KEY` 等环境来源的 key。api key 与整份运行时文件只落本地、不入库。
  - 验证：PUT 保存 → 生成 `.runtime_config.yaml` → 重启后端 → GET 仍返回已保存的 provider/model；GET 依旧不回传任何 key。

## [0.5.8] - 2026-09-13

### Added
- **支持为「添加的模型」单独配置 API Key**（打通前端输入 → 后端存储 → 运行时生效）。
  - 背景：此前运行链路只用全局 `config.llm.api_key`，即便 config.yaml 里每个 `ModelPreset` 带 `api_key`，请求也从不消费它；因此前端设置页不加 key 框是「加了也不生效」的装饰。
  - `agent/config.py`：新增 `active_llm_config()`，按当前选中的 model 在预置列表定位，把该预置的 `base_url` / `api_key` / `provider` 合并进拷贝；未命中回落到全局值。密钥只存在于服务端内存，不跨前端往返。
  - `agent/api/sessions.py`：两处聊天接口（流式 + 非流式）改为 `LLMClient(active_llm_config(config))`，切换模型/provider 后该模型自己的 key/端点生效。
  - `agent/api/config.py`：PUT `/api/config` 接受 `llm.api_key`（覆盖全局 key）与每个模型项的 `api_key`（**仅当携带非空值才更新，否则按 name 保留已有 key**）；GET 依旧剥掉所有 `api_key`，密钥永不回传前端。
  - `frontend/src/features/settings/SettingsPage.tsx`：「添加新模型」表单新增 **API Key（password，仅写不回显）** 输入；填了 key 时同时设为当前生效 key。Provider 下拉由写死的 4 项改为动态：内置 4 个 + 各预置中出现过的自定义 provider 自动并入，添加模型后 Provider 字段也切到该模型归属的 provider。`frontend/src/types/` 给 `llm.models` 补可选 `api_key` 字段。

## [0.5.7] - 2026-09-13

### Changed
- **导航改为底部居中的 Mac 风格 Dock**（React Bits Dock）。
  - `frontend/src/components/dock/Dock.tsx` + `Dock.css`：集成 React Bits 的 `Dock`（基于已装的 `framer-motion`，未新增依赖），鼠标靠近时图标按距离弹性放大、悬停显示标签，激活项以蓝边框/蓝图标高亮。
  - `frontend/src/layouts/MainLayout.tsx`：移除左侧竖向导航栏，改为底部正中的 Dock 承载 会话/记忆/工具/技能/MCP/编排器/设置；左上角品牌区「Project Agent」与页面标题保留在顶部栏。点击仍复用 `navigate` + `setActiveModule` 切换路由。
  - Dock 样式适配深色主题（半透明磨砂底 + 细边框），并沿用全屏 ClickSpark 点击火花。

## [0.5.6] - 2026-09-13

### Added
- **会话页流式输出改为「解密」动画呈现（React Bits DecryptedText）**。
  - `frontend/src/components/effects/DecryptedText.tsx`：集成 React Bits 的 `DecryptedText`（基于已装的 `framer-motion`，未新增依赖），文本先以随机字符掩盖再逐字解密展开，支持 `animateOn="view"` / 顺序/中心两种揭示方向。
  - `frontend/src/features/session/SessionPage.tsx`：回复期间气泡只显示「思考中」动画，不再逐 token 实时写入；整段收完后一次性填回并标记为解密对象，以 `animateOn="view"` 在滚动可视区间淡入解密。`speed` 随回复长度动态计算（约 5ms/字符，总时长 0.5s~2s），短回复轻快、长回复从容。已落库的历史回复渲染为普通文本，仅本轮新生成的回复触发动画。

## [0.5.5] - 2026-09-12

### Added
- **设置页 LLM 配置：模型下拉 + 添加/删除模型 + 切换 Provider 自动带出默认**。
  - `agent/api/config.py`：`/api/config` GET 返回 `llm.models` 预置列表（**永不回传 `api_key`**，密钥一线不落地）；PUT 接受 `models` 并按 `name` 保留已有 api_key（往返不清空密钥）。
  - `frontend/src/features/settings/SettingsPage.tsx`：「模型」由文本框改为**下拉**（已注册预置 + Provider 建议 + 当前模型），原生下拉经 `color-scheme:dark` 与 `<option>` 深底浅字保证可读；提供「＋ 添加新模型」（Provider 与模型之间，空白优先不预填）和「删除当前模型」；切换 Provider 时自动把模型/Base URL 填为该 Provider 默认（优先已注册预置）。
  - Provider 下拉移除与「添加新模型」功能重叠的 `custom` UI 选项（后端仍支持 config.yaml 里 `provider: custom`）。

## [0.5.4] - 2026-09-12

### Fixed
- **前端会话切换串页 + 历史会话被挤走**：`SessionPage` 中流式对话的回填与切换异步加载未做会话归属校验，在发送过程中切到别的会话会把上一个会话的 token/消息串进当前页；且每次发送后 `fetchSessions` 按 `updated_at` 重排侧栏，把选中的历史会话顶走。
  - `frontend/src/features/session/SessionPage.tsx`：用 `activeSessionRef` 记录当前会话，切换时立即清空旧消息、丢弃乱序/越界 token；`loadMessages` 仅在仍停留该会话时才应用。
  - `frontend/src/store/sessionSlice.ts`：`fetchSessions.fulfilled` 改为**按原顺序合并**现有会话（仅新增置顶），不再整表重排，选中会话因此保持固定。
- **会话页输入框不贴底、消息区无法上下滚动**：flex 子项默认 `min-height:auto`，长对话时节缩容器拒绝收缩，内容溢出被外层 `overflow:hidden` 裁剪，导致输入框被顶出可视区、Radix 滚动不生效。修复：在 `SessionPage.tsx` 的根容器、侧栏列、两个 `ScrollArea` 及聊天列补 `min-h-0`，让滚动容器能被压缩并真正滚动，输入框回到最下方固定。聊天历史区由 Radix `ScrollArea` 改为**原生 `overflow-y-auto`** 滚动容器，右侧必然出现可拖动滚动条。
- **会话列表不显示空会话**：`agent/api/sessions.py` 的列表接口为每条附上 `message_count`（加载对应会话统计）；`frontend/src/store/sessionSlice.ts` 过滤掉没有任何对话的空会话（刚新建且正在选中的空会话仍保留可见），侧栏只列出有真实内容的会话。

## [0.5.3] - 2026-09-12

### Fixed
- **Web 前端 4 个页面加载空白**：后端基础路由（`/api/sessions`、`/api/skills`、`/api/config`）注册为带尾斜杠路径，前端 `api.ts` 却用不带斜杠调用，导致 404。修复：`frontend/src/services/api.ts` 改用规范路径（`/sessions/`、`/skills/`、`/config/`）。波及页面：会话列表/新建、技能库、设置。

## [0.5.2] - 2026-06-10

### Fixed
- 对话后按 Ctrl+D 不退出：`_handle_message` 中的 `except Exception` 吞掉了 `EOFError`，导致 Ctrl+D 被当作普通错误处理而非退出信号。现在 `EOFError` 和 `KeyboardInterrupt` 会正确传播到外层 `run()` 的对应 handler
- 退出时"再见！"不打印：`_on_session_end()` 抛异常时会阻断后续的退出提示。现在用 try-except 保护，确保退出消息始终显示

## [0.5.1] - 2026-06-10

### Changed
- **启动优化**：Embedding 模型（`BAAI/bge-small-zh-v1.5`）从启动时加载改为延迟加载，首次语义搜索时才加载权重。启动时间从 ~15s 降至 <0.5s
- **Embedding 引擎切换**：`sentence-transformers`（PyTorch，~2GB）→ `fastembed`（ONNX Runtime，~300MB），同一模型推理速度更快、依赖更轻。首次加载从缓存读取仅 0.13s

### Fixed
- ChromaDB 1.5.9 与 fastembed 兼容性：`embed_query` 接口适配（ChromaDB 传入 `list` 非 `str`，期望返回 `list[ndarray]` 非 `ndarray`），修复 `search_memory` 工具调用时报 `TextEncodeInput must be Union[...]` 错误

## [0.5.0] - 2026-06-09

### Added
- **多 Agent 协作系统**（主控编排模式）：
  - `agent/orchestrator.py`：编排器模块，管理子 Agent 任务生命周期（创建、执行、状态查询、超时、取消、清理）
  - `spawn_agent` 工具：主 Agent 启动专业子 Agent 处理指定任务，异步返回 task_id，支持 `depends_on` 依赖声明
  - `check_agent_status` 工具：查询子 Agent 执行状态，返回结构化 JSON（status/result/summary/error）
  - `config.yaml` 新增 `agents` 字段：定义专业 Agent（system_prompt/model/tools/max_iterations），未填字段继承主配置
  - `config.yaml` 新增 `orchestrator` 字段：编排器配置（enabled/task_timeout/max_concurrent_tasks/max_result_chars/task_retention_seconds）
  - System prompt 自动注入可用 Agent 列表和使用指引，主 Agent 按需 spawn
  - 子 Agent 通过 `ThreadPoolExecutor` 并行执行，`max_concurrent_tasks` 限制并发数
  - `CancellationToken` 协作式取消：Orchestrator 设置标志，AgentLoop 每轮迭代检查
  - `ToolContext` 新增 `orchestrator` 和 `can_spawn_agents` 字段，工具层硬禁止子 Agent 嵌套 spawn
  - 依赖调度：`depends_on` 声明上游 task_id，上游完成后自动调度下游；上游失败时下游自动标记 `dependency_failed`
  - 终态清理：watchdog 基于 `last_accessed_at` 清理过期终态 task，`check_status` 刷新访问时间
  - CLI 多 Agent 状态展示：`spawn_agent` 和 `check_agent_status` 的 tool call/result 回调显示 agent 状态图标
  - 设计文档 `docs/design/multi_agent_design.md`
- **Embedding 模型切换**：`all-MiniLM-L6-v2`（384 维，英文为主）→ `BAAI/bge-small-zh-v1.5`（568 维，中文优化），中文语义搜索效果显著提升
- `ChromaEmbeddingFunction` 新增 `name()`、`embed_query()`、`embed_documents()` 方法，兼容 ChromaDB 新版 EmbeddingFunction 接口
- `.env` 新增 `HF_ENDPOINT=https://hf-mirror.com`，解决国内 HuggingFace 模型下载超时问题

## [0.4.1] - 2026-06-06

### Added
- 斜杠命令 Tab 补全（内联提示 + 下拉菜单）：
  - 输入 `/` 开头命令时实时显示内联灰色后缀提示
  - 候选 >= 2 个时在输入行下方显示竖排菜单，`>` 前缀 + 粗体青色标记当前选中项
  - 上下箭头键移动菜单高亮，内联提示同步切换
  - Tab 键确认选中项填入输入行，菜单消失
  - 候选 = 1 个时只显示内联提示（无菜单），= 0 个时无提示
  - 光标不在行尾时不显示菜单和提示
  - 其他按键（输入/退格/方向键）清除菜单并重新计算
  - `SLASH_COMMANDS` 提升为模块级常量，补全和 readline completer 共用单一数据源
  - 补全列表新增 `/skills`、`/skills reload`、`/think`、`/cd` 命令

### Fixed
- 斜杠命令补全 hint 只显示后缀而非完整命令（`/m` 提示 `odel` 不是 `/model`）
- 删除全部字符后补全菜单正确消失
- banner 底部边框不再被补全菜单遮挡（加空行缓冲）
- IME 中文输入法时内联 hint 与组合窗口位置重叠（接受遮盖，确认选字后恢复）

## [0.4.0] - 2026-06-04

### Added
- Skill `tools` 字段：frontmatter 声明依赖工具，`discover()` 时校验工具是否存在，过滤不存在的并记录到 `unavailable_tools`
- **运行时门控**：`metadata` 字段支持 `os`/`requires.bins`/`requires.anyBins`/`requires.env` 约束，`discover()` 时自动检查，不满足条件的 skill 被跳过
- **预算控制**：`format_skills_catalog()` 三级降级（完整→精简→截断），`SkillsConfig` 新增 `max_skills_in_prompt`（默认 50）和 `max_prompt_chars`（默认 10000）
- `format_skills_catalog()` 方法：生成 XML 格式的 skill 目录，注入 system prompt
- `Skill.file_path` 字段：存储 SKILL.md 的实际文件路径
- `Skill.metadata` 字段：存储解析后的 metadata 结构化数据
- `_parse_metadata()` 函数：解析 JSON/YAML 格式的 metadata
- `_check_runtime_eligibility()` 函数：检查 OS、二进制、环境变量约束
- 重写 `self-improving-agent` skill：去掉 OpenClaw/ClawdHub 等不存在的引用，适配本项目工具集

### Changed
- **Skill 加载模型从 Push 改为 Pull**：system prompt 注入 XML 目录（name + description + tools + path），LLM 按需用 `read_file` 加载 skill 内容，不再一次性注入全文
- `select_skill` 工具改为返回文件路径 + 工具白名单，不再返回全文内容
- `get_skill_summaries()` 摘要包含工具信息
- 所有 skill 文件新增 `tools` 字段声明依赖工具
- 删除 `update_select_skill_description()` 函数及所有调用点（目录已由 system prompt 注入）
- 用户生成内容从 `docs/` 移至 `examples/`，`docs/` 仅保留项目设计文档
- `docs/memory-system.md` 移入 `docs/design/`

### Removed
- `$null`：PowerShell 错误输出垃圾文件
- `test2.xlsx`：测试产物
- `ReAct_agent_loop_tool_schema.py`：早期 LangChain 参考实现，已被 `agent/loop.py` 取代
- `skills-lock.json`：跟踪 `.agents/skills/` 的 hash 文件
- `.agents/skills/`：mattpocock skill 原始安装目录，已迁移至全局配置
- `项目/.claude/skills/`：断链符号链接，已清理

### Migrated
- Claude Code skill（mattpocock/skills）从项目目录迁移至全局配置 `C:\Users\31238\.claude\skills\`，28 个 skill 全部可用，所有项目共享

## [0.3.4] - 2026-06-03

### Added
- `install_skill` 内置工具：从 URL 安装 Skill，Python `urllib` 原生下载，自动跟随重定向，下载后自动 discover + 更新工具描述
- Skill 系统 discover 跳过 `examples/`、`templates/` 子目录，避免模板 skill 污染工具摘要

### Changed
- `get_skill_summaries()` 描述超过 100 字符自动截断，多行合并为单行；工具描述 token 开销从 ~3400 降至 ~234

### Fixed
- Shell 工具 Windows GBK 编码崩溃：显式指定 `encoding="utf-8", errors="replace"`，解决 `curl` 输出 UTF-8 内容时 `UnicodeDecodeError`

## [0.3.3] - 2026-06-03

### Changed
- MCP 启动优化：后台连接 + schema 缓存，启动不再阻塞
  - 首次连接后将工具 schema 缓存到 `.memory/mcp_tools.json`
  - 后续启动从缓存加载（~18ms），后台线程完成真实连接（~7s）
  - 未连接时调用 MCP 工具返回"正在连接中，请稍后重试"
- MCP 后台连接消息改为 `pending_messages` 队列，在 REPL 读取输入前统一显示，不再打断用户输入

### Fixed
- `streamable_http_client()` 不接受 `headers` 参数：改为通过 `httpx.AsyncClient(headers=headers)` 作为 `http_client` 传入
- MCP 缓存加载时 `_register_mcp_tools` 使用 `schemas_override` 绕过 `get_all_tools()` 的 `connected` 检查
- 进程退出卡死：移除 atexit 清理（MCP SDK 连接关闭可能阻塞），daemon 线程由操作系统回收
- `_read_line` 双重 prompt：`_read_line_win()` 和 `_read_line_unix()` 不再重复写 prompt

## [0.3.2] - 2026-06-03

### Fixed
- `/model` 切换模型后重启恢复为旧模型：`.env` 中的 `AGENT_MODEL`/`AGENT_BASE_URL`/`AGENT_API_KEY` 环境变量优先级高于 `config.yaml`，切换时未同步更新导致重启后被覆盖。现在 `/model` 切换后同时写回 `config.yaml` 和 `.env`

## [0.3.1] - 2026-06-03

### Added
- 斜杠命令 Tab 滚动补全：
  - 输入 `/` 开头的命令后按 Tab，输入行内联切换为第一个匹配命令
  - 多个候选时连续按 Tab 循环滚动，右侧显示 `[1/3]` 计数器
  - 只有一个匹配时直接补全，无计数器
  - 光标不在行尾时 Tab 无效果，避免干扰中间编辑
  - 其他按键（输入/退格/方向键）重置补全状态
  - `SLASH_COMMANDS` 提升为模块级常量，inline hint 和 readline completer 共用单一数据源
  - 补全列表同步新增 `/skills`、`/skills reload`、`/think`、`/cd` 命令

## [0.3.0] - 2026-06-02

### Added
- MCP Client 集成（`agent/mcp/`）：
  - `AsyncBridge`：后台 event loop 线程，将 MCP async 调用包装为同步
  - `MCPManager`：管理所有 MCP Server 连接生命周期（连接/重连/断开/工具调用）
  - 支持三种传输协议：stdio（本地进程）、sse（HTTP SSE）、streamable_http（推荐远程）
  - MCP 工具自动注册到 `TOOL_REGISTRY`，命名格式 `server__tool`（双下划线前缀）
  - 启动时并行连接所有 MCP Server，失败跳过不阻塞
  - 工具调用断连自动重连一次，超时可按 server 配置
  - MCP `call_tool` 返回值自动转为字符串，经过 `_truncate_output()` 截断
- `MCPServerConfig` 数据类：name、transport、command/args/env/cwd（stdio）、url/headers（HTTP）、timeout、include/exclude
- `config.yaml` 新增 `mcp_servers` 列表配置，支持 `${VAR}` 环境变量插值
- 配置校验：name 非空不重复、transport 合法值、stdio 必须有 command、HTTP 必须有 url、timeout > 0、正则合法性
- `/mcp` CLI 命令：查看所有 MCP Server 连接状态和工具列表
- `/mcp tools` 子命令：列出所有 MCP 工具全名
- `/tools` 命令新增类型列，区分内置工具和 MCP 工具
- `ToolContext` 新增 `mcp_manager` 字段
- `get_openai_schemas()` 自动包含 `TOOL_REGISTRY` 中名称含 `__` 的工具（MCP 工具）
- `mcp>=1.0.0` 可选依赖，未安装时 MCP 功能跳过并打印警告
- `atexit` 清理：程序退出时优雅关闭所有 MCP session
- 设计文档 `docs/design/mcp_design.md`
- `tests/test_mcp.py` 测试文件

### Fixed
- `streamable_http_client()` 不接受 `headers` 参数：改为通过 `httpx.AsyncClient(headers=headers)` 作为 `http_client` 传入

## [0.2.4] - 2026-05-19

### Added
- 长期记忆系统（`agent/memory.py`）：
  - `MemoryManager` 类：基于 `MEMORY.md` 文件的长期记忆存储，支持 load/save/append/get_all
  - 记忆格式：`##` 分类标题 + `-` 条目，人类可读的 Markdown 文件
  - 新分类自动追加到文件末尾
- `write_memory` 内置工具：LLM 通过 Function Calling 将信息写入长期记忆
- System Prompt 注入：Agent 启动时自动将 `MEMORY.md` 内容注入到 system prompt 尾部（`memory.auto_inject` 控制）
- 触发词检测：用户输入包含"记住"、"remember"等关键词时，自动提示 LLM 调用 `write_memory`（交互和非交互模式均支持）
- `/memory` CLI 命令：显示当前长期记忆内容
- `/memory clear` 命令：清空长期记忆（需确认）
- `/memory edit` 命令：用外部编辑器打开 `MEMORY.md`
- `config.yaml` 新增 `memory` 配置节：`enabled`、`file`、`auto_inject`、`trigger_words`
- `MemoryConfig` 数据类，`AgentConfig` 新增 `memory` 字段和 `resolved_memory_path()` 方法
- 19 个测试用例覆盖 MemoryManager、触发词检测、write_memory 工具和 System Prompt 注入

## [0.2.3] - 2026-05-15

### Added
- `/model` 命令：运行时切换模型，支持按编号或名称选择预设模型，也支持直接输入自定义模型名
- `config.yaml` 新增 `llm.models` 预设模型列表，切换时自动同步更新 provider 和 base_url
- `ModelPreset` 数据类，`load_config()` 解析 models 列表
- `/model` 命令 Tab 补全支持
- 10 个测试用例覆盖模型配置解析和 `/model` 命令切换逻辑

## [0.2.2] - 2026-05-15

### Added
- Excel 工具集（5 个 `@tool`）：
  - `create_workbook`：创建 `.xlsx` 文件，支持表头加粗和自动列宽
  - `read_workbook`：读取 Excel 内容，返回制表符分隔文本，支持指定 sheet 和行数限制
  - `edit_cell`：修改指定单元格的值或公式
  - `format_cells`：设置单元格区域格式（加粗、字体色、背景色、数字格式）
  - `manage_sheet`：工作表管理（创建/删除/重命名/列出）
- `openpyxl>=3.1.0` 依赖，未安装时工具返回明确错误提示
- 22 个测试用例覆盖全部 5 个 Excel 工具的基本功能和边界情况

### Fixed
- `format_cells` 单单元格区域（如 `A1`）格式化失败：openpyxl 对单个单元格返回 `Cell` 对象而非 tuple，已处理两种情况

## [0.2.1] - 2026-05-14

### Added
- Skill 递归发现：自动扫描嵌套子目录中的 `skill.md`，huashu-nuwa 的 14 个子 skill 现在可见（2 → 17）
- Skill 大小写兼容：同时支持 `skill.md` 和 `SKILL.md`，避免 Linux/macOS 部署时静默失败
- Skill 重复名称检测：不同目录的 skill 同名时发出 `warnings.warn` 警告并跳过
- `select_skill` 工具默认启用：无需手动在 `config.yaml` 中添加
- `select_skill` 截断保护：超大 skill 内容（>20KB）自动截断，防止灌爆 LLM context
- `.learnings/` 目录初始化：`LEARNINGS.md`、`ERRORS.md`、`FEATURE_REQUESTS.md`
- 7 个新测试覆盖：递归发现、大小写兼容、重复警告、多行 YAML、无效 YAML 容错、截断保护
- PPT Skill 全面优化（A/B/C/D/E 五项）：
  - 多风格支持：`theme-dark`（科技风）/ `theme-light`（商务风）/ `theme-gradient`（创意风），CSS 变量驱动一键切换
  - 交互增强：F 全屏、O 缩略图概览、N 演讲者备注、空格自动播放、触摸滑动
  - 从主题生成：无需讲稿，输入主题即可自动生成讲稿→大纲确认→HTML 全流程
  - 质量自检：17 项自检规则（文字/结构/视觉/输出），每页 ≤30 字、标题 ≤12 字、列表 ≤5 项
  - 完整 HTML 输出规范：强制完整文件、建议文件名、末尾使用说明
  - 每种页面类型补充反面示例
  - 新增 `references/themes.md`、`references/quality-checklist.md`

### Changed
- Skill frontmatter 解析从手写正则改为 `yaml.safe_load`，支持多行值（`|` 语法）
- `get_skill()` 查找从 O(n) 线性遍历改为 O(1) dict 查找
- Skill 发现中的路径去重从 `any()` 遍历改为 `set` 查找

## [0.2.0] - 2026-05-13

### Added
- `run.bat` Windows 启动脚本，自动使用 conda py100 环境的 Python 3.11，无需手动切环境
- `/chat` 多行聊天框命令：逐行输入，`/send` 发送，`/cancel` 取消
- Bot 回答支持 Markdown 渲染（代码高亮、加粗、列表等）
- 用户消息和 Bot 回答以圆角 Panel 聊天气泡展示
- Session 列表、工具列表、配置、历史等输出改为 rich Table 表格化
- 帮助文本以语法高亮 Panel 展示
- 思考动画改用 rich Status spinner
- `/think` 命令：切换思考过程显示/隐藏
- 提示符状态指示：思考模式开启时显示 `🔍> `，关闭时显示 `> `
- 思考模式开启时：显示工具调用过程（⏳/✓），流式输出最终回答并用 Panel 重新渲染
- 思考模式关闭时：spinner + 完整回答 Panel
- 输入时显示字符、回车后隐藏，由 Panel 统一显示用户消息
- 支持中文字符的光标移动（左/右箭头根据字符宽度移动）
- `tests/test_cli.py` 测试文件：验证思考过程显示控制功能

### Changed
- CLI 依赖从 colorama 迁移至 rich，全面美化输出
- 版本号 0.1.0 -> 0.2.0
- 用户输入改为逐字符读取（Windows: msvcrt, Unix: tty/termios）

### Fixed
- `main.py` 错误提示改为纯 ASCII，修复 Windows cmd GBK 编码导致中文乱码被当作命令执行的问题
- `run.bat` 改为纯 ASCII，修复 cmd 下 UTF-8 中文批处理文件解码失败
- 用户输入重复显示问题：移除 console.input 回显，改为 Panel 统一显示
