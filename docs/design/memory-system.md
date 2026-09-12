# 记忆系统架构分析

## 概览

本 Agent 的记忆系统采用**双层架构**：短期结构化记忆（Observation）和长期平坦记忆（MEMORY.md）。两层之间通过"晋升机制"连接——高频访问的 Observation 会被 LLM 压缩后写入长期记忆。

```
用户对话
  │
  ▼
┌─────────────────────────────────────────────────────┐
│  Session 结束时：ObservationExtractor 提取结构化记忆  │
│  ──→ SQLite + ChromaDB                               │
└──────────────────┬──────────────────────────────────┘
                   │
          每次对话自动检索 (MemorySearch)
                   │
        relevance_count 累加 ≥ 3 时
                   │
                   ▼
┌─────────────────────────────────────────────────────┐
│  自动晋升：LLM 压缩 → 写入 MEMORY.md（长期记忆）     │
└─────────────────────────────────────────────────────┘
```

## 组件清单

| 组件 | 文件 | 职责 |
|------|------|------|
| MemoryManager | `agent/memory.py` | 管理 MEMORY.md 的读写 |
| ObservationStore | `agent/observation.py` | SQLite + FTS5 结构化存储 |
| VectorStore | `agent/vectordb.py` | ChromaDB 语义向量检索 |
| MemorySearch | `agent/memory_search.py` | 混合检索编排 + 晋升驱动 |
| ObservationExtractor | `agent/extractor.py` | LLM 驱动的记忆提取 |
| AgentLoop | `agent/loop.py` | 记忆注入 system prompt |
| CLI | `agent/cli.py` | 用户命令入口 |
| tools.py | `agent/tools.py` | Agent 可调用的记忆工具 |

---

## 第一层：结构化记忆（Observation）

### 存储：ObservationStore

SQLite 数据库，路径 `.memory/memory.db`。

**数据模型：**

| 字段 | 类型 | 说明 |
|------|------|------|
| id | TEXT PK | UUID |
| type | TEXT | bugfix / feature / refactor / change / discovery / decision |
| title | TEXT | 一句话标题 |
| narrative | TEXT | 详细描述 |
| facts | TEXT (JSON) | 关键事实列表 |
| concepts | TEXT (JSON) | 概念标签列表 |
| files_read | TEXT (JSON) | 涉及的读取文件 |
| files_modified | TEXT (JSON) | 涉及的修改文件 |
| session_id | TEXT | 来源会话 ID |
| created_at | TEXT | ISO-8601 时间戳 |
| relevance_count | INTEGER | 被检索命中次数 |
| content_hash | TEXT UNIQUE | SHA-256 去重哈希 |
| promoted | INTEGER | 0=未晋升, 1=已晋升 |

**全文检索（FTS5）：**

- 使用 `trigram` 分词器，支持中文短语搜索
- 覆盖字段：title, narrative, facts, concepts
- 通过 INSERT/DELETE/UPDATE 触发器自动同步
- 搜索策略：AND → OR → LIKE 三级降级

**向量检索（VectorStore）：**

- 依赖 ChromaDB + sentence-transformers（`all-MiniLM-L6-v2`）
- 可选组件，未安装时自动降级为 FTS5-only 模式
- 启动时自动同步 SQLite → ChromaDB，补全缺失向量

### 提取：ObservationExtractor

**触发时机：**
- 用户退出会话时自动触发（`CLI._on_session_end`）
- 用户手动执行 `/memory extract`

**提取流程：**
1. 将 session 消息格式化为可读文本
2. 发送给 LLM，要求输出 JSON 数组
3. 解析 JSON，验证 type 合法性（默认 discovery）
4. 分配 UUID、时间戳、content_hash
5. 写入 SQLite（去重）+ ChromaDB（如可用）

**提取 Prompt 要求 LLM 返回：**
```json
[{
  "type": "discovery",
  "title": "一句话标题",
  "narrative": "详细描述",
  "facts": ["事实1", "事实2"],
  "concepts": ["概念1"],
  "files_read": ["path/to/file"],
  "files_modified": []
}]
```

### 检索：MemorySearch

**混合检索策略：**

```
用户查询
  │
  ├──→ VectorStore.search()  ──→ 语义相似度排名
  │
  ├──→ ObservationStore.search_fts()  ──→ 关键词匹配排名
  │
  ▼
合并去重（取更好排名）→ 按分数排序 → Top-N
  │
  ▼
increment_relevance() 累加命中计数
```

