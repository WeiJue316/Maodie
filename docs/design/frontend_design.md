# Web 前端设计文档

## 1. 项目概述

为 ReAct Agent CLI 添加 Web 前端，提供可视化仪表盘和聊天界面，让用户通过浏览器与 Agent 交互。

**核心目标**：
- 提供仪表盘主界面，展示会话、记忆、工具日志、Skill 等模块
- 实现聊天界面，支持 SSE 流式输出
- 保持与 CLI 功能一致，通过 API 层连接后端
- 单进程部署，FastAPI 托管前端静态文件

**技术栈**：
| 层级 | 选择 |
|------|------|
| 前端框架 | React 18 + TypeScript |
| 构建工具 | Vite |
| 状态管理 | Redux Toolkit |
| 数据获取 | React Query + fetch |
| 路由 | React Router v6 |
| UI 组件库 | Ant Design 5.x |
| 动画组件库 | React Bits |
| 样式 | Tailwind CSS |
| 后端框架 | FastAPI |
| 流式输出 | SSE |
| 部署 | 单进程（FastAPI 托管静态文件） |

**设计风格**：科技感 + 动态交互 + 高级视觉效果

---

## 2. 项目结构

```
project_class/
├── frontend/                    # 前端代码
│   ├── src/
│   │   ├── components/          # 通用组件
│   │   ├── features/            # 功能模块
│   │   │   ├── session/         # 会话模块
│   │   │   ├── memory/          # 记忆模块
│   │   │   ├── tools/           # 工具日志模块
│   │   │   ├── skill/           # Skill 模块
│   │   │   ├── mcp/             # MCP 模块
│   │   │   ├── orchestrator/    # 多 Agent 编排模块
│   │   │   └── settings/        # 设置模块
│   │   ├── store/               # Redux store
│   │   ├── hooks/               # 自定义 hooks
│   │   ├── services/            # API 请求封装
│   │   ├── types/               # TypeScript 类型定义
│   │   ├── utils/               # 工具函数
│   │   ├── layouts/             # 布局组件
│   │   ├── App.tsx              # 主应用
│   │   └── main.tsx             # 入口
│   ├── index.html
│   ├── package.json
│   ├── tsconfig.json
│   ├── vite.config.ts
│   └── tailwind.config.js
├── agent/
│   ├── api/                     # API 路由（新增）
│   │   ├── __init__.py
│   │   ├── sessions.py          # 会话 API
│   │   ├── memory.py            # 记忆 API
│   │   ├── tools.py             # 工具日志 API
│   │   ├── skills.py            # Skill API
│   │   ├── mcp.py               # MCP API
│   │   ├── orchestrator.py      # 编排器 API
│   │   └── config.py            # 配置 API
│   ├── web.py                   # FastAPI 应用（新增）
│   └── ...                      # 现有模块
└── main.py                      # 入口（新增 --web 参数）
```

---

## 3. 布局设计

### 3.1 主布局

采用侧边栏 + 主区域布局，侧边栏用于模块导航，主区域展示内容。

```
┌─────────────────────────────────────────────────────────┐
│  🔵 Project Agent                               [设置] [?] │
├────────────┬────────────────────────────────────────────┤
│            │                                            │
│  📝 会话     │         主内容区域                          │
│  🧠 记忆     │         (根据左侧选择切换)                   │
│  🔧 工具     │                                            │
│  📦 Skill   │                                            │
│  🔌 MCP     │                                            │
│  🤖 编排     │                                            │
│  ⚙️ 设置     │                                            │
│            │                                            │
│ ────────── │                                            │
│ 📌 快速访问  │                                            │
│  · 最近会话  │                                            │
│  · 收藏记忆  │                                            │
│            │                                            │
│ ────────── │                                            │
│ 会话列表    │                                            │
│  ├ 今天     │                                            │
│  │  ├ 会话A │                                            │
│  │  └ 会话B │                                            │
│  └ 昨天     │                                            │
│    └ 会话C  │                                            │
└────────────┴────────────────────────────────────────────┘
```

### 3.2 会话模块布局（分屏）

```
┌─────────────────────────────────────────────────────────┐
│  🔵 Project Agent                               [设置] [?] │
├────────────┬────────────────────────────────────────────┤
│            │  ┌──────────────┬────────────────────────┐ │
│  📝 会话     │  │              │                        │ │
│  🧠 记忆     │  │  会话列表     │      聊天区             │ │
│  🔧 工具     │  │              │                        │ │
│  📦 Skill   │  │  [+ 新建]    │  ┌──────────────────┐ │ │
│  🔌 MCP     │  │  [🔍 搜索]    │  │ agent: 你好！     │ │ │
│  🤖 编排     │  │              │  │                  │ │ │
│  ⚙️ 设置     │  │  ──────────  │  │ user: 帮我看看... │ │ │
│            │  │  📌 今天      │  │                  │ │ │
│            │  │  ├ 会话A      │  │ agent: 好的，...  │ │ │
│            │  │  └ 会话B      │  │                  │ │ │
│            │  │  📌 昨天      │  │ [输入框]         │ │ │
│            │  │  └ 会话C      │  └──────────────────┘ │ │
│            │  │              │                        │ │
│            │  └──────────────┴────────────────────────┘ │
└────────────┴────────────────────────────────────────────┘
```

