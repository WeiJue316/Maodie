# Python ReAct Agent 详细设计文档

## 1. 项目概述

本项目实现一个功能完整的 Python CLI Agent，基于 ReAct（Reasoning + Acting）架构。

**核心目标**：
- 实现完整的 ReAct Agent Loop（Reasoning + Acting）
- 支持常用文件操作、目录操作等工具
- 提供类似 openclaw 的交互式 CLI 界面
- 支持 Session 持久化与恢复
- 通过配置文件统一管理项目设置

**工作目录**：`project_class/`（所有路径默认相对于此目录）

---

## 2. 项目结构

```
project_class/
├── config.yaml                # 项目配置文件（用户填写）
├── config.example.yaml        # 配置示例（提交到版本库）
├── .env                       # 环境变量（API Key 等，不提交）
├── .sessions/                 # Session 持久化目录
│   ├── index.json             # Session 索引（id -> 元信息）
│   └── <session-id>.json      # 各 Session 的对话历史
├── .memory/                   # 记忆系统数据目录
│   ├── memory.db              # SQLite 数据库（observations + FTS5）
│   └── chroma/                # ChromaDB 持久化目录
├── MEMORY.md                  # 长期记忆主文件（晋升目标）
├── agent/
│   ├── __init__.py
│   ├── cli.py                 # CLI 入口，交互式 REPL
│   ├── loop.py                # Agent Loop（ReAct 核心）
│   ├── llm.py                 # LLM 客户端封装
│   ├── tools.py               # 工具注册与执行
│   ├── session.py             # Session 管理
│   ├── config.py              # 配置加载
│   ├── memory.py              # 长期记忆管理（MEMORY.md 读写）
│   ├── observation.py         # Observation 存储层（SQLite + FTS5）
│   ├── vectordb.py            # 向量检索层（ChromaDB + embedding）
│   ├── memory_search.py       # 统一检索编排（向量 + FTS5 + 晋升）
│   └── extractor.py           # Observation 提取（LLM 从对话中提取）
└── main.py                    # 程序入口（python main.py）
```

---

## 3. 配置文件设计

### 3.1 config.yaml

```yaml
# project_class/config.yaml
llm:
  provider: deepseek            # 支持: deepseek | openai | custom
  api_key: ""                   # 也可通过环境变量 AGENT_API_KEY 覆盖
  base_url: "https://api.deepseek.com/v1"
  model: "deepseek-chat"
  temperature: 0.7
  timeout: 60
  max_retries: 3
  streaming: true               # 是否启用流式输出

agent:
  max_iterations: 20            # 单次 Agent Loop 最大步数，防止死循环
  work_dir: "."                 # 工作目录，相对于 project_class/
  system_prompt: |
    你是一个智能助手，可以使用工具帮助用户完成任务。
    工作目录为 {work_dir}。

session:
  dir: ".sessions"              # Session 文件存储目录
  max_history: 100              # 单个 Session 最多保留的消息轮数
  auto_save: true               # 每轮对话后自动保存

tools:
  enabled:                      # 启用的工具列表
    - read_file
    - write_file
    - list_dir
    - change_dir
    - shell
    - search_files
```

### 3.2 环境变量优先级

环境变量可覆盖 config.yaml 中的对应值：

| 环境变量 | 对应配置 |
|---|---|
| `AGENT_API_KEY` | `llm.api_key` |
| `AGENT_BASE_URL` | `llm.base_url` |
| `AGENT_MODEL` | `llm.model` |
| `AGENT_WORK_DIR` | `agent.work_dir` |

### 3.3 config.py 实现逻辑

```
加载顺序（后者覆盖前者）：
1. config.yaml 默认值
2. .env 文件（通过 python-dotenv）
3. 系统环境变量
```

---

## 4. LLM 客户端（llm.py）

封装对 OpenAI-compatible API 的调用，与具体 provider 解耦。

### 4.1 接口设计

```python
class LLMClient:
    def __init__(self, config: LLMConfig): ...

    def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        stream: bool = False,
    ) -> str | Generator[str, None, None]:
        """
        发送对话请求。
        - messages: OpenAI 格式的消息列表
        - tools: 工具 schema 列表（OpenAI function calling 格式）
        - stream: 是否流式返回
        返回：完整回复字符串 或 流式 Generator
        """
```

### 4.2 消息格式

使用 OpenAI 标准格式：

```json
[
  {"role": "system", "content": "你是一个智能助手..."},
  {"role": "user", "content": "用户的问题"},
  {"role": "assistant", "content": "...", "tool_calls": [...]},
  {"role": "tool", "tool_call_id": "xxx", "content": "工具结果"}
]
```

### 4.3 工具调用格式（OpenAI Function Calling）

LLM 返回结构：
```json
{
  "role": "assistant",
  "tool_calls": [
    {
      "id": "call_abc123",
      "type": "function",
      "function": {
        "name": "read_file",
        "arguments": "{\"path\": \"README.md\"}"
      }
    }
  ]
}
```

> **设计决策**：使用 OpenAI Function Calling 格式替代原有的 ````json` 文本解析方式，更可靠，避免 JSON 提取的脆弱性。DeepSeek API 完全兼容此格式。

---

## 5. 工具系统（tools.py）

### 5.1 工具注册机制

使用装饰器注册，工具元信息（name、description、schema）内聚在工具函数本身：

```python
TOOL_REGISTRY: dict[str, Tool] = {}

@tool(
    name="read_file",
    description="读取文件内容",
    schema={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "文件路径（相对于工作目录）"}
        },
        "required": ["path"]
    }
)
def read_file(path: str, context: ToolContext) -> str:
    ...
```

`ToolContext` 包含当前工作目录等运行时状态，工具通过它读取/修改状态。

### 5.2 内置工具清单

| 工具名 | 描述 | 参数 |
|---|---|---|
| `read_file` | 读取文件内容 | `path: str`, `encoding?: str` |
| `write_file` | 写入文件内容 | `path: str`, `content: str`, `append?: bool` |
| `list_dir` | 列出目录内容 | `path?: str`（默认当前目录）|
| `change_dir` | 切换工作目录 | `path: str` |
| `shell` | 执行 shell 命令 | `command: str`, `timeout?: int` |
| `search_files` | 在目录中搜索文件 | `pattern: str`, `path?: str` |

### 5.3 工具执行流程

```
loop.py 收到 tool_calls
  → 查找 TOOL_REGISTRY[tool_name]
  → 解析 arguments JSON
  → 执行工具函数，传入 ToolContext
  → 捕获异常，返回错误字符串（不中断 loop）
  → 构建 role=tool 消息追加到 messages
```

### 5.4 ToolContext

```python
@dataclass
class ToolContext:
    work_dir: str           # 当前工作目录（可被 change_dir 修改）
    session_id: str         # 当前 Session ID
    config: AgentConfig     # 全局配置
```

---

## 6. Skill 系统（skills.py）

### 6.1 概述

Skill 是一种可扩展的能力包，每个 Skill 是一个包含 `skill.md` 描述文件的目录。Agent 在对话中可以动态发现、选择并加载 Skill，将其完整指令注入当前上下文，从而获得新的能力。

### 6.2 Skill 目录结构

```
project_class/
└── skills/
    ├── read_skill/
    │   └── skill.md          # Skill 描述文件（名称、描述、详细指令）
    ├── write_skill/
    │   └── skill.md
    └── search_skill/
        └── skill.md
```

**发现规则**：遍历 `skills/` 目录，包含 `skill.md` 文件的子目录即为一个 Skill。

### 6.3 skill.md 格式

```markdown
---
name: read_skill
description: 读取并分析文件内容，支持多种编码和格式
---