**自动注入：** 每次用户发消息时，`AgentLoop.ensure_system_prompt()` 调用 `MemorySearch.search(user_input)`，将结果格式化后注入 system prompt。

---

## 第二层：长期记忆（MEMORY.md）

### 存储：MemoryManager

平坦的 Markdown 文件，按分类组织：

```markdown
## 项目约束
- 某个决策或 bugfix 的压缩摘要

## 历史上下文
- 某个发现或功能的压缩摘要
```

**分类映射：**

| Observation type | MEMORY.md 分类 |
|-----------------|---------------|
| bugfix, decision | 项目约束 |
| feature, discovery, refactor, change | 历史上下文 |

### 写入途径

1. **Agent 工具写入：** 用户说"记住这个"→ 触发词检测 → system hint 注入 → Agent 调用 `write_memory` 工具
2. **自动晋升：** Observation 的 `relevance_count` 达到阈值（默认 3）→ LLM 压缩为一句话 → `MemoryManager.append()` 写入

### 注入方式

`AgentLoop.ensure_system_prompt()` 在每次对话开始时：
1. 加载 MEMORY.md 内容
2. 追加到 system prompt 的"长期记忆"段落

---

## CLI 命令

| 命令 | 功能 | 调用链 |
|------|------|--------|
| `/memory` | 显示 MEMORY.md 内容 | `MemoryManager.load()` |
| `/memory search <q>` | 搜索 Observation | `MemorySearch.search()` |
| `/memory stats` | 显示统计信息 | `MemorySearch.get_stats()` |
| `/memory extract` | 手动提取当前 session | `ObservationExtractor.extract_from_session()` |
| `/memory today` | 显示今天的记忆 | `generate_daily_memory()` |
| `/memory day <date>` | 显示指定日期记忆 | `generate_daily_memory()` |
| `/memory clear` | 清空 MEMORY.md | `MemoryManager.save("")` |
| `/memory edit` | 外部编辑器打开 | `subprocess.run([editor, path])` |

## Agent 工具

| 工具 | 功能 | 调用链 |
|------|------|--------|
| `write_memory` | 写入长期记忆 | `MemoryManager.append()` |
| `search_memory` | 搜索 Observation | `MemorySearch.search()` |
| `get_daily_memory` | 查看每日记忆 | `generate_daily_memory()` |

---

## 配置项

```yaml
# 长期记忆（MEMORY.md）
memory:
  enabled: true
  file: "MEMORY.md"
  auto_inject: true          # 自动注入 system prompt
  trigger_words: ["记住", "记一下", "remember"]

# 结构化记忆（SQLite）
observation:
  enabled: true
  db_path: ".memory/memory.db"
  extract_model: ""          # 空=用主 LLM
  extract_temperature: 0.3
  max_observations_per_session: 10

# 向量检索（ChromaDB，可选）
vectordb:
  enabled: true
  persist_dir: ".memory/chroma"
  embedding_model: "all-MiniLM-L6-v2"
  collection_name: "observations"

# 混合检索 + 晋升
memory_search:
  enabled: true
  auto_search: true          # 每次对话自动检索注入
  search_limit: 5
  promotion_threshold: 3     # 命中几次后晋升
  auto_promote: true
```

---

## 数据流全景

```
┌──────────────────────────────────────────────────────────────────┐
│                        用户发消息                                │
└──────────────┬───────────────────────────────────────────────────┘
               │
               ▼
     ensure_system_prompt()
       │
       ├── 1. 加载 MEMORY.md → 注入 system prompt
       │
       ├── 2. MemorySearch.search(user_input)
       │       ├── VectorStore.search()    [语义]
       │       └── ObservationStore.search_fts() [关键词]
       │       → 合并排序 → 注入 system prompt
       │
       └── 3. check_and_promote()
               └── relevance ≥ 3? → LLM压缩 → MEMORY.md
               │
               ▼
     AgentLoop.run()  ← LLM 带着记忆上下文回答
       │
       ├── Agent 可调用 write_memory / search_memory / get_daily_memory
       │
       ▼
     用户退出 / 新 session
       │
       └── ObservationExtractor.extract_from_session()
             └── LLM 提取 → SQLite + ChromaDB
```

## 存储目录结构

```
.memory/
├── memory.db          # SQLite 数据库（Observation + FTS5）
└── chroma/            # ChromaDB 向量数据库（可选）
```

```
MEMORY.md              # 长期记忆文件（项目根目录）
.sessions/             # 会话持久化目录
├── index.json
└── YYYYMMDD-HHMMSS-xxxxxx.json
```