### 3.3 聊天区工具调用展示

工具调用以折叠卡片形式展示，默认折叠，点击展开查看详情。

```
┌─────────────────────────────────────────┐
│ 🔵 Agent                                │
│                                         │
│ 好的，我来帮你分析 main.py 的代码结构。     │
│                                         │
│ ┌─────────────────────────────────────┐ │
│ │ 🔧 read_file "main.py"       [展开 ▼] │ │
│ └─────────────────────────────────────┘ │
│                                         │
│ ┌─────────────────────────────────────┐ │
│ │ 🔧 search_files "*.py"       [展开 ▼] │ │
│ └─────────────────────────────────────┘ │
│                                         │
│ 根据分析，main.py 主要包含以下几个部分：   │
│ 1. 版本检查                             │
│ 2. CLI 参数解析                          │
│ 3. 主循环入口                            │
└─────────────────────────────────────────┘
```

展开后：

```
┌─────────────────────────────────────────┐
│ ┌─────────────────────────────────────┐ │
│ │ 🔧 read_file "main.py"       [收起 ▲] │ │
│ │                                     │ │
│ │ 参数: {"path": "main.py"}           │ │
│ │ 耗时: 0.12s                         │ │
│ │ 结果: (前 3 行预览)                   │ │
│ │ ┌───────────────────────────────┐   │ │
│ │ │ #!/usr/bin/env python3       │   │ │
│ │ │ import sys                   │   │ │
│ │ │ from agent.cli import main   │   │ │
│ │ └───────────────────────────────┘   │ │
│ └─────────────────────────────────────┘ │
```

---

## 4. API 设计

### 4.1 会话模块

```
GET    /api/sessions                  — 会话列表
POST   /api/sessions                  — 创建会话
GET    /api/sessions/{id}             — 会话详情
DELETE /api/sessions/{id}             — 删除会话
POST   /api/sessions/{id}/messages    — 发送消息
GET    /api/sessions/{id}/messages    — 消息历史
POST   /api/sessions/{id}/chat        — 流式对话（SSE）
```

### 4.2 长期记忆

```
GET    /api/memory/long-term          — 获取 MEMORY.md
PUT    /api/memory/long-term          — 更新 MEMORY.md
POST   /api/memory/long-term/append   — 追加记忆
```

### 4.3 短期记忆（Observation）

```
GET    /api/memory/observations       — Observation 列表
GET    /api/memory/observations/{id}  — 单条详情
GET    /api/memory/observations/today — 今天的 Observation
GET    /api/memory/observations/date/{date} — 按日期查询
```

### 4.4 混合检索

```
GET    /api/memory/search?q=xxx       — 搜索
POST   /api/memory/search             — 高级搜索
```

### 4.5 晋升

```
GET    /api/memory/promotable         — 可晋升列表
POST   /api/memory/promote/{id}       — 手动晋升
```

### 4.6 Observation 提取

```
POST   /api/memory/extract            — 手动触发提取
POST   /api/memory/extract/{session_id} — 从指定 Session 提取
```

### 4.7 统计

```
GET    /api/memory/stats              — 记忆系统统计
```

### 4.8 工具日志

```
GET    /api/tools/logs                — 调用历史
GET    /api/tools/logs/{id}           — 单条详情
```

### 4.9 Skill

```
GET    /api/skills                    — Skill 列表
GET    /api/skills/{name}             — Skill 详情
GET    /api/skills/{name}/content     — skill.md 内容
GET    /api/skills/available          — 可用 Skill
GET    /api/skills/unavailable        — 不可用 Skill
```

### 4.10 MCP

```
GET    /api/mcp/servers               — MCP Server 状态
GET    /api/mcp/servers/{name}        — 单个 Server 详情
POST   /api/mcp/servers/{name}/reconnect — 重连
GET    /api/mcp/tools                 — 所有 MCP 工具
GET    /api/mcp/tools/{server}        — 指定 Server 的工具
```

### 4.11 多 Agent 编排

```
GET    /api/orchestrator/tasks        — 任务列表
POST   /api/orchestrator/tasks        — 创建任务
GET    /api/orchestrator/tasks/{id}   — 任务状态
POST   /api/orchestrator/tasks/{id}/cancel — 取消任务
GET    /api/orchestrator/agents       — 可用 Agent 列表
```

### 4.12 配置

```
GET    /api/config                    — 获取配置
PUT    /api/config                    — 更新配置
```

---

## 5. SSE 流式输出

### 5.1 协议

使用 Server-Sent Events 实现 LLM 回答的流式输出。

**请求**：
```
POST /api/sessions/{id}/chat
Content-Type: application/json

{
  "content": "用户消息"
}
```

**响应**：
```
Content-Type: text/event-stream

data: {"type": "token", "content": "你"}
data: {"type": "token", "content": "好"}
data: {"type": "tool_call", "name": "read_file", "arguments": {...}}
data: {"type": "tool_result", "name": "read_file", "result": "..."}
data: {"type": "token", "content": "根据分析..."}
data: {"type": "done"}
```

