# MCP Client 集成设计文档

## 目标

为 ReAct Agent CLI 集成 MCP (Model Context Protocol) Client 能力，使 Agent 能够连接外部 MCP Server 并调用其暴露的工具。

## 设计决策摘要

| 决策项 | 选择 | 理由 |
|--------|------|------|
| MCP 角色 | 仅 Client | 核心需求是让 Agent 调用外部工具，无需对外暴露 |
| 异步策略 | 同步包装 + 后台 event loop 线程 | 现有项目全同步，不改造主循环 |
| 工具命名 | 固定前缀 `server__tool` | 避免冲突，清晰来源 |
| 配置格式 | config.yaml 扁平列表 | 直观，一眼看清所有 server |
| 连接时机 | 启动时全量连接 | LLM 需要 tools schema，必须先 list |
| 失败处理 | 跳过警告继续 | MCP 是可选扩展，不阻塞核心 |
| Event loop | 有 MCP 配置时才启动 | 无 MCP 时零开销 |
| 支持原语 | 仅 Tools（v1） | Resources/Prompts 需额外交互设计 |
| 工具过滤 | Server 级 include/exclude | 精细控制单个 server 的工具暴露 |
| 超时机制 | 每 server 可配，默认 30s | 不同 transport 延迟特征不同 |
| 错误处理 | 断连自动重试一次，超时直接报错 | 重连透明，超时不重试避免卡死 |
| 依赖管理 | 可选依赖 | 和 chromadb 同级，没装就跳过 |
| ToolContext | 新增 mcp_manager 字段 | 保持一致性，便于未来扩展 |
| CLI 命令 | 新增 `/mcp` | 排障必需，查看连接状态和工具列表 |
| 记忆协作 | 无需额外代码 | extractor 自动捕获 MCP 工具结果，ensure_system_prompt 已覆盖上下文注入 |
| Observation 结构 | 不加 external_resources | MCP 操作信息自然保留在 narrative/facts 中，无需结构化字段 |

---

## 架构概览

```
┌─────────────────────────────────────────────────────┐
│                    Agent Loop                        │
│                                                      │
│  LLM.chat(messages, tools)                           │
│     tools = 内置工具 + MCP 工具 (统一 OpenAI schema)  │
│                                                      │
│  execute_tool(name, args, ctx)                       │
│     ├─ 内置工具 → TOOL_REGISTRY[name].func()          │
│     └─ MCP 工具 → ctx.mcp_manager.call_tool()        │
│                        │                             │
│                   ┌────┴────┐                        │
│                   │ 同步桥接 │ run_coroutine_threadsafe│
│                   └────┬────┘                        │
│                        │                             │
│              ┌─────────┴──────────┐                  │
│              │  后台 Event Loop    │ (独立线程)        │
│              │                    │                  │
│              │  MCPManager        │                  │
│              │    ├─ StdioSession │ ←→ 子进程         │
│              │    ├─ SSESession   │ ←→ HTTP Server    │
│              │    └─ HTTPSession  │ ←→ HTTP Server    │
│              └────────────────────┘                  │
└─────────────────────────────────────────────────────┘
```

---

## 模块设计

### 1. `agent/mcp/` — MCP 客户端模块（新目录）

```
agent/mcp/
├── __init__.py
├── manager.py      # MCPManager：管理所有 MCP Server 连接
├── transport.py    # 传输层工厂：stdio / sse / streamable_http
├── bridge.py       # 同步桥接：后台 event loop + 同步调用接口
└── schema.py       # MCP tool schema → OpenAI tool schema 转换
```

#### 1.1 `manager.py` — MCPManager

`MCPServerConfig` 定义在 `agent/config.py`（见第 2 节），`manager.py` 直接复用，不重复定义。

```python
@dataclass
class MCPServerState:
    config: MCPServerConfig
    session: ClientSession | None = None
    tools: list[dict] = field(default_factory=list)    # OpenAI schema 格式
    connected: bool = False
    error: str = ""

class MCPManager:
    """管理所有 MCP Server 连接的生命周期。"""

    def __init__(self, servers: list[MCPServerConfig]):
        ...

    async def connect_all(self) -> dict[str, MCPServerState]:
        """并行连接所有 server，返回 {name: state}。
        连接失败的 server 记录 error，不抛异常。"""

    async def call_tool(self, server_name: str, tool_name: str,
                        arguments: dict) -> str:
        """调用指定 server 的工具。
        断连时自动重连一次。超时抛 TimeoutError。"""

    async def disconnect_all(self):
        """优雅关闭所有 session。stdio server 发 shutdown 信号。"""

    def get_all_tools(self) -> list[dict]:
        """返回所有已连接 server 的工具 schema（OpenAI 格式）。"""

    def get_status(self) -> list[dict]:
        """返回所有 server 的状态（供 /mcp 命令使用）。"""
```