# Read Skill

你是一个文件读取专家。当用户需要读取文件时：
1. 先使用 list_dir 了解目录结构
2. 使用 read_file 读取目标文件
3. 对内容进行分析和总结

## 规则
- 优先读取文本文件
- 遇到二进制文件时提示用户
- 大文件分段读取
```

- **Frontmatter**（`---` 之间）：`name`（Skill 名称）和 `description`（一行描述）
- **正文**：详细的 Skill 指令，加载后作为 system-level 上下文注入

### 6.4 Skill 数据结构

```python
@dataclass
class Skill:
    name: str               # Skill 名称（来自 frontmatter 或目录名）
    description: str        # 一行描述（来自 frontmatter）
    path: Path              # skill.md 所在目录的绝对路径
    content: str            # skill.md 的完整内容（含 frontmatter）
```

### 6.5 SkillManager 接口

```python
class SkillManager:
    def __init__(self, skills_dir: Path): ...

    def discover(self) -> list[Skill]:
        """扫描 skills/ 目录，返回所有已发现的 Skill 列表。"""

    def get_skill(self, name: str) -> Skill | None:
        """按名称查找并返回 Skill，未找到返回 None。"""

    def get_skill_summaries(self) -> str:
        """返回所有 Skill 的名称+描述摘要，用于注入 LLM 提示词。"""
```

### 6.6 Skill 注入流程

```
用户发送消息
  ↓
SkillManager.discover() 获取所有可用 Skill
  ↓
将 Skill 摘要列表作为工具描述的一部分传给 LLM
  ↓
LLM 决定是否调用 select_skill 工具
  ├─ 调用 → 读取对应 skill.md 完整内容 → 作为工具结果返回 → LLM 继续处理
  └─ 不调用 → 正常回答
```

### 6.7 select_skill 工具

注册为内置工具，LLM 通过 Function Calling 调用：

```python
@tool(
    name="select_skill",
    description="选择并加载一个 Skill。可用 Skills：\n{skill_summaries}",
    schema={
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "要加载的 Skill 名称"}
        },
        "required": ["name"]
    }
)
def select_skill(args, ctx) -> str:
    # 读取 skill.md 完整内容返回给 LLM
```

**关键设计**：`select_skill` 的 `description` 动态生成，包含所有 Skill 的名称和描述，使 LLM 能据此做出选择。

### 6.8 配置

```yaml
# config.yaml
skills:
  dir: "skills"              # Skill 目录，相对于 project_root
```

环境变量：`AGENT_SKILLS_DIR` 可覆盖。

### 6.9 CLI 命令

| 命令 | 描述 |
|---|---|
| `/skills` | 列出所有已发现的 Skill |
| `/skills reload` | 重新扫描 Skill 目录 |

---

## 7. 长期记忆系统（memory.py）

### 7.1 概述

长期记忆使 Agent 能够跨会话记住用户的重要信息。与 Session 保存完整对话历史不同，长期记忆只保存用户明确要求记住的关键信息（偏好、约束、上下文等）。

**设计原则**（简化自 openclaw）：
- 存储为人类可读的 Markdown 文件，不依赖数据库
- Agent 启动时自动注入 system prompt，无需额外操作
- 用户通过自然语言触发（"记住"、"记一下"等），LLM 决定写入内容

### 7.2 存储结构

```
project_class/
├── MEMORY.md              # 长期记忆主文件（项目根目录）
└── agent/
    └── memory.py          # 记忆管理模块
```

**MEMORY.md 格式**：

```markdown
# 长期记忆

## 用户偏好
- 偏好使用中文交流
- 喜欢简洁的回答，不要过度解释

## 项目约束
- 所有 API 调用必须设置超时
- 日志格式统一为 JSON

## 历史上下文
- 2024-04-20: 用户提到项目最终要部署到 AWS Lambda
```

采用分类组织（`##` 二级标题），每条记忆一行，以 `-` 开头。

### 7.3 MemoryManager 接口

```python
class MemoryManager:
    def __init__(self, memory_path: Path): ...

    def load(self) -> str:
        """读取 MEMORY.md 全部内容。文件不存在时返回空字符串。"""

    def save(self, content: str) -> None:
        """覆盖写入 MEMORY.md。"""

    def append(self, category: str, item: str) -> None:
        """向指定分类追加一条记忆。分类不存在时自动创建。"""

    def get_all(self) -> dict[str, list[str]]:
        """解析 MEMORY.md，返回 {分类: [记忆条目]} 字典。"""
```

### 7.4 System Prompt 注入

Agent 启动时（`AgentLoop.__init__`），将 MEMORY.md 内容注入到 system prompt 尾部：

```
原始 system_prompt（来自 config.yaml）
+
"\n\n# 长期记忆\n以下是用户之前要求记住的信息，在回答时参考：\n"
+
MEMORY.md 的完整内容
```

**时机**：仅在 Session 首次创建时注入一次（写入 `session.messages[0]`）。恢复已有 Session 时，记忆已在历史消息的 system prompt 中。

### 7.5 记忆写入触发

**触发词检测**：在 `cli.py` 的用户输入处理中，检测是否包含触发关键词：
- 中文：`记住`、`记一下`、`记着`、`别忘了`
- 英文：`remember`、`keep in mind`、`don't forget`

**处理流程**：

```
用户输入包含触发词？
  ├─ 否 → 正常进入 Agent Loop
  └─ 是 → 追加隐式指令到用户消息末尾：
          "\n\n[系统提示] 用户希望记住某些信息，请使用 write_memory 工具将其保存到长期记忆。"
          → 正常进入 Agent Loop
          → LLM 自行决定调用 write_memory 工具
```

**设计决策**：不硬编码解析逻辑，而是让 LLM 判断用户想记住什么。触发词只是提示，最终由 LLM 决定是否写入、写入什么内容、归入哪个分类。

### 7.6 write_memory 工具

注册为内置工具，LLM 通过 Function Calling 调用：

```python
@tool(
    name="write_memory",
    description="将信息写入长期记忆。记忆会跨会话保存，下次启动时自动加载。",
    schema={
        "type": "object",
        "properties": {
            "category": {
                "type": "string",
                "description": "记忆分类，如：用户偏好、项目约束、历史上下文"
            },
            "content": {
                "type": "string",
                "description": "要记住的具体内容，简洁明了"
            }
        },
        "required": ["category", "content"]
    }
)
def write_memory(category: str, content: str, context: ToolContext) -> str:
    # 调用 MemoryManager.append(category, content)
    # 返回确认信息
```

### 7.7 CLI 命令

| 命令 | 描述 |
|---|---|
| `/memory` | 显示当前长期记忆内容 |
| `/memory clear` | 清空长期记忆（需确认） |
| `/memory edit` | 用外部编辑器打开 MEMORY.md |

### 7.8 配置

```yaml
# config.yaml
memory:
  enabled: true                    # 是否启用长期记忆
  file: "MEMORY.md"                # 记忆文件路径（相对于项目根目录）
  auto_inject: true                # 是否自动注入 system prompt
  trigger_words:                   # 触发关键词（可自定义）
    - "记住"
    - "记一下"
    - "记着"
    - "别忘了"
    - "remember"
    - "keep in mind"
```

---

## 8. Agent Loop（loop.py）

### 8.1 ReAct 循环逻辑

```
输入：用户消息
  ↓
追加到 messages（role=user）
  ↓
┌─────────────────────────────────┐
│  while iteration < max_iter:    │
│    LLM.chat(messages, tools)    │
│    ↓                            │
│    有 tool_calls?                │
│    ├─ Yes → 执行工具             │
│    │         追加 tool 结果      │
│    │         continue           │
│    └─ No  → 这是最终回答        │
│              追加 assistant msg │
│              break              │
└─────────────────────────────────┘
  ↓
返回最终回答给 CLI 显示
```