### 5.2 事件类型

| type | 说明 | 数据 |
|------|------|------|
| `token` | LLM 输出的文本片段 | `{content: string}` |
| `tool_call` | 工具调用开始 | `{name: string, arguments: object}` |
| `tool_result` | 工具执行结果 | `{name: string, result: string}` |
| `error` | 错误信息 | `{message: string}` |
| `done` | 流结束 | `{}` |

### 5.3 前端处理

```typescript
const response = await fetch(`/api/sessions/${sessionId}/chat`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ content }),
})

const reader = response.body.getReader()
const decoder = new TextDecoder()

while (true) {
  const { done, value } = await reader.read()
  if (done) break

  const text = decoder.decode(value)
  const lines = text.split('\n')

  for (const line of lines) {
    if (line.startsWith('data: ')) {
      const data = JSON.parse(line.slice(6))
      switch (data.type) {
        case 'token':
          appendToken(data.content)
          break
        case 'tool_call':
          showToolCall(data)
          break
        case 'tool_result':
          showToolResult(data)
          break
        case 'done':
          finishMessage()
          break
      }
    }
  }
}
```

---

## 6. 状态管理

### 6.1 Redux Store 结构

```typescript
// store/index.ts
import { configureStore } from '@reduxjs/toolkit'
import sessionReducer from './sessionSlice'
import memoryReducer from './memorySlice'
import uiReducer from './uiSlice'

export const store = configureStore({
  reducer: {
    session: sessionReducer,
    memory: memoryReducer,
    ui: uiReducer,
  },
})

export type RootState = ReturnType<typeof store.getState>
export type AppDispatch = typeof store.dispatch
```

### 6.2 Session Slice

```typescript
// store/sessionSlice.ts
interface SessionState {
  sessions: Session[]
  currentSessionId: string | null
  loading: boolean
  error: string | null
}

const sessionSlice = createSlice({
  name: 'session',
  initialState,
  reducers: {
    setCurrentSession: (state, action) => {
      state.currentSessionId = action.payload
    },
    addSession: (state, action) => {
      state.sessions.push(action.payload)
    },
    removeSession: (state, action) => {
      state.sessions = state.sessions.filter(s => s.id !== action.payload)
    },
  },
  extraReducers: (builder) => {
    builder
      .addCase(fetchSessions.pending, (state) => { state.loading = true })
      .addCase(fetchSessions.fulfilled, (state, action) => {
        state.sessions = action.payload
        state.loading = false
      })
      .addCase(fetchSessions.rejected, (state, action) => {
        state.error = action.error.message || 'Failed to fetch sessions'
        state.loading = false
      })
  },
})
```

### 6.3 UI Slice

```typescript
// store/uiSlice.ts
interface UIState {
  sidebarCollapsed: boolean
  activeModule: 'session' | 'memory' | 'tools' | 'skill' | 'mcp' | 'orchestrator' | 'settings'
}

const uiSlice = createSlice({
  name: 'ui',
  initialState: {
    sidebarCollapsed: false,
    activeModule: 'session',
  },
  reducers: {
    toggleSidebar: (state) => {
      state.sidebarCollapsed = !state.sidebarCollapsed
    },
    setActiveModule: (state, action) => {
      state.activeModule = action.payload
    },
  },
})
```

---

## 7. React Query 配置

### 7.1 Query Client

```typescript
// services/queryClient.ts
import { QueryClient } from '@tanstack/react-query'

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 1000 * 60,      // 1 分钟
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
})
```

### 7.2 API 请求封装

```typescript
// services/api.ts
const API_BASE = '/api'

async function fetchApi<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options?.headers,
    },
  })

  if (!response.ok) {
    const error = await response.json().catch(() => ({ message: 'Unknown error' }))
    throw new Error(error.message || `HTTP ${response.status}`)
  }

  return response.json()
}

// 会话 API
export const sessionApi = {
  list: () => fetchApi<Session[]>('/sessions'),
  get: (id: string) => fetchApi<Session>(`/sessions/${id}`),
  create: (data: CreateSessionRequest) => fetchApi<Session>('/sessions', {
    method: 'POST',
    body: JSON.stringify(data),
  }),
  delete: (id: string) => fetchApi<void>(`/sessions/${id}`, { method: 'DELETE' }),
  getMessages: (id: string) => fetchApi<Message[]>(`/sessions/${id}/messages`),
}

// 记忆 API
export const memoryApi = {
  getLongTerm: () => fetchApi<LongTermMemory>('/memory/long-term'),
  updateLongTerm: (content: string) => fetchApi<void>('/memory/long-term', {
    method: 'PUT',
    body: JSON.stringify({ content }),
  }),
  getObservations: (params?: ObservationParams) => {
    const query = new URLSearchParams(params).toString()
    return fetchApi<Observation[]>(`/memory/observations?${query}`)
  },
  search: (query: string) => fetchApi<Observation[]>(`/memory/search?q=${encodeURIComponent(query)}`),
  getStats: () => fetchApi<MemoryStats>('/memory/stats'),
}
```