#### 1.2 `transport.py` — 传输层工厂

```python
async def create_transport(config: MCPServerConfig):
    """根据 config.transport 创建对应的 MCP 传输。"""
    if config.transport == "stdio":
        return StdioServerParameters(
            command=config.command,
            args=config.args,
            env=config.env or None,
            cwd=config.cwd or None,
        )
    elif config.transport == "sse":
        return config.url, config.headers
    elif config.transport == "streamable_http":
        return config.url, config.headers
    else:
        raise ValueError(f"Unknown transport: {config.transport}")
```

#### 1.3 `bridge.py` — 同步桥接

```python
class AsyncBridge:
    """在后台线程运行 event loop，提供同步调用接口。"""

    def __init__(self):
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None

    def start(self):
        """启动后台 event loop 线程。"""

    def stop(self):
        """停止 event loop，等待线程退出。"""

    def run_sync(self, coro) -> Any:
        """将 async coroutine 提交到后台 loop，同步等待结果。"""
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return future.result(timeout=...)
```

- 仅在 `config.mcp_servers` 非空时启动
- `main.py` 初始化时创建，`atexit` + 信号处理确保退出时清理

#### 1.4 `schema.py` — Schema 转换

```python
def mcp_tool_to_openai(tool) -> dict:
    """MCP Tool → OpenAI function calling schema。

    MCP 格式:
        {"name": "search", "description": "...", "inputSchema": {...}}
    OpenAI 格式:
        {"type": "function", "function": {"name": "prefix__search", ...}}
    """

def apply_tool_filter(tools: list, include: list[str],
                      exclude: list[str]) -> list:
    """按 include/exclude 正则过滤工具列表。"""
```

---

### 2. 配置变更

#### `config.yaml` 新增字段

```yaml
mcp_servers: []   # MCP Server 列表，空列表 = 不启用 MCP
```

#### `agent/config.py` 新增数据类

```python
@dataclass
class MCPServerConfig:
    name: str
    transport: str = "stdio"           # stdio | sse | streamable_http
    command: str = ""
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    cwd: str = ""
    url: str = ""
    headers: dict[str, str] = field(default_factory=dict)
    timeout: int = 30
    include: list[str] = field(default_factory=list)
    exclude: list[str] = field(default_factory=list)

@dataclass
class AgentConfig:
    ...
    mcp_servers: list[MCPServerConfig] = field(default_factory=list)
```

#### 配置示例

```yaml
mcp_servers:
  # 本地文件系统 MCP (stdio)
  - name: filesystem
    transport: stdio
    command: npx
    args: ["-y", "@modelcontextprotocol/server-filesystem", "/home/user/docs"]
    timeout: 10

  # GitHub MCP (stdio)
  - name: github
    transport: stdio
    command: npx
    args: ["-y", "@modelcontextprotocol/server-github"]
    env:
      GITHUB_TOKEN: "${GITHUB_TOKEN}"   # 引用环境变量（见下方插值说明）

  # 远程 MCP (streamable_http)
  - name: remote-tools
    transport: streamable_http
    url: https://api.example.com/mcp
    headers:
      Authorization: "Bearer ${API_KEY}"
    timeout: 30
    exclude: ["admin_*"]                # 排除危险工具

  # SSE (向后兼容旧 server)
  - name: legacy-server
    transport: sse
    url: http://localhost:3001/sse
```

#### 环境变量插值

`env` 和 `headers` 字段中的 `${VAR_NAME}` 模式在配置加载时自动展开为系统环境变量的值。实现逻辑：

```python
import re

def _interpolate_env(value: str) -> str:
    """将 ${VAR_NAME} 替换为 os.environ[VAR_NAME]。
    未定义的变量保持原样不替换。"""
    def replacer(m):
        var = m.group(1)
        return os.environ.get(var, m.group(0))
    return re.sub(r'\$\{(\w+)\}', replacer, value)
```

递归应用于 `env` 和 `headers` dict 的所有 value。`command`、`args`、`url` 等字段不做插值。