### 8.2 loop.py 接口

```python
class AgentLoop:
    def __init__(self, config: AgentConfig, session: Session): ...

    def run(self, user_input: str) -> str:
        """
        执行一轮 Agent Loop。
        - 接收用户输入
        - 修改 session.messages（in-place）
        - 返回最终回答文本
        """

    def stream_run(self, user_input: str) -> Generator[str, None, None]:
        """流式版本，逐 token yield 最终回答"""
```

### 8.3 Messages 管理

- 每次 `run()` 将用户输入追加到 `session.messages`
- 工具调用过程中的中间消息（assistant tool_calls + tool results）也追加进去
- 最终回答的 assistant 消息追加进去
- 整个 messages 列表即为完整对话历史，保存在 Session 中

---

## 9. Session 管理（session.py）

### 9.1 Session 数据结构

每个 Session 对应 `.sessions/<session-id>.json`：

```json
{
  "id": "20240420-143022-abc123",
  "created_at": "2024-04-20T14:30:22Z",
  "updated_at": "2024-04-20T15:10:05Z",
  "title": "用户对话摘要（取首条消息前30字）",
  "work_dir": ".",
  "messages": [
    {"role": "system", "content": "..."},
    {"role": "user", "content": "..."},
    {"role": "assistant", "content": "..."}
  ]
}
```

Session 索引 `.sessions/index.json`：

```json
{
  "sessions": [
    {
      "id": "20240420-143022-abc123",
      "title": "...",
      "created_at": "...",
      "updated_at": "..."
    }
  ]
}
```

### 9.2 Session ID 生成

```
格式：YYYYMMDD-HHMMSS-<随机6位十六进制>
示例：20240420-143022-a3f7b1
```

### 9.3 SessionManager 接口

```python
class SessionManager:
    def new_session(self) -> Session: ...
    def load_session(self, session_id: str) -> Session: ...
    def save_session(self, session: Session) -> None: ...
    def list_sessions(self) -> list[SessionMeta]: ...
    def delete_session(self, session_id: str) -> None: ...
    def get_latest_session(self) -> Session | None: ...
```

### 9.4 Session 生命周期

```
程序启动
  → 无 --session 参数：创建新 Session
  → 有 --session <id>：加载已有 Session（恢复历史）
  → 有 --resume：加载最近一次 Session

每轮对话结束后（auto_save=true）：
  → session.save()（更新文件 + 索引）

程序退出：
  → 最终 save
```

---

## 10. CLI 设计（cli.py）

### 10.1 启动方式

```bash
# 启动新会话
python main.py

# 恢复最近会话
python main.py --resume

# 恢复指定会话
python main.py --session 20240420-143022-a3f7b1

# 直接执行单条指令（非交互模式）
python main.py --message "列出当前目录的文件"

# 指定配置文件
python main.py --config /path/to/config.yaml
```

### 10.2 交互式 REPL

启动后进入交互循环，界面风格参考 openclaw：

```
Agent v0.1.0 | Session: 20240420-143022-a3f7b1 | 工作目录: project_class/
输入 /help 查看可用命令

> 你好，列出当前目录的内容

[调用工具] list_dir path="."
[工具结果] agent/  agent-skills/  config.yaml  main.py  ...

当前目录包含以下文件：
- agent/（核心代码）
- agent-skills/（Skill 目录）
- config.yaml（配置文件）
...

> 
```

### 10.3 内置斜杠命令

| 命令 | 描述 |
|---|---|
| `/help` | 显示帮助信息 |
| `/exit` 或 `/quit` | 退出程序 |
| `/session new` | 创建新 Session |
| `/session list` | 列出所有 Session |
| `/session load <id>` | 切换到指定 Session |
| `/session info` | 显示当前 Session 信息 |
| `/history` | 显示当前会话历史 |
| `/clear` | 清空当前会话历史（不删除文件）|
| `/tools` | 显示所有可用工具 |
| `/cd <path>` | 切换工作目录 |
| `/config` | 显示当前配置 |

### 10.4 输出格式

- **工具调用**：灰色前缀 `[调用工具] tool_name args...`
- **工具结果**：灰色前缀 `[工具结果] ...`（超长时截断）
- **最终回答**：正常输出，支持流式打印
- **错误信息**：红色前缀 `[错误] ...`
- **系统提示**：蓝色前缀 `[系统] ...`

使用 `colorama` 库实现跨平台颜色支持。

### 10.5 readline 历史

使用 Python `readline` 模块，支持：
- 上下键浏览历史输入
- 历史保存到 `.sessions/.input_history`，跨会话持久化
- Tab 补全斜杠命令

---

## 11. 主入口（main.py）

```python
def main():
    args = parse_args()           # argparse 解析命令行参数
    config = load_config(args)    # 加载 config.yaml + 环境变量
    session_mgr = SessionManager(config)
    session = resolve_session(args, session_mgr)   # new / load / resume
    loop = AgentLoop(config, session)
    cli = CLI(loop, session, session_mgr, config)
    cli.run()                     # 进入交互循环

if __name__ == "__main__":
    main()
```

---

## 12. 依赖管理

### 12.1 依赖列表（requirements.txt）

```
openai>=1.0.0          # OpenAI SDK（兼容 DeepSeek）
python-dotenv>=1.0.0   # .env 文件支持
pyyaml>=6.0            # config.yaml 解析
colorama>=0.4.6        # 跨平台终端颜色
readline               # 标准库（Linux/Mac）；Windows 用 pyreadline3
```

### 12.2 Python 版本要求

Python >= 3.10（使用了 `match` 语句和 `X | Y` 类型注解）

---

## 13. 实现顺序（分阶段）

### Phase 1：核心可运行
1. `config.py` — 加载 config.yaml + 环境变量
2. `llm.py` — LLM 客户端，支持流式和非流式
3. `tools.py` — 工具注册机制 + 全部内置工具
4. `loop.py` — Agent Loop，基于 Function Calling
5. `main.py` — 基础非交互模式（`--message` 参数）

### Phase 2：CLI 交互
6. `session.py` — Session 持久化
7. `cli.py` — 交互式 REPL + 斜杠命令
8. `main.py` — 完整参数解析和会话恢复

### Phase 3：完善
9. 流式输出集成到 CLI
10. readline 历史和 Tab 补全
11. config.example.yaml 和 .gitignore

### Phase 4：Skill 系统
12. `skills.py` — Skill 发现与加载
13. `select_skill` 工具注册到 tools.py
14. CLI `/skills` 命令
15. 示例 Skill

### Phase 5：长期记忆
16. `memory.py` — MemoryManager 实现
17. `write_memory` 工具注册到 tools.py
18. 触发词检测逻辑（cli.py）
19. System Prompt 注入（loop.py）
20. CLI `/memory` 命令

---

## 14. 测试设计

### 14.1 测试策略

| 层次 | 覆盖范围 | 隔离方式 |
|---|---|---|
| 单元测试 | config / tools / session / llm 响应解析 | 不依赖网络，不依赖真实文件系统（用 tmp_path）|
| 集成测试 | loop + tools + session 联动 | Mock LLM，真实工具执行，临时目录 |
| 端到端测试（可选）| 完整 CLI 流程 | Mock LLM + 临时目录，验证输出 |

