# 多 Agent 协作设计文档

## 目标

为 ReAct Agent CLI 增加多 Agent 协作能力，使主 Agent 能够根据任务复杂度自动判断是否需要启动多个专业 Agent 并行工作，通过共享黑板机制交换信息，最终由主 Agent 整合结果回复用户。

## 设计决策摘要

| 决策项 | 选择 | 理由 |
|--------|------|------|
| 协作模式 | 主控编排（Main-led Orchestration） | v1 由主 Agent 负责拆分、调度、汇总；子 Agent 专业执行但不互相调度，避免“对等协作”和“禁止嵌套”冲突 |
| 通信机制 | Task Result + 共享 Observation Store | 短期依赖通过 task result 精确传递，长期/跨任务信息写入 observation store；避免子 agent 早于依赖完成时搜不到黑板内容 |
| 并发模型 | 有上限的线程池 | 改动小，适合 I/O 密集场景；必须限制 `max_concurrent_tasks`，避免模型请求和文件操作无界并发 |
| 编排层 | 独立模块 `agent/orchestrator.py` | 职责清晰，不污染现有 AgentLoop |
| Agent 定义 | config.yaml 中的 `agents` 字段 | 每个 agent 定义 system_prompt、model、tools、max_iterations |
| 记忆策略 | 隔离 session + 结果摘要入黑板 | 对话上下文独立；子 agent 完成后先保存 task result，再通过 ObservationExtractor 或轻量 observation 写入共享记忆 |
| 触发方式 | 主 Agent 自动判断（T3） | 用户无需了解底层 agent 体系，主 agent 根据任务自行决策 |
| Agent 发现 | system prompt 注入（D1） | 与 skill catalog 同一套机制，主 agent 第一轮即可见 |
| spawn 行为 | 异步任务（S2）+ 依赖等待 | `spawn_agent` 立即返回 task_id；带 `depends_on` 的任务先进入 pending，依赖完成后再运行 |
| 嵌套限制 | 工具层硬禁止嵌套（N1） | 不只依赖 prompt；子 agent 的 ToolContext 标记 `can_spawn_agents=False`，调用 spawn 直接返回结构化错误 |
| spawn 参数 | agent + task + context + depends_on | `depends_on` 解决顺序依赖，`context` 承载用户补充或上游 task_id |
| 子 agent session | 保存 + 摘要写入 task result + observation store | 主 Agent 读取稳定的 task result；共享黑板用于后续检索和跨 session 记忆 |
| 判断逻辑 | 纯 LLM 推理（R1） | 靠 system prompt 中的使用指引引导，灵活 |
| CLI 展示 | 简单状态行（U1） | 第一版简洁，后续可升级 |
| 错误处理 | 结构化 JSON + 全局超时 + 可取消标记 | 工具始终返回 `{ok,status,error}`，主 agent 不解析自然语言错误；超时只能协作取消，LLM 请求依赖 request timeout |
| Agent 间通知 | v1 不做主动通知 | 依赖由 orchestrator 处理；子 agent 可主动搜索共享 store，但不承担等待依赖的职责 |
| 实现阶段 | v1 核心骨架 → v2 增强 | 先跑通闭环，再迭代体验 |

---

## 架构概览