#### 配置校验

`config.py` 加载 `mcp_servers` 列表后，逐条校验：

| 校验规则 | 错误处理 |
|----------|----------|
| `name` 不能为空 | 报错退出 |
| `name` 不能重复 | 报错退出 |
| `transport` 必须是 `stdio`/`sse`/`streamable_http` | 报错退出 |
| stdio 必须有 `command` | 报错退出 |
| sse/streamable_http 必须有 `url` | 报错退出 |
| `timeout` 必须 > 0 | 报错退出 |
| `include`/`exclude` 必须是合法正则 | 报错退出 |

---

### 3. ToolContext 扩展

```python
@dataclass
class ToolContext:
    work_dir: Path
    session_id: str = ""
    skill_manager: SkillManager | None = None
    memory_manager: MemoryManager | None = None
    memory_search: MemorySearch | None = None
    mcp_manager: MCPManager | None = None      # 新增
```

---

### 4. MCP 工具注册与执行

#### 注册流程（启动时）

```
main.py 初始化:
  1. 加载 config
  2. if config.mcp_servers 非空:
     a. 创建 AsyncBridge，启动后台 event loop
     b. 创建 MCPManager(servers)
     c. bridge.run_sync(mcp_manager.connect_all())
     d. 获取 tools = mcp_manager.get_all_tools()
     e. 注册到 TOOL_REGISTRY（带前缀的 wrapper）
  3. 创建 ToolContext(mcp_manager=mcp_manager)
  4. Agent Loop 正常启动
```

#### Wrapper 注册

为每个 MCP 工具创建一个闭包 wrapper 注册到 `TOOL_REGISTRY`：

```python
def _make_mcp_tool_wrapper(server_name: str, tool_name: str,
                           manager: MCPManager, bridge: AsyncBridge):
    full_name = f"{server_name}__{tool_name}"

    def wrapper(args: dict, ctx: ToolContext) -> str:
        return bridge.run_sync(
            manager.call_tool(server_name, tool_name, args)
        )

    return full_name, wrapper
```

工具名格式：`{server_name}__{tool_name}`（双下划线分隔）。

LLM 看到的 tools schema 中，工具名已经是带前缀的全名，无需额外映射。

---

### 5. CLI 命令 `/mcp`

```
/mcp                列出所有 MCP Server 状态
/mcp tools          列出所有 MCP 工具（带前缀名）
/mcp reconnect <n>  重连指定 server（v2）
```

输出示例：

```
MCP Servers
┌──────────────┬─────────┬────────────────────┐
│ Server       │ Status  │ Tools              │
├──────────────┼─────────┼────────────────────┤
│ filesystem   │ ✓ 5 tools │ read_file, ...   │
│ github       │ ✓ 8 tools │ create_issue, ...│
│ remote-tools │ ✗ timeout │ —                │
└──────────────┴─────────┴────────────────────┘
```

---

### 6. 依赖管理

`requirements.txt` 中：

```
# MCP (可选)
mcp>=1.0.0
```

启动时检测逻辑：

```python
# main.py
MCP_AVAILABLE = False
try:
    import mcp
    MCP_AVAILABLE = True
except ImportError:
    pass

if config.mcp_servers and not MCP_AVAILABLE:
    console.print("[yellow]警告: 配置了 MCP Server 但未安装 mcp 包，"
                  "请运行: pip install mcp[/yellow]")
```

---

### 7. 错误处理策略

| 场景 | 处理方式 |
|------|----------|
| 启动时 server 连接失败 | 跳过该 server，打印警告，继续启动 |
| 工具调用时连接断开 | 自动重连一次，失败返回错误字符串给 LLM |
| 工具调用超时 | 返回 `[错误] MCP 工具 {name} 超时({timeout}s)` 给 LLM |
| server 主动关闭 | 标记为 disconnected，下次调用触发重连 |
| mcp 包未安装 | 跳过 MCP 功能，打印警告 |
| 配置格式错误 | 启动时报错，指出具体字段 |

所有错误统一返回 `"[错误] MCP 工具 {name} 执行失败：{reason}"` 字符串，与现有内置工具错误格式一致，LLM 自行决定如何处理。

---

### 8. 文件变更清单