**原则**：
- 不调用真实 LLM（无需 API Key 即可运行测试）
- 用 `pytest` + `unittest.mock` 实现 LLM Mock
- 每个测试用例独立，使用 `tmp_path` fixture 隔离文件系统
- 测试文件放在 `tests/` 目录，与 `agent/` 平级

### 14.2 测试目录结构

```
project_class/
└── tests/
    ├── __init__.py
    ├── conftest.py              # 公共 fixture（tmp_path、mock config、mock LLM）
    ├── test_config.py           # 配置加载测试
    ├── test_tools.py            # 工具执行测试
    ├── test_session.py          # Session 管理测试
    ├── test_llm.py              # LLM 响应解析测试（不访问网络）
    ├── test_loop.py             # Agent Loop 集成测试（Mock LLM）
    ├── test_skills.py           # Skill 发现与加载测试
    └── test_memory.py           # 长期记忆测试
```

### 14.3 各模块测试用例

#### config.py 测试（test_config.py）

| 用例 | 说明 |
|---|---|
| `test_default_values` | 无 config.yaml 时，所有字段使用默认值 |
| `test_load_from_yaml` | config.yaml 中的值正确覆盖默认值 |
| `test_env_var_overrides_yaml` | 环境变量优先级高于 yaml |
| `test_env_var_overrides_default` | 无 yaml 时环境变量也能生效 |
| `test_missing_api_key_is_empty` | 未配置 api_key 时返回空字符串而非报错 |
| `test_resolved_work_dir_relative` | 相对路径的 work_dir 正确解析为绝对路径 |
| `test_resolved_work_dir_absolute` | 绝对路径的 work_dir 原样返回 |
| `test_resolved_session_dir` | session.dir 正确解析为绝对路径 |
| `test_formatted_system_prompt` | system_prompt 中 `{work_dir}` 占位符被正确替换 |
| `test_partial_yaml_uses_defaults` | yaml 只写部分字段，其余仍使用默认值 |

#### tools.py 测试（test_tools.py）

| 用例 | 说明 |
|---|---|
| `test_read_file_success` | 正常读取已有文件，返回完整内容 |
| `test_read_file_not_found` | 文件不存在时返回含 `[错误]` 的字符串 |
| `test_read_file_with_line_range` | `start_line` / `max_lines` 参数生效 |
| `test_write_file_creates_file` | 写入新文件，文件确实被创建且内容正确 |
| `test_write_file_overwrite` | 覆盖模式下，旧内容被替换 |
| `test_write_file_append` | append=true 时内容追加而非覆盖 |
| `test_write_file_creates_parent_dir` | 目标目录不存在时自动创建 |
| `test_list_dir_returns_entries` | 列出目录条目，包含文件和子目录标记 |
| `test_list_dir_hidden_files` | show_hidden=false 时不显示 `.` 开头条目 |
| `test_list_dir_not_found` | 目录不存在时返回含 `[错误]` 的字符串 |
| `test_change_dir_success` | 切换到已有目录，ctx.work_dir 被更新 |
| `test_change_dir_not_found` | 目录不存在时返回错误，ctx.work_dir 不变 |
| `test_change_dir_affects_subsequent_tools` | change_dir 后，read_file 使用新目录解析路径 |
| `test_shell_success` | 执行合法命令，返回 stdout |
| `test_shell_stderr` | 命令有 stderr 输出时也被返回 |
| `test_shell_nonzero_exit` | 非零退出码时返回中包含退出码信息 |
| `test_shell_timeout` | 超时时返回含超时提示的错误字符串 |
| `test_search_files_by_pattern` | glob 模式匹配，返回匹配文件列表 |
| `test_search_files_with_keyword` | content_keyword 过滤，只返回含关键词的文件 |
| `test_search_files_not_found` | 无匹配时返回提示字符串 |
| `test_execute_tool_unknown` | 调用不存在的工具名返回 `[错误]` 而不抛异常 |
| `test_tool_exception_is_caught` | 工具内部抛出异常时，execute_tool 返回错误字符串 |

#### session.py 测试（test_session.py）

| 用例 | 说明 |
|---|---|
| `test_new_session_has_unique_id` | 连续创建两个 Session，ID 不相同 |
| `test_new_session_id_format` | Session ID 符合 `YYYYMMDD-HHMMSS-xxxxxx` 格式 |
| `test_save_and_load_roundtrip` | 保存后加载，messages 和元信息完整还原 |
| `test_save_creates_index` | 首次保存后 index.json 被创建 |
| `test_save_updates_index` | 多次保存同一 Session，index 中只有一条记录 |
| `test_list_sessions_sorted` | list_sessions 按 updated_at 降序排列 |
| `test_load_nonexistent_raises` | 加载不存在的 ID 抛出 FileNotFoundError |
| `test_delete_session` | 删除后文件消失，index 中也无记录 |
| `test_delete_nonexistent_returns_false` | 删除不存在的 ID 返回 False，不报错 |
| `test_get_latest_session` | 返回最近更新的 Session |
| `test_get_latest_session_empty` | 无任何记录时返回 None |
| `test_auto_title_from_first_user_message` | 首条 user 消息自动成为 title |
| `test_touch_updates_updated_at` | touch() 后 updated_at 变为当前时间 |

#### llm.py 测试（test_llm.py）

> 本模块不访问真实网络，仅测试响应解析逻辑（Mock `OpenAI` 客户端）。

| 用例 | 说明 |
|---|---|
| `test_blocking_response_content` | 非流式响应正确提取 content 文本 |
| `test_blocking_response_tool_calls` | 非流式响应正确解析 tool_calls（含 arguments JSON）|
| `test_blocking_response_no_tool_calls` | 无 tool_calls 时，has_tool_calls 为 False |
| `test_blocking_to_message` | to_message() 返回正确的 assistant dict |
| `test_streaming_response_content` | 流式响应拼接后 content 正确 |
| `test_streaming_response_tool_calls` | 流式 tool_calls 各 chunk 正确合并 |
| `test_streaming_stream_text` | stream_text() 逐 chunk yield 文本 |

#### loop.py 测试（test_loop.py）

> 使用 Mock LLM，不调用真实 API。

| 用例 | 说明 |
|---|---|
| `test_direct_answer_no_tools` | LLM 直接回答（无 tool_calls），messages 中只有 user + assistant |
| `test_system_prompt_injected` | 首次 run() 后 messages[0] 是 system 消息 |
| `test_single_tool_call` | LLM 返回一次工具调用，工具执行后再次调用 LLM 得到最终回答 |
| `test_multi_tool_calls_in_one_turn` | 单次响应包含多个 tool_calls，全部执行后继续 |
| `test_multiple_iterations` | 需要多轮工具调用才能得到最终回答 |
| `test_max_iterations_reached` | 超过 max_iterations 时返回警告字符串 |
| `test_messages_appended_correctly` | 验证 messages 的 role 序列：system/user/assistant/tool.../assistant |
| `test_tool_error_does_not_stop_loop` | 工具执行出错时，loop 继续而非崩溃 |
| `test_on_tool_call_callback_fired` | on_tool_call 回调在工具调用前被触发 |
| `test_on_tool_result_callback_fired` | on_tool_result 回调在工具执行后被触发 |
| `test_stream_run_yields_tokens` | stream_run() 正确 yield 最终回答的各 token |
| `test_context_work_dir_updated_by_change_dir` | change_dir 工具修改后，loop.tool_ctx.work_dir 随之更新 |

#### skills.py 测试（test_skills.py）