```
┌─────────────────────────────────────────────────────────────┐
│                         用户                                 │
│                          │                                   │
│                          ▼                                   │
│                    ┌───────────┐                             │
│                    │    CLI    │                             │
│                    └─────┬─────┘                             │
│                          │                                   │
│                          ▼                                   │
│                  ┌───────────────┐                           │
│                  │  主 AgentLoop │  ← system prompt 注入     │
│                  │               │    agent 列表 + 使用指引    │
│                  └──┬─────────┬──┘                           │
│                     │         │                              │
│         spawn_agent │         │ check_agent_status           │
│                     ▼         ▼                              │
│              ┌─────────────────────┐                        │
│              │    Orchestrator     │ ← agent/orchestrator.py │
│              │                     │                         │
│              │  task_manager       │  管理 task 生命周期       │
│              │  thread_pool        │  线程池执行子 agent       │
│              │  timeout_watchdog   │  全局超时监控             │
│              └──┬──────┬──────┬───┘                         │
│                 │      │      │                              │
│            ┌────┘      │      └────┐                        │
│            ▼           ▼           ▼                         │
│      ┌──────────┐ ┌──────────┐ ┌──────────┐                │
│      │ AgentLoop│ │ AgentLoop│ │ AgentLoop│  ← 各自独立     │
│      │(architect)│ │ (coder)  │ │(reviewer)│    session      │
│      └────┬─────┘ └────┬─────┘ └────┬─────┘                │
│           │             │             │                      │
│           ▼             ▼             ▼                      │
│      ┌──────────────────────────────────────┐               │
│      │     共享 Observation Store (SQLite)    │  ← 黑板      │
│      │     + ChromaDB 向量索引（可选）         │               │
│      └──────────────────────────────────────┘               │
└─────────────────────────────────────────────────────────────┘
```

### 数据流

```
用户输入 "帮我实现登录模块"
  → 主 AgentLoop 收到任务
  → LLM 推理：这个任务需要架构设计 + 编码实现
  → 主 agent 调用 spawn_agent(agent="architect", task="设计登录模块架构")
     → Orchestrator 创建 task，启动线程运行 architect AgentLoop
     → 立即返回 task_id
  → 主 agent 调用 spawn_agent(
        agent="coder",
        task="实现登录模块",
        context="基于 architect task 的设计实现",
        depends_on=["architect_task_id"]
     )
     → Orchestrator 创建 pending task，等待 architect 完成
  → 主 agent 调用 check_agent_status(task_id) 轮询
     → architect 完成 → session 保存 → task result 保存 → 摘要写入 observation store
     → Orchestrator 将 architect 的 summary/result_ref 注入 coder context
     → coder 从 pending 变为 running
     → coder 完成 → session 保存 → task result 保存 → 摘要写入 observation store
  → 主 agent 收到所有结果
  → 主 agent 整合结果，回复用户
```

---

## 模块设计

### 1. `agent/orchestrator.py` — 编排器（新模块）

#### 1.1 Task 数据结构

```python
@dataclass
class AgentTask:
    task_id: str                    # UUID
    agent_name: str                 # 对应 config.agents 中的 key
    task_description: str           # 主 agent 传入的任务描述
    context: str                    # 可选：主 agent 传入的额外上下文
    depends_on: list[str]           # 上游 task_id；未完成前本任务保持 pending
    status: str                     # "pending" | "running" | "completed" | "failed" | "timeout" | "cancelled"
    created_at: float               # time.time()
    started_at: float | None
    completed_at: float | None
    result: str | None              # 子 agent 的最终回答，可能被 max_result_chars 截断
    summary: str | None             # 给主 agent 和下游任务使用的短摘要
    result_ref: str | None          # 完整 session 或 observation 引用，如 session_id / observation_id
    error: str | None               # 失败时的错误信息
    error_type: str | None          # "dependency_failed" | "agent_error" | "timeout" | "cancelled"
    failed_dependency: str | None   # error_type="dependency_failed" 时指向失败的 task_id
    session_id: str | None          # 子 agent 的 session ID
    last_accessed_at: float         # check_status 每次命中刷新；watchdog 用此字段判断是否可清理
    cancellation_token: CancellationToken
    future: Future | None           # ThreadPoolExecutor 返回的 Future
```

#### 1.2 Orchestrator 核心

