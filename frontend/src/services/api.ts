import {
  Session,
  CreateSessionRequest,
  Message,
  LongTermMemory,
  Observation,
  MemoryStats,
  ToolLog,
  Skill,
  MCPServer,
  MCPTool,
  OrchestratorTask,
  AgentSpec,
  AppConfig,
} from '../types'

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
  list: () => fetchApi<Session[]>('/sessions/'),
  get: (id: string) => fetchApi<Session>(`/sessions/${id}`),
  create: (data: CreateSessionRequest) => fetchApi<Session>('/sessions/', {
    method: 'POST',
    body: JSON.stringify(data),
  }),
  delete: (id: string) => fetchApi<void>(`/sessions/${id}`, { method: 'DELETE' }),
  getMessages: (id: string) => fetchApi<Message[]>(`/sessions/${id}/messages`),
  sendMessage: (id: string, content: string) => fetchApi<Message>(`/sessions/${id}/messages`, {
    method: 'POST',
    body: JSON.stringify({ content }),
  }),
}

// 记忆 API
export const memoryApi = {
  getLongTerm: () => fetchApi<LongTermMemory>('/memory/long-term'),
  updateLongTerm: (content: string) => fetchApi<void>('/memory/long-term', {
    method: 'PUT',
    body: JSON.stringify({ content }),
  }),
  appendMemory: (category: string, content: string) => fetchApi<void>('/memory/long-term/append', {
    method: 'POST',
    body: JSON.stringify({ category, content }),
  }),
  getObservations: (params?: { page?: number; page_size?: number; type?: string }) => {
    const query = new URLSearchParams()
    if (params?.page) query.set('page', params.page.toString())
    if (params?.page_size) query.set('page_size', params.page_size.toString())
    if (params?.type) query.set('type', params.type)
    return fetchApi<Observation[]>(`/memory/observations?${query.toString()}`)
  },
  getObservation: (id: string) => fetchApi<Observation>(`/memory/observations/${id}`),
  getTodayObservations: () => fetchApi<Observation[]>('/memory/observations/today'),
  getObservationsByDate: (date: string) => fetchApi<Observation[]>(`/memory/observations/date/${date}`),
  search: (query: string) => fetchApi<Observation[]>(`/memory/search?q=${encodeURIComponent(query)}`),
  advancedSearch: (params: Record<string, any>) => fetchApi<Observation[]>('/memory/search', {
    method: 'POST',
    body: JSON.stringify(params),
  }),
  getPromotable: () => fetchApi<Observation[]>('/memory/promotable'),
  promote: (id: string) => fetchApi<void>(`/memory/promote/${id}`, { method: 'POST' }),
  extract: () => fetchApi<{ count: number }>('/memory/extract', { method: 'POST' }),
  extractFromSession: (sessionId: string) => fetchApi<{ count: number }>(`/memory/extract/${sessionId}`, {
    method: 'POST',
  }),
  getStats: () => fetchApi<MemoryStats>('/memory/stats'),
}

// 工具日志 API
export const toolsApi = {
  getLogs: (params?: { page?: number; page_size?: number; tool_name?: string }) => {
    const query = new URLSearchParams()
    if (params?.page) query.set('page', params.page.toString())
    if (params?.page_size) query.set('page_size', params.page_size.toString())
    if (params?.tool_name) query.set('tool_name', params.tool_name)
    return fetchApi<ToolLog[]>(`/tools/logs?${query.toString()}`)
  },
  getLog: (id: string) => fetchApi<ToolLog>(`/tools/logs/${id}`),
}

// Skill API
export const skillsApi = {
  list: () => fetchApi<Skill[]>('/skills/'),
  get: (name: string) => fetchApi<Skill>(`/skills/${name}`),
  getContent: (name: string) => fetchApi<{ content: string }>(`/skills/${name}/content`),
  getAvailable: () => fetchApi<Skill[]>('/skills/available'),
  getUnavailable: () => fetchApi<Skill[]>('/skills/unavailable'),
}

// MCP API
export const mcpApi = {
  getServers: () => fetchApi<MCPServer[]>('/mcp/servers'),
  getServer: (name: string) => fetchApi<MCPServer>(`/mcp/servers/${name}`),
  reconnect: (name: string) => fetchApi<void>(`/mcp/servers/${name}/reconnect`, { method: 'POST' }),
  getTools: () => fetchApi<MCPTool[]>('/mcp/tools'),
  getServerTools: (server: string) => fetchApi<MCPTool[]>(`/mcp/tools/${server}`),
}

// 编排器 API
export const orchestratorApi = {
  getTasks: () => fetchApi<OrchestratorTask[]>('/orchestrator/tasks'),
  createTask: (data: {
    agent_name: string
    task_description: string
    context?: string
    depends_on?: string[]
  }) => fetchApi<OrchestratorTask>('/orchestrator/tasks', {
    method: 'POST',
    body: JSON.stringify(data),
  }),
  getTask: (id: string) => fetchApi<OrchestratorTask>(`/orchestrator/tasks/${id}`),
  cancelTask: (id: string) => fetchApi<void>(`/orchestrator/tasks/${id}/cancel`, { method: 'POST' }),
  getAgents: () => fetchApi<AgentSpec[]>('/orchestrator/agents'),
}

// 配置 API
export const configApi = {
  get: () => fetchApi<AppConfig>('/config/'),
  update: (config: Partial<AppConfig>) => fetchApi<void>('/config/', {
    method: 'PUT',
    body: JSON.stringify(config),
  }),
}