| 用例 | 说明 |
|---|---|
| `test_discover_finds_skill_dirs` | 包含 skill.md 的目录被正确发现 |
| `test_discover_ignores_empty_dirs` | 没有 skill.md 的目录被跳过 |
| `test_discover_ignores_files` | skills/ 下的普通文件被忽略 |
| `test_parse_frontmatter` | 正确解析 skill.md 的 name 和 description |
| `test_parse_frontmatter_missing_fields` | frontmatter 缺少字段时使用默认值（目录名作为 name） |
| `test_parse_no_frontmatter` | 无 frontmatter 时使用目录名和空描述 |
| `get_skill_by_name` | 按名称查找 Skill 成功 |
| `get_skill_not_found` | 查找不存在的 Skill 返回 None |
| `get_skill_summaries_format` | 摘要格式正确（name + description 列表） |
| `select_skill_loads_content` | select_skill 工具返回完整 skill.md 内容 |
| `select_skill_not_found` | select_skill 工具对不存在的 Skill 返回错误 |

#### memory.py 测试（test_memory.py）

| 用例 | 说明 |
|---|---|
| `test_load_empty_when_no_file` | MEMORY.md 不存在时返回空字符串 |
| `test_load_reads_content` | 正确读取 MEMORY.md 的完整内容 |
| `test_save_creates_file` | 首次写入时创建 MEMORY.md 文件 |
| `test_save_overwrites_content` | 覆盖写入，旧内容被替换 |
| `test_append_to_existing_category` | 向已有分类追加条目 |
| `test_append_creates_new_category` | 分类不存在时自动创建 |
| `test_get_all_parses_categories` | 正确解析各分类及其条目 |
| `test_get_all_empty_file` | 空文件返回空字典 |
| `test_write_memory_tool` | write_memory 工具调用 append 并返回确认信息 |
| `test_memory_injected_to_system_prompt` | 新 Session 的 system prompt 包含 MEMORY.md 内容 |
| `test_trigger_word_detected` | 包含"记住"的消息被正确识别 |
| `test_no_trigger_word` | 不含触发词的消息不触发记忆写入 |

### 14.4 公共 Fixture（conftest.py）

```python
# tests/conftest.py

@pytest.fixture
def tmp_work_dir(tmp_path):
    """临时工作目录，隔离文件系统操作。"""
    return tmp_path

@pytest.fixture
def tool_ctx(tmp_work_dir):
    """预配置好的 ToolContext，工作目录指向临时目录。"""
    return ToolContext(work_dir=tmp_work_dir, session_id="test-session")

@pytest.fixture
def default_config(tmp_work_dir, tmp_path):
    """返回测试用 AgentConfig（无需真实 config.yaml）。"""
    cfg = AgentConfig()
    cfg.llm.api_key = "test-key"
    cfg.work_dir = str(tmp_work_dir)
    cfg.project_root = tmp_work_dir
    cfg.session.dir = str(tmp_path / ".sessions")
    return cfg

@pytest.fixture
def session_mgr(tmp_path):
    """指向临时目录的 SessionManager。"""
    return SessionManager(tmp_path / ".sessions")

@pytest.fixture
def mock_llm_direct_answer():
    """Mock LLMClient：直接返回文本，无工具调用。"""
    # 返回固定文本 "这是回答"
    ...

@pytest.fixture
def mock_llm_one_tool_call():
    """Mock LLMClient：第一次返回工具调用，第二次返回最终回答。"""
    ...
```

### 14.5 运行方式

```bash
# 安装测试依赖
pip install pytest pytest-cov

# 运行所有测试
cd project_class
pytest tests/ -v

# 运行单个模块测试
pytest tests/test_tools.py -v

# 生成覆盖率报告
pytest tests/ --cov=agent --cov-report=term-missing
```

### 14.6 测试依赖补充（requirements.txt）

```
pytest>=7.0
pytest-cov>=4.0
```

---

## 15. 关键设计决策说明

| 决策 | 理由 |
|---|---|
| 使用 OpenAI Function Calling 格式 | 比原始 ```json 文本解析更可靠，DeepSeek 完全支持，结构化 tool_call_id 便于追踪 |
| Session 用 JSON 文件存储 | 简单、可读、无需数据库依赖，参考 openclaw sessions 目录的设计思路 |
| ToolContext 传入工具函数 | 工具可访问当前工作目录等状态，change_dir 修改的目录对后续工具生效 |
| config.yaml + 环境变量双轨 | yaml 适合复杂配置，环境变量便于 CI/部署场景覆盖，.env 保护敏感信息 |
| 使用 openai SDK 而非 langchain | 减少依赖链，直接控制 API 调用行为，便于调试；原始代码的 langchain 主要用于工具包装，可直接替代 |
| 工作目录锁定在 project_class/ | 明确边界，避免工具操作影响父目录；`change_dir` 只在此范围内生效（可配置是否允许越界）|
| Observation 用 SQLite 存储 | 结构化数据支持 FTS5/向量检索/去重/统计，纯 Markdown 无法做到。参考 Claude-Mem 的 observations 表 |
| FTS5 + ChromaDB 双路检索 | FTS5 做关键词精确匹配，ChromaDB 做语义模糊匹配，互补覆盖。FTS5 不可用时降级 LIKE |
| 本地 embedding (all-MiniLM-L6-v2) | 零 API 费用，离线可用，384 维足够。缺点是首次下载 ~80MB + torch ~500MB |
| 晋升到 MEMORY.md | 与现有长期记忆系统兼容，人类可读，不引入额外存储。晋升内容由 LLM 压缩为一句话 |
| Session 结束时提取 Observation | 不影响对话流畅度，单次批量提取比每轮提取 API 成本低。参考 Claude-Mem 的 SessionEnd hook |
| 每日记忆是只读视图 | 从 SQLite 查询当天 observation 渲染为 Markdown，不是独立存储层，避免数据冗余 |

---

## 16. Observation 记忆系统（observation.py）

### 16.1 概述

Observation 是结构化的记忆单元，替代纯文本 MEMORY.md 成为记忆的主存储。每个 Observation 从一次 Session 对话中由 LLM 提取，存入 SQLite，支持 FTS5 全文检索和 ChromaDB 向量检索。

**设计参考**：Claude-Mem 的 observations 表结构（TypeScript），简化为 Python 实现。

### 16.2 数据结构

```python
@dataclass
class Observation:
    id: str                       # UUID
    type: str                     # bugfix | feature | refactor | change | discovery | decision
    title: str                    # 一句话标题（<50字）
    narrative: str                # 详细描述（1-3 段）
    facts: list[str]              # 关键事实列表（每条一句话）
    concepts: list[str]           # 概念标签（如 "api-design", "error-handling"）
    files_read: list[str]         # 本次涉及的读取文件
    files_modified: list[str]     # 本次涉及的修改文件
    session_id: str               # 来源 Session ID
    created_at: str               # ISO-8601 时间戳
    relevance_count: int = 0      # 被检索引用次数（晋升用）
    content_hash: str = ""        # 去重哈希（SHA-256 of session_id + title + narrative，截取16位）
```

### 16.3 SQLite Schema

```sql
CREATE TABLE IF NOT EXISTS observations (
    id TEXT PRIMARY KEY,
    type TEXT NOT NULL,
    title TEXT NOT NULL,
    narrative TEXT NOT NULL,
    facts TEXT NOT NULL,           -- JSON array
    concepts TEXT NOT NULL,        -- JSON array
    files_read TEXT NOT NULL,      -- JSON array
    files_modified TEXT NOT NULL,  -- JSON array
    session_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    relevance_count INTEGER DEFAULT 0,
    content_hash TEXT NOT NULL UNIQUE  -- 去重约束
);