### 7.3 Hooks

```typescript
// hooks/useSessions.ts
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { sessionApi } from '../services/api'

export function useSessions() {
  return useQuery({
    queryKey: ['sessions'],
    queryFn: sessionApi.list,
  })
}

export function useCreateSession() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: sessionApi.create,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['sessions'] })
    },
  })
}

export function useDeleteSession() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: sessionApi.delete,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['sessions'] })
    },
  })
}
```

---

## 8. 路由设计

```typescript
// App.tsx
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import MainLayout from './layouts/MainLayout'
import SessionPage from './features/session/SessionPage'
import MemoryPage from './features/memory/MemoryPage'
import ToolsPage from './features/tools/ToolsPage'
import SkillPage from './features/skill/SkillPage'
import McpPage from './features/mcp/McpPage'
import OrchestratorPage from './features/orchestrator/OrchestratorPage'
import SettingsPage from './features/settings/SettingsPage'

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<MainLayout />}>
          <Route index element={<SessionPage />} />
          <Route path="memory" element={<MemoryPage />} />
          <Route path="tools" element={<ToolsPage />} />
          <Route path="skill" element={<SkillPage />} />
          <Route path="mcp" element={<McpPage />} />
          <Route path="orchestrator" element={<OrchestratorPage />} />
          <Route path="settings" element={<SettingsPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}
```

---

## 9. 组件设计

### 9.1 主布局组件

```typescript
// layouts/MainLayout.tsx
import { Layout, Menu } from 'antd'
import { Outlet, useNavigate, useLocation } from 'react-router-dom'
import {
  MessageOutlined,
  DatabaseOutlined,
  ToolOutlined,
  AppstoreOutlined,
  CloudServerOutlined,
  RobotOutlined,
  SettingOutlined,
} from '@ant-design/icons'

const { Sider, Content } = Layout

const menuItems = [
  { key: '/', icon: <MessageOutlined />, label: '会话' },
  { key: '/memory', icon: <DatabaseOutlined />, label: '记忆' },
  { key: '/tools', icon: <ToolOutlined />, label: '工具' },
  { key: '/skill', icon: <AppstoreOutlined />, label: 'Skill' },
  { key: '/mcp', icon: <CloudServerOutlined />, label: 'MCP' },
  { key: '/orchestrator', icon: <RobotOutlined />, label: '编排' },
  { key: '/settings', icon: <SettingOutlined />, label: '设置' },
]

export default function MainLayout() {
  const navigate = useNavigate()
  const location = useLocation()

  return (
    <Layout className="h-screen">
      <Sider width={250} theme="light">
        <div className="p-4 font-bold text-lg">Project Agent</div>
        <Menu
          mode="inline"
          selectedKeys={[location.pathname]}
          items={menuItems}
          onClick={({ key }) => navigate(key)}
        />
      </Sider>
      <Content className="overflow-auto">
        <Outlet />
      </Content>
    </Layout>
  )
}
```

### 9.2 聊天组件

```typescript
// features/session/ChatArea.tsx
import { useState, useRef } from 'react'
import { Input, Button, Card } from 'antd'
import { SendOutlined } from '@ant-design/icons'
import MessageBubble from './MessageBubble'
import ToolCallCard from './ToolCallCard'

interface ChatAreaProps {
  sessionId: string
  messages: Message[]
}

export default function ChatArea({ sessionId, messages }: ChatAreaProps) {
  const [input, setInput] = useState('')
  const [isStreaming, setIsStreaming] = useState(false)
  const messagesEndRef = useRef<HTMLDivElement>(null)

  const handleSend = async () => {
    if (!input.trim() || isStreaming) return

    const content = input
    setInput('')
    setIsStreaming(true)

    // 添加用户消息
    appendMessage({ role: 'user', content })

    // SSE 流式请求
    const response = await fetch(`/api/sessions/${sessionId}/chat`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content }),
    })

    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let assistantContent = ''
    let toolCalls: ToolCall[] = []

    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      const text = decoder.decode(value)
      const lines = text.split('\n')

      for (const line of lines) {
        if (line.startsWith('data: ')) {
          const data = JSON.parse(line.slice(6))
          switch (data.type) {
            case 'token':
              assistantContent += data.content
              updateAssistantMessage(assistantContent)
              break
            case 'tool_call':
              toolCalls.push(data)
              updateToolCalls(toolCalls)
              break
            case 'tool_result':
              updateToolResult(data)
              break
          }
        }
      }
    }

    setIsStreaming(false)
    scrollToBottom()
  }

  return (
    <div className="flex flex-col h-full">
      <div className="flex-1 overflow-auto p-4 space-y-4">
        {messages.map((msg, index) => (
          <MessageBubble key={index} message={msg} />
        ))}
        <div ref={messagesEndRef} />
      </div>
      <div className="p-4 border-t">
        <div className="flex gap-2">
          <Input.TextArea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onPressEnter={(e) => {
              if (!e.shiftKey) {
                e.preventDefault()
                handleSend()
              }
            }}
            placeholder="输入消息..."
            autoSize={{ minRows: 1, maxRows: 4 }}
            disabled={isStreaming}
          />
          <Button
            type="primary"
            icon={<SendOutlined />}
            onClick={handleSend}
            loading={isStreaming}
          />
        </div>
      </div>
    </div>
  )
}
```