| 文件 | 变更类型 | 说明 |
|------|----------|------|
| `agent/mcp/__init__.py` | 新建 | 模块入口 |
| `agent/mcp/manager.py` | 新建 | MCPManager + MCPServerConfig |
| `agent/mcp/transport.py` | 新建 | 传输层工厂 |
| `agent/mcp/bridge.py` | 新建 | 同步桥接（后台 event loop） |
| `agent/mcp/schema.py` | 新建 | MCP → OpenAI schema 转换 |
| `agent/config.py` | 修改 | 新增 MCPServerConfig 数据类 |
| `agent/tools.py` | 修改 | ToolContext 新增 mcp_manager 字段 |
| `agent/cli.py` | 修改 | 新增 /mcp 命令 |
| `main.py` | 修改 | MCP 初始化 + 注册 + 清理 |
| `config.yaml` | 修改 | 新增 mcp_servers 配置 |
| `requirements.txt` | 修改 | 新增 mcp 可选依赖 |
| `tests/test_mcp.py` | 新建 | MCP 模块单元测试 |

---

### 9. 与记忆系统的协作

MCP 与现有记忆系统（Observation + MEMORY.md + 向量检索）的协作分三个方向：

#### 9.1 MCP 工具结果被记忆系统捕获（自动生效，无需额外代码）

`extractor.py` 在 Session 结束时分析 `session.messages` 全量历史。MCP 工具调用的结果是标准的 `role: tool` 消息，与内置工具无异，提取器天然可见。

- MCP 工具名带前缀（如 `github__create_issue`），LLM 提取器有足够推理能力理解来源
- MCP 操作的是外部系统，`files_read`/`files_modified` 字段为空即可，关键信息保留在 `narrative` 和 `facts` 中
- 不增加 `external_resources` 等新字段，保持 Observation 结构不变

#### 9.2 记忆系统作为 MCP Server 暴露（v2 再考虑）

将 observation 搜索、记忆写入等能力作为 MCP Server 对外提供，让 Claude Code 等外部客户端也能使用本项目的记忆系统。这是独立模块，与 MCP Client 互不依赖，等 Client 稳定后再实现。

#### 9.3 MCP 工具执行时查询记忆（无需额外代码）

`ensure_system_prompt` 在每轮对话开始时已用 `user_input` 做 hybrid search，将相关 observation 注入 system prompt。LLM 基于这些记忆决定调用哪个 MCP 工具——记忆已在起作用，无需在工具调用前后额外查询。

---

### 10. MCP 工具返回值转换

MCP SDK 的 `call_tool` 返回 `(list[Content], isError)` 元组，其中 `Content` 可能是 `TextContent`、`ImageContent`、`EmbeddedResource` 等类型。需要转换为 `execute_tool` 期望的 `str`。

```python
def _mcp_result_to_str(result) -> str:
    """MCP call_tool 返回值 → 字符串。"""
    content_list, isError = result
    parts = []
    for item in content_list:
        if hasattr(item, "text"):          # TextContent
            parts.append(item.text)
        elif hasattr(item, "data"):        # ImageContent / EmbeddedResource
            parts.append(f"[{item.type}: {item.mimeType}] ({len(item.data)} bytes)")
        else:
            parts.append(str(item))
    text = "\n".join(parts)
    if isError:
        return f"[错误] MCP 工具执行失败：{text}"
    return text
```

转换后的字符串同样经过 `_truncate_output()` 截断（20,000 字节上限），与内置工具一致。

---

### 11. Session 恢复与 MCP 工具

恢复旧 session 时，`session.messages` 中可能包含 MCP 工具的 `tool_call` 和 `tool` 消息（如 `github__create_issue`）。此时有两种情况：

| 场景 | 处理 |
|------|------|
| 对应 MCP Server 已连接 | 工具在 TOOL_REGISTRY 中，LLM 可以继续调用 |
| 对应 MCP Server 未连接（配置删除或连接失败） | 工具不在 TOOL_REGISTRY 中，不影响对话历史回放；LLM 若再次调用该工具名，`execute_tool` 返回 `[错误] 工具 github__create_issue 不存在` |

无需特殊处理。`prepare_messages_for_provider` 已有逻辑清理孤立 tool 消息（`agent/llm.py`），DeepSeek 和非 DeepSeek provider 都能正确处理。

---

### 12. 不在 v1 范围内

- MCP Server 角色（入站）
- MCP Resources 和 Prompts 支持
- 工具热更新（listChanged 通知）
- OAuth 认证
- `/mcp reconnect` 命令
- 工具 schema 缓存（避免每次启动都 list_tools）