```python
@dataclass
class CancellationToken:
    cancelled: bool = False
    reason: str | None = None

class Orchestrator:
    def __init__(self, config: AgentConfig, session_manager: SessionManager,
                 observation_store: ObservationStore | None,
                 observation_extractor: ObservationExtractor | None = None):
        self.config = config
        self.session_manager = session_manager
        self.observation_store = observation_store
        self.observation_extractor = observation_extractor
        self.tasks: dict[str, AgentTask] = {}  # task_id -> AgentTask
        self.lock = threading.Lock()
        self.executor = ThreadPoolExecutor(
            max_workers=config.orchestrator.max_concurrent_tasks
        )

    def spawn_agent(self, agent_name: str, task_description: str,
                    context: str = "", depends_on: list[str] | None = None) -> dict:
        """创建子 agent 任务，返回结构化 task 状态。"""
        # 1. 从 config.agents[agent_name] 读取 agent 配置
        # 2. 校验 depends_on 中的 task 是否存在
        # 3. 创建 AgentTask；有未完成依赖则 status="pending"
        # 4. 无依赖则 submit 到线程池；有依赖则由 _watchdog/_schedule_ready_tasks 调度
        # 5. 返回 {"ok": True, "task_id": "...", "status": "..."}

    def check_status(self, task_id: str) -> dict:
        """查询 task 状态。每次命中刷新 last_accessed_at。
        返回 {ok, status, result, error, ...}。
        若 task 已被 retention 清理但 session/result_ref 存在，返回 status="expired" 并附 hint。"""

    def cancel_task(self, task_id: str, reason: str = "") -> dict:
        """协作式取消任务；已进入 LLM 请求或长工具调用时不能立即中断。"""

    def _run_agent(self, task: AgentTask):
        """在线程中执行子 agent。"""
        # 1. 基于 AgentSpec 派生子 agent config，不直接修改主 config
        # 2. 创建独立 Session、LLMClient、ToolContext(can_spawn_agents=False)
        # 3. 将已完成依赖的 summary/result_ref 合并进 task context
        # 4. 运行 AgentLoop.run(task_description)，每轮迭代前检查 cancellation_token
        # 5. 保存 session，生成 summary，必要时截断 result
        # 6. 通过 ObservationExtractor 或轻量 observation 写入 observation store
        # 7. 更新 task.status = "completed" 并调度依赖它的 pending task
        # 8. 异常时：task.status = "failed"，记录 error

    def cleanup(self):
        """停止 watchdog，关闭 executor，清理过期 task 快照。"""
```

#### 1.3 超时机制

```python
TERMINAL_STATUSES = {"completed", "failed", "timeout", "cancelled"}

def _watchdog(self):
    """后台守护线程，每 10s 检查超时 task、调度依赖已满足的 pending task、清理过期终态 task。"""
    while True:
        now = time.time()
        with self.lock:
            tasks = list(self.tasks.values())

        for task in tasks:
            # 1. 超时检查
            if task.status == "running":
                elapsed = now - (task.started_at or task.created_at)
                if elapsed > self.config.orchestrator.task_timeout:
                    task.status = "timeout"
                    task.error = f"Agent {task.agent_name} timed out after {elapsed:.0f}s"
                    task.cancellation_token.cancelled = True
                    task.cancellation_token.reason = "timeout"

            # 2. 依赖调度
            if task.status == "pending" and self._dependencies_completed(task):
                self._submit_task(task)

        # 3. 清理过期终态 task（用 last_accessed_at 而非 completed_at）
        with self.lock:
            expired_ids = [
                tid for tid, t in self.tasks.items()
                if t.status in TERMINAL_STATUSES
                and now - t.last_accessed_at > self.config.orchestrator.task_retention_seconds
            ]
            for tid in expired_ids:
                del self.tasks[tid]

        time.sleep(10)
```

> **清理策略**：只清理终态 task（completed/failed/timeout/cancelled），基于 `last_accessed_at` 判断是否过期。pending/running 永不按 retention 清理，只能超时、取消或完成。task 被清理后，完整结果不丢失——`session_id` / `result_ref` 指向 session 或 observation，主 agent 若持有之前的 status 响应仍可追溯。