### 9.3 工具调用卡片

```typescript
// features/session/ToolCallCard.tsx
import { useState } from 'react'
import { Card, Tag, Collapse } from 'antd'
import { ToolOutlined } from '@ant-design/icons'

interface ToolCallCardProps {
  name: string
  arguments: Record<string, any>
  result?: string
  duration?: number
  status: 'running' | 'success' | 'error'
}

export default function ToolCallCard({ name, arguments: args, result, duration, status }: ToolCallCardProps) {
  const [expanded, setExpanded] = useState(false)

  const statusColor = {
    running: 'processing',
    success: 'success',
    error: 'error',
  }[status]

  return (
    <Card
      size="small"
      className="mb-2"
      extra={
        <Tag color={statusColor}>
          {status === 'running' ? '执行中' : status === 'success' ? '成功' : '失败'}
        </Tag>
      }
    >
      <Collapse
        ghost
        onChange={(keys) => setExpanded(keys.length > 0)}
      >
        <Collapse.Panel
          header={
            <div className="flex items-center gap-2">
              <ToolOutlined />
              <span className="font-mono">{name}</span>
              {duration && <span className="text-gray-400 text-sm">{duration}s</span>}
            </div>
          }
          key="1"
        >
          <div className="space-y-2">
            <div>
              <div className="text-gray-500 text-sm mb-1">参数</div>
              <pre className="bg-gray-50 p-2 rounded text-sm overflow-auto">
                {JSON.stringify(args, null, 2)}
              </pre>
            </div>
            {result && (
              <div>
                <div className="text-gray-500 text-sm mb-1">结果</div>
                <pre className="bg-gray-50 p-2 rounded text-sm overflow-auto max-h-40">
                  {result}
                </pre>
              </div>
            )}
          </div>
        </Collapse.Panel>
      </Collapse>
    </Card>
  )
}
```

---

## 10. 后端 API 实现

### 10.1 FastAPI 应用

```python
# agent/web.py
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path

def create_app() -> FastAPI:
    app = FastAPI(title="Project Agent API")

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 注册路由
    from agent.api import sessions, memory, tools, skills, mcp, orchestrator, config
    app.include_router(sessions.router, prefix="/api/sessions", tags=["sessions"])
    app.include_router(memory.router, prefix="/api/memory", tags=["memory"])
    app.include_router(tools.router, prefix="/api/tools", tags=["tools"])
    app.include_router(skills.router, prefix="/api/skills", tags=["skills"])
    app.include_router(mcp.router, prefix="/api/mcp", tags=["mcp"])
    app.include_router(orchestrator.router, prefix="/api/orchestrator", tags=["orchestrator"])
    app.include_router(config.router, prefix="/api/config", tags=["config"])

    # 静态文件（前端打包产物）
    frontend_dist = Path(__file__).parent.parent / "frontend" / "dist"
    if frontend_dist.exists():
        app.mount("/", StaticFiles(directory=str(frontend_dist), html=True))

    return app
```

### 10.2 会话 API

```python
# agent/api/sessions.py
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional
import json

router = APIRouter()

class CreateSessionRequest(BaseModel):
    work_dir: Optional[str] = None

class SendMessageRequest(BaseModel):
    content: str

@router.get("/")
async def list_sessions():
    """获取会话列表"""
    # 调用 SessionManager.list_sessions()
    pass

@router.post("/")
async def create_session(req: CreateSessionRequest):
    """创建新会话"""
    # 调用 SessionManager.new_session()
    pass

@router.get("/{session_id}")
async def get_session(session_id: str):
    """获取会话详情"""
    # 调用 SessionManager.load_session()
    pass

@router.delete("/{session_id}")
async def delete_session(session_id: str):
    """删除会话"""
    # 调用 SessionManager.delete_session()
    pass

@router.get("/{session_id}/messages")
async def get_messages(session_id: str):
    """获取消息历史"""
    # 调用 SessionManager.load_session().messages
    pass

@router.post("/{session_id}/chat")
async def chat(session_id: str, req: SendMessageRequest):
    """流式对话（SSE）"""
    async def generate():
        # 调用 AgentLoop.stream_run()
        # 逐 token yield SSE 事件
        yield f"data: {json.dumps({'type': 'token', 'content': token})}\n\n"
        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")
```

### 10.3 记忆 API