CREATE INDEX IF NOT EXISTS idx_obs_type ON observations(type);
CREATE INDEX IF NOT EXISTS idx_obs_session ON observations(session_id);
CREATE INDEX IF NOT EXISTS idx_obs_created ON observations(created_at);
```

**去重策略**：`content_hash = SHA-256(session_id + title + narrative)[:16]`，INSERT 使用 `ON CONFLICT(content_hash) DO NOTHING`。

### 16.4 ObservationStore 接口

```python
class ObservationStore:
    def __init__(self, db_path: Path): ...

    def insert(self, obs: Observation) -> bool:
        """插入一条 observation。去重时返回 False。"""

    def insert_batch(self, observations: list[Observation]) -> int:
        """批量插入，返回实际新增条数。"""

    def get_by_id(self, obs_id: str) -> Observation | None: ...

    def get_by_session(self, session_id: str) -> list[Observation]: ...

    def get_recent(self, limit: int = 20) -> list[Observation]:
        """按 created_at 降序返回最近的 observation。"""

    def increment_relevance(self, obs_id: str) -> None:
        """relevance_count += 1。被 memory_search 检索命中时调用。"""

    def get_promotable(self, threshold: int = 3) -> list[Observation]:
        """返回 relevance_count >= threshold 且尚未晋升的 observation。"""

    def mark_promoted(self, obs_id: str) -> None:
        """标记为已晋升。"""

    def count(self) -> int: ...
```

### 16.5 Observation 提取流程（extractor.py）

Session 结束时，用 LLM 从对话历史中提取结构化 observation：

```
Session 结束（/exit、/session new、程序退出）
  ↓
获取 session.messages（完整对话历史）
  ↓
构建提取 prompt：
  "请从以下对话中提取关键信息，以 JSON 数组格式返回。
   每条包含：type, title, narrative, facts, concepts, files_read, files_modified。
   类型包括：bugfix, feature, refactor, change, discovery, decision。
   只提取有价值的信息，忽略寒暄和简单问答。"
  ↓
调用 LLM（非流式，temperature=0.3）
  ↓
解析 JSON 响应 → 构建 Observation 对象列表
  ↓
计算 content_hash → ObservationStore.insert_batch()
  ↓
返回新增条数
```

**提取 Prompt 模板**：

```
你是一个信息提取专家。请从以下对话中提取值得长期记住的关键信息。

## 对话历史
{session.messages 格式化为可读文本}

## 输出格式
以 JSON 数组返回，每条包含：
- type: "bugfix" | "feature" | "refactor" | "change" | "discovery" | "decision"
- title: 一句话标题（<50字）
- narrative: 详细描述（1-3段）
- facts: 关键事实列表（每条一句话）
- concepts: 概念标签列表
- files_read: 涉及的读取文件路径列表
- files_modified: 涉及的修改文件路径列表

## 规则
1. 只提取有长期价值的信息，忽略寒暄和简单问答
2. 每条 observation 应是独立完整的，不依赖上下文
3. 如果对话中没有值得提取的信息，返回空数组 []
4. facts 应是可验证的具体事实，不是模糊的总结
```

### 16.6 配置

```yaml
# config.yaml
observation:
  enabled: true
  db_path: ".memory/memory.db"       # SQLite 数据库路径
  extract_model: ""                   # 提取用模型（空则用主模型）
  extract_temperature: 0.3
  max_observations_per_session: 10   # 单次提取上限
```

### 16.7 CLI 命令

| 命令 | 描述 |
|---|---|
| `/memory` | 显示 MEMORY.md 内容（现有） |
| `/memory stats` | 显示 observation 统计（总数、按类型分布、最近 5 条） |
| `/memory search <query>` | 搜索 observation（FTS5 + 向量混合检索） |
| `/memory extract` | 手动触发当前 session 的 observation 提取 |

---

## 17. FTS5 全文检索

### 17.1 概述

SQLite FTS5 提供关键词级别的全文检索，作为向量检索的补充和 fallback。当 ChromaDB 不可用时，FTS5 是唯一的检索手段。

**设计参考**：Claude-Mem 的 `observations_fts` 虚拟表 + 自动同步触发器。

### 17.2 FTS5 虚拟表

```sql
-- FTS5 虚拟表，索引 observation 的文本字段
CREATE VIRTUAL TABLE IF NOT EXISTS observations_fts USING fts5(
    title,
    narrative,
    facts,        -- JSON array，FTS5 会索引其文本内容
    concepts,     -- JSON array
    content='observations',
    content_rowid='rowid'
);
```

### 17.3 自动同步触发器

```sql
-- INSERT 时同步
CREATE TRIGGER IF NOT EXISTS obs_ai AFTER INSERT ON observations BEGIN
    INSERT INTO observations_fts(rowid, title, narrative, facts, concepts)
    VALUES (new.rowid, new.title, new.narrative, new.facts, new.concepts);
END;

-- DELETE 时同步
CREATE TRIGGER IF NOT EXISTS obs_ad AFTER DELETE ON observations BEGIN
    INSERT INTO observations_fts(observations_fts, rowid, title, narrative, facts, concepts)
    VALUES ('delete', old.rowid, old.title, old.narrative, old.facts, old.concepts);
END;

-- UPDATE 时同步
CREATE TRIGGER IF NOT EXISTS obs_au AFTER UPDATE ON observations BEGIN
    INSERT INTO observations_fts(observations_fts, rowid, title, narrative, facts, concepts)
    VALUES ('delete', old.rowid, old.title, old.narrative, old.facts, old.concepts);
    INSERT INTO observations_fts(rowid, title, narrative, facts, concepts)
    VALUES (new.rowid, new.title, new.narrative, new.facts, new.concepts);
END;
```

### 17.4 FTS5 可用性探测

Python 的 sqlite3 模块是否支持 FTS5 取决于编译时链接的 SQLite 版本。需要运行时探测：

```python
def check_fts5_available(conn: sqlite3.Connection) -> bool:
    """尝试创建临时 FTS5 表，成功则说明 FTS5 可用。"""
    try:
        conn.execute("CREATE VIRTUAL TABLE _fts5_probe USING fts5(x)")
        conn.execute("DROP TABLE _fts5_probe")
        return True
    except Exception:
        return False
```

FTS5 不可用时，降级为 `LIKE %query%` 模糊查询。

### 17.5 查询接口

```python
class FTS5Search:
    def __init__(self, conn: sqlite3.Connection): ...

    def search(self, query: str, limit: int = 10) -> list[Observation]:
        """全文检索，按 relevance rank 排序。"""
        # FTS5 可用时：
        #   SELECT o.* FROM observations o
        #   JOIN observations_fts f ON f.rowid = o.rowid
        #   WHERE observations_fts MATCH ?
        #   ORDER BY f.rank
        #   LIMIT ?
        # FTS5 不可用时降级：
        #   SELECT * FROM observations
        #   WHERE title LIKE ? OR narrative LIKE ?
        #   LIMIT ?
```

### 17.6 查询转义

FTS5 特殊字符（`"`, `*`, `(`, `)`, `OR`, `AND`, `NOT`, `NEAR`）需要转义。策略：将用户查询用双引号包裹作为字面短语匹配。

```python
def escape_fts5_query(query: str) -> str:
    """将查询转为 FTS5 字面短语。"""
    escaped = query.replace('"', '""')
    return f'"{escaped}"'
```

---

## 18. 向量检索（vectordb.py）

### 18.1 概述

ChromaDB 提供语义级别的向量检索。每条 observation 的 title + narrative 经 embedding 后存入 ChromaDB，查询时用用户输入做语义匹配。

**设计参考**：Claude-Mem 的 ChromaSync 粒度文档策略，简化为每条 observation 一个文档。