> **注意**：Python 无法强制终止线程。超时后只能设置 `CancellationToken`，子 agent 在每轮迭代前、工具执行前后检查后退出。已经阻塞在 LLM 请求或长耗时工具里的执行，依赖 LLM/request timeout 和工具自身超时兜底。

---

### 2. 新增 Tool：`spawn_agent` + `check_agent_status`

注册到 `TOOL_REGISTRY`，与内置工具同级。

#### 2.1 `spawn_agent`

```python
@tool(
    name="spawn_agent",
    description="启动一个专业 Agent 来处理指定任务。Agent 在后台运行，立即返回 task 状态；只有主 Agent 可调用。",
    schema={
        "type": "object",
        "properties": {
            "agent": {
                "type": "string",
                "description": "Agent 名称，如 architect、coder、reviewer"
            },
            "task": {
                "type": "string",
                "description": "任务描述，越具体越好"
            },
            "context": {
                "type": "string",
                "description": "可选的额外上下文信息"
            },
            "depends_on": {
                "type": "array",
                "items": {"type": "string"},
                "description": "可选，上游 task_id 列表；未完成前本任务保持 pending"
            }
        },
        "required": ["agent", "task"]
    }
)
def spawn_agent(args: dict, ctx: ToolContext) -> str:
    """启动子 agent，返回 task_id。"""
    if not ctx.can_spawn_agents:
        return json.dumps({
            "ok": False,
            "status": "failed",
            "error": "spawn_agent is only available to the main agent",
        }, ensure_ascii=False)

    if ctx.orchestrator is None:
        return json.dumps({
            "ok": False,
            "status": "failed",
            "error": "orchestrator is not configured",
        }, ensure_ascii=False)

    result = ctx.orchestrator.spawn_agent(
        agent_name=args["agent"],
        task_description=args["task"],
        context=args.get("context", ""),
        depends_on=args.get("depends_on", []),
    )
    return json.dumps(result, ensure_ascii=False)
    # 返回: {"ok": true, "task_id": "task_xxx", "agent": "coder", "status": "running"}
```

#### 2.2 `check_agent_status`

```python
@tool(
    name="check_agent_status",
    description="查询子 Agent 的执行状态。返回状态、结果或错误信息。",
    schema={
        "type": "object",
        "properties": {
            "task_id": {
                "type": "string",
                "description": "spawn_agent 返回的 task_id"
            }
        },
        "required": ["task_id"]
    }
)
def check_agent_status(args: dict, ctx: ToolContext) -> str:
    """查询 task 状态。"""
    if ctx.orchestrator is None:
        return json.dumps({
            "ok": False,
            "status": "failed",
            "error": "orchestrator is not configured",
        }, ensure_ascii=False)

    result = ctx.orchestrator.check_status(args["task_id"])
    return json.dumps(result, ensure_ascii=False)
```

#### 2.3 ToolContext 扩展

```python
@dataclass
class ToolContext:
    work_dir: Path
    session_id: str
    config: AgentConfig
    skill_manager: SkillManager | None = None
    memory_manager: MemoryManager | None = None
    memory_search: MemorySearch | None = None
    mcp_manager: MCPManager | None = None
    orchestrator: Orchestrator | None = None
    can_spawn_agents: bool = True  # 主 agent 为 True，子 agent 必须为 False
```

---

### 3. System Prompt 注入

在 `AgentLoop.ensure_system_prompt()` 中，新增 agent 列表注入逻辑（与 skill catalog 同级）。

#### 3.1 注入格式