```python
# agent/api/memory.py
from fastapi import APIRouter, Query
from pydantic import BaseModel
from typing import Optional

router = APIRouter()

class UpdateLongTermRequest(BaseModel):
    content: str

class AppendMemoryRequest(BaseModel):
    category: str
    content: str

@router.get("/long-term")
async def get_long_term():
    """获取 MEMORY.md"""
    # 调用 MemoryManager.get_all()
    pass

@router.put("/long-term")
async def update_long_term(req: UpdateLongTermRequest):
    """更新 MEMORY.md"""
    # 调用 MemoryManager.save()
    pass

@router.post("/long-term/append")
async def append_memory(req: AppendMemoryRequest):
    """追加记忆"""
    # 调用 MemoryManager.append()
    pass

@router.get("/observations")
async def list_observations(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    type: Optional[str] = None,
):
    """获取 Observation 列表"""
    # 调用 ObservationStore.get_recent()
    pass

@router.get("/observations/{obs_id}")
async def get_observation(obs_id: str):
    """获取单条 Observation"""
    # 调用 ObservationStore.get_by_id()
    pass

@router.get("/observations/today")
async def get_today_observations():
    """获取今天的 Observation"""
    # 调用 ObservationStore.get_by_date()
    pass

@router.get("/observations/date/{date}")
async def get_observations_by_date(date: str):
    """按日期获取 Observation"""
    # 调用 ObservationStore.get_by_date()
    pass

@router.get("/search")
async def search_memory(q: str = Query(..., min_length=1)):
    """搜索记忆"""
    # 调用 MemorySearch.search()
    pass

@router.get("/promotable")
async def get_promotable():
    """获取可晋升列表"""
    # 调用 ObservationStore.get_promotable()
    pass

@router.post("/promote/{obs_id}")
async def promote(obs_id: str):
    """手动晋升"""
    # 调用 MemorySearch.check_and_promote()
    pass

@router.post("/extract")
async def extract():
    """手动触发提取"""
    # 调用 ObservationExtractor.extract_from_session()
    pass

@router.post("/extract/{session_id}")
async def extract_from_session(session_id: str):
    """从指定 Session 提取"""
    # 调用 ObservationExtractor.extract_from_session()
    pass

@router.get("/stats")
async def get_stats():
    """获取记忆系统统计"""
    # 调用 MemorySearch.get_stats()
    pass
```

---

## 11. 开发配置

### 11.1 Vite 配置

```typescript
// frontend/vite.config.ts
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from 'tailwindcss'
import autoprefixer from 'autoprefixer'

export default defineConfig({
  plugins: [react()],
  css: {
    postcss: {
      plugins: [tailwindcss(), autoprefixer()],
    },
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
  },
})
```

### 11.2 Tailwind 配置

```javascript
// frontend/tailwind.config.js
/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {},
  },
  plugins: [],
  // 避免与 Ant Design 样式冲突
  corePlugins: {
    preflight: false,
  },
}
```

### 11.3 package.json

```json
{
  "name": "project-agent-frontend",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc && vite build",
    "preview": "vite preview"
  },
  "dependencies": {
    "react": "^18.2.0",
    "react-dom": "^18.2.0",
    "react-router-dom": "^6.20.0",
    "@reduxjs/toolkit": "^2.0.0",
    "react-redux": "^9.0.0",
    "@tanstack/react-query": "^5.0.0",
    "antd": "^5.12.0",
    "@ant-design/icons": "^5.2.0"
  },
  "devDependencies": {
    "@types/react": "^18.2.0",
    "@types/react-dom": "^18.2.0",
    "@vitejs/plugin-react": "^4.2.0",
    "autoprefixer": "^10.4.0",
    "postcss": "^8.4.0",
    "tailwindcss": "^3.4.0",
    "typescript": "^5.3.0",
    "vite": "^5.0.0"
  }
}
```

---

## 12. 启动命令

### 12.1 开发模式

```bash
# 终端 1：启动后端
python main.py --web --port 8000

# 终端 2：启动前端开发服务器
cd frontend && npm run dev
```

### 12.2 生产模式

```bash
# 1. 打包前端
cd frontend && npm run build

# 2. 启动后端（自动托管前端静态文件）
python main.py --web --port 8000
```

### 12.3 main.py 参数