### 18.2 Embedding 模型

使用 `sentence-transformers` 的 `all-MiniLM-L6-v2`：
- 维度：384
- 大小：~80MB（首次使用时自动下载）
- 速度：CPU 上 ~500 条/秒
- 依赖：`sentence-transformers`（会拉取 `torch`，总依赖 ~500MB）

### 18.3 ChromaDB 存储结构

```
Collection: "observations"
Document:   "{title}\n{narrative}"    -- observation 的文本表示
Metadata:   {
    "observation_id": obs.id,
    "type": obs.type,
    "session_id": obs.session_id,
    "created_at": obs.created_at,
    "concepts": ",".join(obs.concepts)   -- ChromaDB metadata 不支持 list，用逗号拼接
}
ID:         obs.id                      -- 与 SQLite 的 observation id 一致
```

### 18.4 VectorStore 接口

```python
class VectorStore:
    def __init__(self, persist_dir: Path): ...

    def add(self, obs: Observation) -> None:
        """将 observation embedding 后存入 ChromaDB。"""

    def add_batch(self, observations: list[Observation]) -> None:
        """批量添加。"""

    def search(self, query: str, limit: int = 10) -> list[tuple[str, float]]:
        """语义检索，返回 (observation_id, distance) 列表。"""

    def delete(self, obs_id: str) -> None: ...

    def count(self) -> int: ...
```

### 18.5 Embedding 封装

```python
class EmbeddingModel:
    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        from sentence_transformers import SentenceTransformer
        self._model = SentenceTransformer(model_name)

    def embed(self, text: str) -> list[float]: ...
    def embed_batch(self, texts: list[str]) -> list[list[float]]: ...
```

ChromaDB 支持自定义 embedding function，将 `EmbeddingModel` 适配为 ChromaDB 的 `EmbeddingFunction` 接口。

### 18.6 同步策略

Observation 写入 SQLite 后，同步写入 ChromaDB：

```
extractor 提取 observation
  ↓
ObservationStore.insert_batch() → SQLite（去重）
  ↓
仅对实际新增的 observation → VectorStore.add_batch() → ChromaDB
```

**启动时补全**：程序启动时，检查 SQLite 和 ChromaDB 的数量差异，将缺失的 observation 补充到 ChromaDB。

### 18.7 配置

```yaml
# config.yaml
vectordb:
  enabled: true
  persist_dir: ".memory/chroma"      # ChromaDB 持久化目录
  embedding_model: "all-MiniLM-L6-v2"
  collection_name: "observations"
```

### 18.8 依赖

```
chromadb>=0.4.0
sentence-transformers>=2.0.0
```

> **注意**：`sentence-transformers` 会拉取 `torch`，首次安装约 500MB。如果用户不需要向量检索，可通过 `vectordb.enabled: false` 跳过。

---

## 19. 统一检索与晋升机制（memory_search.py）

### 19.1 概述

`MemorySearch` 编排 FTS5 和 ChromaDB 两条检索路径，合并结果去重后注入 system prompt。同时追踪 observation 的被引用次数，驱动晋升机制。

### 19.2 检索流程

```
每轮对话开始前（AgentLoop.run() 入口）
  ↓
MemorySearch.search(user_input, limit=5)
  ├─ ChromaDB 语义检索 → top-K 结果 (observation_id, distance)
  ├─ FTS5 关键词检索 → top-K 结果 (observation_id, rank)
  └─ 合并去重 → 按综合得分排序 → 取 top-N
  ↓
对命中的 observation 调用 increment_relevance()
  ↓
格式化为 context 文本 → 注入 system prompt 尾部
```

### 19.3 混合检索策略

```python
class MemorySearch:
    def __init__(self, store: ObservationStore, fts: FTS5Search, vectordb: VectorStore | None): ...

    def search(self, query: str, limit: int = 5) -> list[Observation]:
        """
        混合检索：
        1. 向量检索 top-K（如果 vectordb 可用）
        2. FTS5 检索 top-K
        3. 合并：同一 observation 在两条路径都命中时，取更高排名
        4. 按综合得分排序，返回 top-limit
        """
```

**Fallback 链**：ChromaDB 可用 → 向量 + FTS5 混合；ChromaDB 不可用 → FTS5 单路；FTS5 不可用 → LIKE 降级。

### 19.4 System Prompt 注入格式

```python
def format_memory_context(observations: list[Observation]) -> str:
    """将检索结果格式化为 system prompt 注入文本。"""
    # 输出格式：
    # # 相关记忆
    # 以下是与当前对话相关的历史记忆，请参考：
    #
    # ## [bugfix] 修复 API 超时问题
    # 在调用 DeepSeek API 时需要设置 timeout=60，否则长对话会超时。
    # - 事实：DeepSeek API 默认无超时限制
    # - 概念：api-design, error-handling
    # - 涉及文件：agent/llm.py
    #
    # ## [decision] 使用 OpenAI Function Calling 格式
    # ...
```

### 19.5 晋升机制

**晋升条件**：`relevance_count >= threshold`（默认 threshold=3）

**晋升流程**：

```
MemorySearch 检索命中 observation
  ↓
increment_relevance(obs_id)
  ↓
relevance_count >= threshold?
  ├─ 否 → 继续
  └─ 是 → promote(obs)
          ↓
          LLM 将 observation 压缩为一句话
          ↓
          MemoryManager.append(category, content)
          （追加到 MEMORY.md 对应分类）
          ↓
          ObservationStore.mark_promoted(obs_id)
```

**晋升分类映射**：

| Observation type | MEMORY.md 分类 |
|---|---|
| bugfix | 项目约束 |
| feature | 历史上下文 |
| decision | 项目约束 |
| discovery | 历史上下文 |
| refactor | 历史上下文 |
| change | 历史上下文 |

**晋升 Prompt**：

```
请将以下 observation 压缩为一句话（<30字），用于写入长期记忆文件。

标题：{obs.title}
描述：{obs.narrative}
事实：{obs.facts}

只输出压缩后的一句话，不要其他内容。
```

### 19.6 接口

```python
class MemorySearch:
    def search(self, query: str, limit: int = 5) -> list[Observation]: ...

    def check_and_promote(self, observations: list[Observation], llm_client: LLMClient) -> int:
        """检查命中的 observation 是否达到晋升阈值，执行晋升。返回晋升条数。"""

    def get_stats(self) -> dict:
        """返回记忆系统统计信息。"""
        # {
        #   "total_observations": 42,
        #   "by_type": {"bugfix": 10, "feature": 15, ...},
        #   "promoted_count": 5,
        #   "fts5_available": true,
        #   "vectordb_available": true,
        #   "vectordb_count": 40
        # }
```

### 19.7 配置

```yaml
# config.yaml
memory_search:
  enabled: true
  auto_search: true               # 每轮对话自动检索
  search_limit: 5                 # 注入 system prompt 的最大条数
  promotion_threshold: 3          # relevance_count 达到此值时晋升
  auto_promote: true              # 是否自动晋升（false 时仅提醒）
```

---

## 20. 每日记忆视图

### 20.1 概述

每日记忆不是独立存储层，而是从 SQLite 查询当天 observation 后渲染的只读 Markdown 视图。

### 20.2 生成逻辑

```python
def generate_daily_memory(date: str, store: ObservationStore) -> str:
    """生成指定日期的每日记忆 Markdown。"""
    observations = store.get_by_date(date)  # WHERE created_at LIKE '2026-05-20%'
    if not observations:
        return f"# {date} 每日记忆\n\n今天没有新的记忆。\n"

    lines = [f"# {date} 每日记忆\n"]
    for obs in observations:
        lines.append(f"## [{obs.type}] {obs.title}")
        lines.append(f"\n{obs.narrative}\n")
        if obs.facts:
            lines.append("**事实**：")
            for fact in obs.facts:
                lines.append(f"- {fact}")
        lines.append(f"\n*来源 Session: {obs.session_id}*\n")
    return "\n".join(lines)
```