```
## Available Agents

Use the spawn_agent tool to delegate tasks to specialized agents.
Each agent runs independently and returns results asynchronously.
Use check_agent_status to poll for results.
If one agent depends on another agent's output, pass depends_on with the upstream task_id.

- **architect**: 软件架构师，负责分析需求、设计模块结构、定义接口。
  USE WHEN: the task requires system design, module decomposition, or interface definition.
  DON'T USE FOR: writing code, reviewing code, simple questions.

- **coder**: 高级开发者，根据设计规格编写实现代码。
  USE WHEN: you have a clear spec and need implementation code written.
  DON'T USE FOR: vague requirements without design, code review.

- **reviewer**: 代码审查专家，检查代码质量、安全性和可维护性。
  USE WHEN: code has been written and needs quality/safety review.
  DON'T USE FOR: writing code, designing systems.

## Collaboration

You may work alongside other agents. When your task depends on another agent's
output (e.g., "implement based on the design"), prefer depends_on so the
orchestrator injects the upstream summary/result reference before the dependent
agent starts. Use search_memory for broader background or older observations.

IMPORTANT: Only spawn agents when the task genuinely benefits from specialization.
For simple tasks, handle them yourself. Don't spawn agents just because they exist.
```

#### 3.2 注入条件

- `config.orchestrator.enabled == True`
- `config.agents` 非空
- 主 agent 的 system prompt 中注入
- 子 agent 不注入 Available Agents，且其 `ToolContext.can_spawn_agents=False`，工具层硬禁止嵌套 spawn

---

### 4. Config 格式

#### 4.1 新增配置项

```yaml
# config.yaml

agents:
  architect:
    system_prompt: |
      你是一个软件架构师，负责分析需求、设计模块结构、定义接口。
      输出应该包含：模块划分、接口定义、数据结构、技术选型理由。
    model: mimo-v2.5-pro          # 可选，默认继承主 config
    tools: [read_file, list_dir, search_files, search_memory]  # 可选，默认继承全部
    max_iterations: 15            # 可选，默认继承主 config

  coder:
    system_prompt: |
      你是一个高级开发者，根据设计规格编写实现代码。
      要求：代码风格一致、有必要的错误处理、遵循项目约定。
    max_iterations: 30

  reviewer:
    system_prompt: |
      你是一个代码审查专家，检查代码质量、安全性和可维护性。
      输出格式：问题列表，每个问题包含文件位置、问题描述、修复建议。
    tools: [read_file, list_dir, search_files]
    max_iterations: 10

orchestrator:
  enabled: true                   # 是否启用多 agent 能力
  task_timeout: 300               # 子 agent 全局超时（秒），默认 300
  llm_timeout: 120                # 单次 LLM 请求超时（秒），默认继承主 LLMClient 配置
  max_concurrent_tasks: 3         # 最大并发子 agent 数，防止无界并发
  max_result_chars: 12000         # check_status 返回的 result 最大长度，超出后保留 summary + result_ref
  task_retention_seconds: 3600    # completed/failed/timeout task 在内存中的保留时间
```

#### 4.2 配置加载

在 `AgentConfig` 中新增：

```python
@dataclass
class AgentSpec:
    """单个 agent 的定义。"""
    name: str
    system_prompt: str
    model: str | None = None          # None = 继承主 config
    tools: list[str] | None = None    # None = 继承全部 enabled_tools
    max_iterations: int | None = None # None = 继承主 config
    result_summary_prompt: str | None = None # 可选：用于压缩子 agent 结果的摘要提示

@dataclass
class OrchestratorConfig:
    """编排器配置。"""
    enabled: bool = False
    task_timeout: int = 300
    llm_timeout: int | None = None
    max_concurrent_tasks: int = 3
    max_result_chars: int = 12000
    task_retention_seconds: int = 3600

# AgentConfig 中新增：
# agents: dict[str, AgentSpec] = field(default_factory=dict)
# orchestrator: OrchestratorConfig = field(default_factory=OrchestratorConfig)
```

---

### 5. 子 Agent 执行流程

#### 5.1 启动