```bash
python main.py --web [--port PORT] [--host HOST]
```

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--web` | - | 启动 Web 模式 |
| `--port` | 8000 | 监听端口 |
| `--host` | 0.0.0.0 | 监听地址 |

---

## 13. 实现顺序

### Phase 1：基础框架
1. 创建 `frontend/` 目录，初始化 Vite + React + TypeScript
2. 配置 Tailwind CSS + Ant Design
3. 实现主布局（侧边栏 + 主区域）
4. 配置 React Router 路由

### Phase 2：后端 API
5. 创建 `agent/web.py`，初始化 FastAPI
6. 实现会话 API（CRUD + 流式对话）
7. 实现记忆 API
8. 实现工具日志 API
9. 实现 Skill API
10. 实现 MCP API
11. 实现编排器 API
12. 实现配置 API

### Phase 3：前端功能
13. 配置 Redux Store
14. 配置 React Query
15. 实现会话模块（列表 + 聊天）
16. 实现记忆模块（长期记忆 + Observation + 搜索）
17. 实现工具日志模块
18. 实现 Skill 模块
19. 实现 MCP 模块
20. 实现编排器模块
21. 实现设置模块

### Phase 4：完善
22. SSE 流式输出完善
23. 错误处理和加载状态
24. 响应式适配
25. 打包部署配置

---

## 14. React Bits 动画组件方案

### 14.1 设计理念

采用**科技感 + 动态交互 + 高级视觉效果**的设计风格，通过 React Bits 组件库实现：
- 背景动画营造科技氛围
- 文本动画增强信息展示
- 卡片交互提升用户体验
- 按钮动效增加操作反馈

### 14.2 组件选型

#### 背景动画
| 组件 | 用途 | 位置 |
|------|------|------|
| **Aurora** | 主页面背景 | 整个页面背景层 |
| **Dot Grid** | 会话列表背景 | 侧边栏会话列表区域 |
| **Particles** | 仪表盘背景 | 记忆、工具统计页面 |

#### 文本动画
| 组件 | 用途 | 位置 |
|------|------|------|
| **Shiny Text** | 页面标题 | "Project Agent" 标题 |
| **Typewriter** | Agent 回答 | 聊天区 agent 消息逐字显示 |
| **Gradient Text** | 统计数字 | 记忆统计、工具统计数字 |
| **Count Up** | 数字滚动 | 统计面板的数字动画 |
| **Split Text** | 标题入场 | 各模块页面标题 |

#### 卡片组件
| 组件 | 用途 | 位置 |
|------|------|------|
| **Spotlight Card** | 会话卡片 | 会话列表中的每个会话 |
| **Glass Card** | 记忆卡片 | Observation 列表、工具日志 |
| **Tilt Card** | Skill 卡片 | Skill 列表展示 |
| **Bento Grid** | 仪表盘布局 | 统计面板、Agent 编排面板 |

#### 按钮组件
| 组件 | 用途 | 位置 |
|------|------|------|
| **Magnetic Button** | 主操作按钮 | 发送按钮、新建会话按钮 |
| **Shiny Button** | 次要按钮 | 设置保存、导出按钮 |
| **Glow Button** | 状态指示 | MCP 连接状态、任务状态 |

#### 交互效果
| 组件 | 用途 | 位置 |
|------|------|------|
| **Cursor Follower** | 光标跟随 | 全局光标效果（可选） |
| **Scroll-triggered** | 列表入场 | 会话列表、记忆列表滚动触发动画 |
| **Stagger Children** | 交错入场 | 子元素依次出现 |

#### 加载动画
| 组件 | 用途 | 位置 |
|------|------|------|
| **Dot Spinner** | 加载状态 | 数据加载、流式输出等待 |
| **Bar Loader** | 进度条 | 文件上传、提取进度 |

### 14.3 各页面组件应用

#### 会话页面
```
┌─────────────────────────────────────────────────────────────────┐
│  ✨ [Shiny Text] Project Agent                    [Magnetic Btn] │
├──────────────┬──────────────────────────────────────────────────┤
│  [Aurora]    │                                                  │
│              │  ┌─────────────────────────────────────────┐    │
│  📝 会话       │  │  [Spotlight Card] 会话A                  │    │
│  🧠 记忆       │  │  最后消息: 帮我分析代码...                 │    │
│  🔧 工具       │  └─────────────────────────────────────────┘    │
│  📦 Skill     │                                                  │
│  🔌 MCP       │  ┌─────────────────────────────────────────┐    │
│  🤖 编排       │  │  [Spotlight Card] 会话B                  │    │
│  ⚙️ 设置       │  │  最后消息: 部署文档在哪...                 │    │
│              │  └─────────────────────────────────────────┘    │
│ ──────────── │                                                  │
│ [Dot Grid]   │  ┌─────────────────────────────────────────┐    │
│ 会话列表      │  │  [Typewriter] Agent 回答中...             │    │
│              │  │  根据分析，main.py 包含：                  │    │
│  ┌────────┐  │  │  1. 版本检查                             │    │
│  │[Tilt]  │  │  │  2. CLI 参数解析                          │    │
│  │ 会话A  │  │  │  3. 主循环入口                            │    │
│  └────────┘  │  └─────────────────────────────────────────┘    │
│              │                                                  │
│  ┌────────┐  │  [Magnetic Button] 发送                          │
│  │[Tilt]  │  │                                                  │
│  │ 会话B  │  │                                                  │
│  └────────┘  │                                                  │
└──────────────┴──────────────────────────────────────────────────┘
```

#### 记忆页面
- **统计面板**：Count Up 数字滚动 + Gradient Text
- **Observation 列表**：Glass Card + Scroll-triggered 入场
- **搜索框**：Shiny Text 提示文字
- **晋升按钮**：Shiny Button 闪光效果

#### 工具日志页面
- **统计数字**：Count Up + Gradient Text
- **日志列表**：Spotlight Card + 交错入场动画
- **状态标签**：Glow Button 发光效果

#### Skill 页面
- **Skill 卡片**：Tilt Card 3D 倾斜效果
- **状态指示**：Glow Button 发光
- **详情展开**：Glass Card 毛玻璃

#### MCP 页面
- **Server 状态**：Glow Button 发光指示
- **工具列表**：Spotlight Card
- **重连按钮**：Magnetic Button

#### 编排器页面
- **任务卡片**：Tilt Card + 状态颜色
- **Agent 列表**：Bento Grid 苹果风格布局
- **取消按钮**：Split Button 分裂动画

#### 设置页面
- **表单卡片**：Glass Card 毛玻璃
- **保存按钮**：Shiny Button 闪光
- **开关**：Glow Button 发光

### 14.4 组件封装

```typescript
// components/ui/AnimatedCard.tsx
import { motion } from 'framer-motion'