### 20.3 CLI 命令

| 命令 | 描述 |
|---|---|
| `/memory today` | 显示今天的每日记忆 |
| `/memory day <YYYY-MM-DD>` | 显示指定日期的每日记忆 |
| `/memory export <YYYY-MM-DD>` | 将指定日期的记忆导出为 .md 文件 |

---

## 21. 模块依赖关系

```
main.py
  └── cli.py
        ├── loop.py (AgentLoop)
        │     ├── llm.py (LLMClient)
        │     ├── tools.py (ToolRegistry)
        │     ├── session.py (SessionManager)
        │     ├── memory.py (MemoryManager) ← MEMORY.md 读写
        │     ├── memory_search.py (MemorySearch) ← 每轮自动检索
        │     │     ├── observation.py (ObservationStore) ← SQLite + FTS5
        │     │     ├── vectordb.py (VectorStore) ← ChromaDB
        │     │     └── memory.py (MemoryManager) ← 晋升写入
        │     └── extractor.py (ObservationExtractor) ← Session 结束时提取
        │           ├── llm.py
        │           └── observation.py
        └── config.py
```

---

## 22. 实现顺序（更新）

### Phase 1：核心可运行
1. `config.py` — 加载 config.yaml + 环境变量
2. `llm.py` — LLM 客户端，支持流式和非流式
3. `tools.py` — 工具注册机制 + 全部内置工具
4. `loop.py` — Agent Loop，基于 Function Calling
5. `main.py` — 基础非交互模式（`--message` 参数）

### Phase 2：CLI 交互
6. `session.py` — Session 持久化
7. `cli.py` — 交互式 REPL + 斜杠命令
8. `main.py` — 完整参数解析和会话恢复

### Phase 3：完善
9. 流式输出集成到 CLI
10. readline 历史和 Tab 补全
11. config.example.yaml 和 .gitignore

### Phase 4：Skill 系统
12. `skills.py` — Skill 发现与加载
13. `select_skill` 工具注册到 tools.py
14. CLI `/skills` 命令
15. 示例 Skill

### Phase 5：长期记忆（MEMORY.md）
16. `memory.py` — MemoryManager 实现
17. `write_memory` 工具注册到 tools.py
18. 触发词检测逻辑（cli.py）
19. System Prompt 注入（loop.py）
20. CLI `/memory` 命令

### Phase 6：Observation 存储层
21. `observation.py` — ObservationStore + SQLite schema + FTS5 虚拟表
22. Observation 数据结构和去重逻辑
23. FTS5 可用性探测 + 降级 LIKE 查询
24. CLI `/memory stats` 命令

### Phase 7：向量检索
25. `vectordb.py` — ChromaDB 封装 + EmbeddingModel
26. 启动时补全逻辑（SQLite → ChromaDB 同步）
27. `memory_search.py` — 混合检索编排（向量 + FTS5）
28. 每轮自动检索 + system prompt 注入（loop.py 集成）

### Phase 8：Observation 提取
29. `extractor.py` — LLM 提取 prompt + JSON 解析
30. Session 结束时自动提取（cli.py 集成）
31. CLI `/memory extract` 手动触发
32. CLI `/memory search <query>` 命令

### Phase 9：晋升机制与每日记忆
33. `memory_search.py` — relevance_count 追踪 + 晋升逻辑
34. 晋升 prompt（LLM 压缩 observation → MEMORY.md）
35. CLI `/memory today` + `/memory day <date>` 每日记忆视图
36. CLI `/memory export` 导出

---

## 23. 依赖管理（更新）

### 23.1 依赖列表（requirements.txt）

```
openai>=1.0.0              # OpenAI SDK（兼容 DeepSeek）
python-dotenv>=1.0.0       # .env 文件支持
pyyaml>=6.0                # config.yaml 解析
colorama>=0.4.6            # 跨平台终端颜色
readline                   # 标准库（Linux/Mac）；Windows 用 pyreadline3
chromadb>=0.4.0            # 向量数据库
sentence-transformers>=2.0.0  # 本地 embedding 模型
```

### 23.2 可选依赖

```
# 如果不需要向量检索，可以只安装核心依赖
# pip install openai python-dotenv pyyaml colorama
# 此时 vectordb.enabled 设为 false，仅使用 FTS5 检索
```

### 23.3 Python 版本要求

Python >= 3.10（使用了 `match` 语句和 `X | Y` 类型注解）

---

## 24. 测试设计（更新）

### 24.1 新增测试文件

```
tests/
├── test_observation.py      # ObservationStore 单元测试
├── test_fts5.py             # FTS5 检索测试
├── test_vectordb.py         # VectorStore 测试（Mock ChromaDB）
├── test_memory_search.py    # 混合检索 + 晋升集成测试
└── test_extractor.py        # Observation 提取测试（Mock LLM）
```

### 24.2 新增测试用例

#### observation.py 测试（test_observation.py）

| 用例 | 说明 |
|---|---|
| `test_insert_and_get` | 插入后按 ID 查询，字段完整 |
| `test_insert_duplicate_hash` | 相同 content_hash 的第二次插入被跳过 |
| `test_insert_batch` | 批量插入，返回实际新增条数 |
| `test_get_by_session` | 按 session_id 查询返回正确列表 |
| `test_get_recent_order` | get_recent 按 created_at 降序 |
| `test_increment_relevance` | 调用后 relevance_count +1 |
| `test_get_promotable` | 只返回 relevance_count >= threshold 的条目 |
| `test_mark_promoted` | 标记后不再出现在 get_promotable 中 |

#### fts5.py 测试（test_fts5.py）

| 用例 | 说明 |
|---|---|
| `test_fts5_available` | 探测函数在支持 FTS5 的环境中返回 True |
| `test_search_by_keyword` | 精确关键词匹配返回相关 observation |
| `test_search_ranking` | 更相关的排在前面 |
| `test_escape_special_chars` | FTS5 特殊字符被正确转义 |
| `test_fallback_to_like` | FTS5 不可用时降级为 LIKE 查询 |

#### vectordb.py 测试（test_vectordb.py）

| 用例 | 说明 |
|---|---|
| `test_add_and_search` | 添加后语义检索能找到 |
| `test_search_returns_ids_and_scores` | 返回格式正确 |
| `test_delete` | 删除后检索不到 |
| `test_count` | 添加 N 条后 count == N |

#### memory_search.py 测试（test_memory_search.py）

| 用例 | 说明 |
|---|---|
| `test_hybrid_search_merges_results` | 向量 + FTS5 结果正确合并 |
| `test_search_increments_relevance` | 检索命中后 relevance_count 增加 |
| `test_promotion_triggered` | 达到阈值时自动晋升到 MEMORY.md |
| `test_promotion_not_duplicated` | 已晋升的不再重复晋升 |
| `test_stats_format` | 统计信息格式正确 |

#### extractor.py 测试（test_extractor.py）

| 用例 | 说明 |
|---|---|
| `test_extract_valid_json` | LLM 返回合法 JSON 时正确解析为 Observation |
| `test_extract_empty_array` | 对话无有价值信息时返回空列表 |
| `test_extract_invalid_json` | LLM 返回非法 JSON 时返回空列表（不崩溃） |
| `test_content_hash_dedup` | 相同内容的 observation 有相同 hash |