```
spawn_agent(
  agent="coder",
  task="实现登录模块",
  context="基于 architect 设计",
  depends_on=["architect_task_id"]
)
  → Orchestrator.spawn_agent()
    → 读取 config.agents["coder"]
    → 校验 depends_on 引用的 task 存在
    → 创建 AgentTask
    → last_accessed_at = created_at
    → 如果依赖未完成，状态设为 "pending"
    → 如果依赖已完成或无依赖，提交到 ThreadPoolExecutor，状态设为 "running"
    → 立即返回 {"ok": true, "task_id": "xxx", "status": "pending"}
```

#### 5.2 执行

```
_run_agent(task):
  try:
    task.started_at = time.time()

    if task.cancellation_token.cancelled:
      task.status = "cancelled"
      return

    dependency_context = collect_dependency_summaries(task.depends_on)
    # 如果任一依赖 failed/timeout/cancelled，直接标记本 task 为 failed，不启动 agent
    if dependency_context.has_failures:
        task.status = "failed"
        task.error_type = "dependency_failed"
        task.failed_dependency = dependency_context.first_failed_task_id
        task.error = f"Upstream task {task.failed_dependency} failed: {dependency_context.first_error}"
        return
    agent_loop = create_child_agent_loop(
      task=task,
      can_spawn_agents=False,
    )
    task.session_id = agent_loop.session.id
    result = agent_loop.run(task.task_description + "\n\n" + dependency_context)

    task.result = result
    task.summary = summarize_result(result, max_chars=1200)
    task.result_ref = task.session_id
    task.status = "completed"
    task.completed_at = time.time()

    # 保存 session
    session_manager.save_session(agent_loop.session)

    # 提取或写入 observation store
    self._persist_observation(task, result)

  except Exception as e:
    task.status = "failed"
    task.error = str(e)
```

#### 5.3 Observation 写入

```python
def _persist_observation(self, task: AgentTask, result: str):
    """将子 agent 产出写入共享 observation store。"""
    if not self.observation_store:
        return

    if self.observation_extractor:
        observations = self.observation_extractor.extract_from_session(task.session_id)
        inserted = self.observation_store.insert_batch(observations)
        task.result_ref = f"session:{task.session_id}"
        return

    # fallback：没有 extractor 时写入一条轻量 observation，保证黑板可用。
    # 根据 agent 名称推断 observation type
    type_map = {
        "architect": "decision",
        "coder": "feature",
        "reviewer": "discovery",
    }
    obs_type = type_map.get(task.agent_name, "change")

    observation = Observation(
        id=str(uuid.uuid4()),
        type=obs_type,
        title=f"[{task.agent_name}] {task.task_description[:50]}",
        narrative=result,
        facts=[],
        concepts=[],
        files_read=[],
        files_modified=[],
        session_id=task.session_id,
        created_at=datetime.now().isoformat(),
        relevance_count=0,
        content_hash=hashlib.sha256(
            ((task.session_id or "") + task.task_description[:50] + result[:200]).encode()
        ).hexdigest()[:16],
    )
    if self.observation_store.insert(observation):
        task.result_ref = f"observation:{observation.id}"
```

> **约束**：完整 result 不直接等同于长期记忆。任务结果用于当前编排闭环，Observation 用于后续检索和晋升。优先使用既有 `ObservationExtractor` 保持 schema、去重和向量索引一致；轻量 observation 只作为 v1 fallback。

---

### 6. CLI 集成

#### 6.1 状态展示

主 agent 的对话流程中，spawn 和 check_status 的 tool call/result 会自然出现在消息历史中。CLI 需要在主 agent 等待期间展示子 agent 状态。

```python
# cli.py 中的 tool call 回调
def on_tool_call(event: ToolCallEvent):
    if event.name == "spawn_agent":
        args = json.loads(event.arguments)
        console.print(f"  ⏳ 启动 agent: {args['agent']} — {args['task'][:40]}")

    if event.name == "check_agent_status":
        # check_agent_status 的 result 回调中展示状态变化
        pass

def on_tool_result(event: ToolResultEvent):
    if event.name == "check_agent_status":
        result = json.loads(event.result)
        status_icon = {
            "pending": "…",
            "running": "⏳",
            "completed": "✅",
            "failed": "❌",
            "timeout": "⏰",
            "cancelled": "⏹",
        }
        icon = status_icon.get(result["status"], "❓")
        console.print(f"  {icon} {result['agent']}: {result['status']}")
```