interface AnimatedCardProps {
  children: React.ReactNode
  className?: string
  delay?: number
}

export function AnimatedCard({ children, className, delay = 0 }: AnimatedCardProps) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, delay }}
      className={className}
    >
      {children}
    </motion.div>
  )
}

// components/ui/SpotlightCard.tsx
import { useState, useRef } from 'react'

interface SpotlightCardProps {
  children: React.ReactNode
  className?: string
}

export function SpotlightCard({ children, className }: SpotlightCardProps) {
  const [position, setPosition] = useState({ x: 0, y: 0 })
  const ref = useRef<HTMLDivElement>(null)

  const handleMouseMove = (e: React.MouseEvent) => {
    if (!ref.current) return
    const rect = ref.current.getBoundingClientRect()
    setPosition({
      x: e.clientX - rect.left,
      y: e.clientY - rect.top,
    })
  }

  return (
    <div
      ref={ref}
      onMouseMove={handleMouseMove}
      className={`relative overflow-hidden ${className}`}
    >
      <div
        className="pointer-events-none absolute -inset-px opacity-0 transition-opacity duration-300 hover:opacity-100"
        style={{
          background: `radial-gradient(600px circle at ${position.x}px ${position.y}px, rgba(255,255,255,0.1), transparent 40%)`,
        }}
      />
      {children}
    </div>
  )
}

// components/ui/TypewriterText.tsx
import { useState, useEffect } from 'react'

interface TypewriterTextProps {
  text: string
  speed?: number
  onComplete?: () => void
}

export function TypewriterText({ text, speed = 50, onComplete }: TypewriterTextProps) {
  const [displayedText, setDisplayedText] = useState('')
  const [currentIndex, setCurrentIndex] = useState(0)

  useEffect(() => {
    if (currentIndex < text.length) {
      const timeout = setTimeout(() => {
        setDisplayedText(prev => prev + text[currentIndex])
        setCurrentIndex(prev => prev + 1)
      }, speed)
      return () => clearTimeout(timeout)
    } else if (onComplete) {
      onComplete()
    }
  }, [currentIndex, text, speed, onComplete])

  return (
    <span>
      {displayedText}
      {currentIndex < text.length && (
        <span className="animate-pulse">|</span>
      )}
    </span>
  )
}

// components/ui/CountUpNumber.tsx
import { useState, useEffect } from 'react'
import { motion, useSpring, useTransform } from 'framer-motion'

interface CountUpNumberProps {
  value: number
  duration?: number
  className?: string
}

export function CountUpNumber({ value, duration = 2, className }: CountUpNumberProps) {
  const spring = useSpring(0, { duration: duration * 1000 })
  const display = useTransform(spring, (current) => Math.round(current))
  const [displayValue, setDisplayValue] = useState(0)

  useEffect(() => {
    spring.set(value)
  }, [spring, value])

  useEffect(() => {
    return display.on('change', (latest) => {
      setDisplayValue(latest)
    })
  }, [display])

  return <motion.span className={className}>{displayValue}</motion.span>
}
```

### 14.5 依赖更新

```json
{
  "dependencies": {
    "react-bits": "^1.0.0",
    "framer-motion": "^11.0.0"
  }
}
```

---

## 15. 设计决策

| 决策 | 理由 |
|------|------|
| 使用 React + TypeScript | 生态最大，组件库丰富，学习资源多 |
| 使用 Redux Toolkit | DevTools 调试方便，适合中大型应用 |
| 使用 React Query | 管理异步数据，自带缓存、重试、loading 状态 |
| 使用 Ant Design 5.x | 组件齐全，CSS-in-JS 与 Tailwind 共存好 |
| 使用 React Bits | 高质量动画组件，提升视觉高级感 |
| 使用 Framer Motion | React Bits 底层动画库，性能好，API 简洁 |
| 使用 Tailwind CSS | 原子化 CSS，灵活度高 |
| 使用 SSE 而非 WebSocket | 单向推送足够，比 WebSocket 简单 |
| 单进程部署 | 本地使用，一个命令启动，无需配置 Nginx |
| Vite proxy + CORS | 开发时用 proxy，生产时留 CORS 口子 |
| 侧边栏布局 | 多模块导航直观，会话列表常驻 |
| 分屏会话界面 | 类似 Slack/微信，切换会话方便 |
| 折叠工具卡片 | 不干扰阅读，按需展开查看详情 |
| 科技感设计风格 | 展现技术能力，提升产品质感 |
| 动态交互效果 | 增强用户体验，增加操作反馈 |