#### 6.2 `/tasks` 命令（可选，v2）

```
> /tasks
┌──────────┬───────────┬──────────┬──────────┐
│ Task ID  │ Agent     │ Status   │ Duration │
├──────────┼───────────┼──────────┼──────────┤
│ task_abc │ architect │ ✅ done  │ 12s      │
│ task_def │ coder     │ ⏳ running│ 25s...  │
└──────────┴───────────┴──────────┴──────────┘
```

---

### 7. 错误处理

| 场景 | 处理方式 |
|------|------|
| agent 名称不存在 | `spawn_agent` 返回 `{"ok": false, "status": "failed", "error": "unknown agent: xxx"}` |
| 子 agent 调用 `spawn_agent` | 工具层检查 `ctx.can_spawn_agents=False`，返回结构化错误，不创建 task |
| `depends_on` 引用不存在 | `spawn_agent` 直接返回结构化错误，不创建 task |
| 上游 task 失败/超时 | 下游 pending task 标记为 `failed`，返回 `error_type: "dependency_failed"` + `failed_dependency: "task_id"`；主 agent 可自行重新 spawn 新 task 恢复 |
| 子 agent API 调用失败 | 子 agent 的 AgentLoop 内部已有 try-except；orchestrator 捕获外层异常，`task.status = "failed"` |
| 子 agent max_iterations 耗尽 | AgentLoop 返回警告字符串，`task.status = "completed"`，summary 中保留警告 |
| 全局超时 | watchdog 设置 `task.status = "timeout"` 和 cancellation token；无法强杀已阻塞线程 |
| observation store 写入失败 | 记录警告日志，不影响 task 状态（observation 是增强功能，非必需） |
| 主 agent 调用 check_status 时 task 不存在 | 返回 `{"ok": false, "status": "failed", "error": "task not found: xxx"}` |
| task 已被 retention 清理 | 返回 `{"ok": false, "status": "expired", "error": "task metadata expired", "hint": "Use result_ref/session_id if available from previous status response."}` |
| result 超过 `max_result_chars` | check_status 返回 summary + result_ref，result 字段截断或省略 |

---

### 8. 线程安全

| 共享资源 | 保护策略 |
|----------|----------|
| `Orchestrator.tasks` dict | 所有读写都使用 `threading.Lock`；对外返回 snapshot，不在遍历时暴露可变 dict |
| `TOOL_REGISTRY` | 只在启动时写入，运行时只读，无需锁 |
| `ObservationStore` (SQLite) | 开启 WAL；每线程独立 SQLite connection，或由单写入队列串行写入 |
| `SessionManager` | 每个子 agent 有独立 session；如果索引文件共享，保存和索引更新必须加锁 |
| `LLMClient` | 每个子 agent 创建独立实例；不要在多个线程共享带可变状态的 client |
| `CancellationToken` | task 独占，orchestrator 只设置取消标记；AgentLoop 和工具只读检查 |
| 工作目录 `work_dir` | 子 agent 使用创建时的 work_dir 快照；`change_dir` 只影响自身 ToolContext，不影响其他 agent |

> **原则**：不要依赖 GIL 判断复合操作安全。只要涉及“检查后修改”“遍历时可能被写入”“多个对象状态联动”，都必须用锁或不可变 snapshot。

---

## 实现阶段

### v1：核心骨架

**目标**：跑通主 agent → spawn 子 agent → 并行执行 → 结果回流 → 用户看到回答 的完整闭环。

| 任务 | 涉及文件 |
|------|----------|
| 新增 `AgentSpec` 和 `OrchestratorConfig` 数据类 | `agent/config.py` |
| config.yaml 解析 `agents` 和 `orchestrator` 字段 | `agent/config.py` |
| 实现 `Orchestrator` 类（task 管理、线程池、超时 watchdog） | `agent/orchestrator.py`（新建） |
| 注册 `spawn_agent` 和 `check_agent_status` tool | `agent/tools.py` |
| `ToolContext` 新增 `orchestrator` 字段 | `agent/tools.py` |
| `ToolContext` 新增 `can_spawn_agents` 并在子 agent 中置为 False | `agent/tools.py`, `agent/orchestrator.py` |
| `ensure_system_prompt()` 注入 agent 列表 | `agent/loop.py` |
| AgentLoop 支持协作式取消检查 | `agent/loop.py` |
| 子 agent 完成后保存 task result，并通过 ObservationExtractor/fallback observation 写入 observation store | `agent/orchestrator.py`, `agent/extractor.py` |
| CLI tool call/result 回调展示子 agent 状态 | `agent/cli.py` |
| `main.py` 启动时初始化 Orchestrator | `main.py` |
| 单元测试 | `tests/test_orchestrator.py`, `tests/test_agent_tools.py`, `tests/test_multi_agent_config.py` |
| 更新设计文档和 CHANGELOG | `docs/design/`, `CHANGELOG.md` |

### v1 必测用例

| 测试 | 验证点 |
|------|--------|
| `test_spawn_agent_returns_running_task` | 无依赖任务立即进入 running，并返回结构化 JSON |
| `test_spawn_agent_with_dependency_stays_pending` | 依赖未完成时下游 task 保持 pending |
| `test_dependency_completion_schedules_pending_task` | 上游 completed 后，下游自动提交执行 |
| `test_dependency_failure_fails_downstream_task` | 上游 failed/timeout 时，下游 task 标记 failed，返回 `error_type="dependency_failed"` |
| `test_child_agent_cannot_spawn` | 子 agent 的 `can_spawn_agents=False` 会让 `spawn_agent` 返回错误 |
| `test_unknown_agent_returns_structured_error` | agent 名称不存在时不抛异常、不创建 task |
| `test_unknown_dependency_returns_structured_error` | `depends_on` task_id 不存在时返回结构化错误 |
| `test_timeout_sets_cancellation_token` | 超时后 task 变为 timeout，token 标记 cancelled |
| `test_check_status_truncates_large_result` | 超长 result 返回 summary/result_ref，不撑爆上下文 |
| `test_tasks_snapshot_thread_safe` | 并发 spawn/check 不触发 dict 遍历或状态竞争异常 |
| `test_observation_write_failure_does_not_fail_task` | observation 写入失败只记录警告，task 仍 completed |
| `test_tool_context_work_dir_is_isolated` | 子 agent change_dir 不影响主 agent 和其他子 agent |
| `test_retention_cleanup_removes_expired_terminal_tasks` | 终态 task 超过 retention 且 last_accessed_at 过期后被清理 |
| `test_check_status_returns_expired_for_cleaned_task` | 已清理 task 返回 `status="expired"` 并附 result_ref hint |
| `test_check_status_refreshes_last_accessed_at` | 每次 check_status 刷新 last_accessed_at，防止被提前清理 |

### v2：增强

| 功能 | 说明 |
|------|------|
| Workflow 预定义 | config.yaml 中定义 `workflows`，CLI 支持 `/run workflow_name` |
| Agent 间 handoff tool | `handoff_to(agent, context)` 让子 agent 主动把控制权交给另一个 agent |
| CLI 分区面板 | 每个子 agent 独立 Panel，实时更新 tool call 过程 |
| Agent 执行日志回放 | `/tasks <task_id>` 查看子 agent 的完整对话历史 |
| 嵌套 spawn（带深度限制） | 子 agent 也能 spawn，最多 2 层 |
| 动态 agent 注册 | 运行时通过 tool 添加/删除 agent 定义 |
