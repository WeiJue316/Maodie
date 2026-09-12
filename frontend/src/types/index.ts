// 会话相关类型
export interface Session {
  id: string
  title: string
  created_at: string
  updated_at: string
  work_dir: string
  messages: Message[]
}

export interface Message {
  role: 'system' | 'user' | 'assistant' | 'tool'
  content: string
  tool_calls?: ToolCall[]
  tool_call_id?: string
}

export interface ToolCall {
  id: string
  type: 'function'
  function: {
    name: string
    arguments: string
  }
}

export interface CreateSessionRequest {
  work_dir?: string
}

// 记忆相关类型
export interface LongTermMemory {
  content: string
  categories: Record<string, string[]>
}

export interface Observation {
  id: string
  type: 'bugfix' | 'feature' | 'refactor' | 'change' | 'discovery' | 'decision'
  title: string
  narrative: string
  facts: string[]
  concepts: string[]
  files_read: string[]
  files_modified: string[]
  session_id: string
  created_at: string
  relevance_count: number
  content_hash: string
  promoted: number
}

export interface MemoryStats {
  total_observations: number
  by_type: Record<string, number>
  promoted_count: number
  fts5_available: boolean
  vectordb_available: boolean
  vectordb_count: number
}

// 工具日志相关类型
export interface ToolLog {
  id: string
  session_id: string
  tool_name: string
  arguments: Record<string, any>
  result: string
  status: 'success' | 'error'
  duration: number
  created_at: string
}

// Skill 相关类型
export interface Skill {
  name: string
  description: string
  path: string
  file_path: string
  tools: string[]
  unavailable_tools: string[]
  metadata: Record<string, any>
}

// MCP 相关类型
export interface MCPServer {
  name: string
  transport: string
  connected: boolean
  tool_count: number
  tools: string[]
  error: string
}

export interface MCPTool {
  name: string
  description: string
  parameters: Record<string, any>
  server: string
}

// 编排器相关类型
export interface OrchestratorTask {
  task_id: string
  agent: string
  status: 'pending' | 'running' | 'completed' | 'failed' | 'timeout' | 'cancelled'
  task_description: string
  context?: string
  depends_on: string[]
  result?: string
  summary?: string
  error?: string
  error_type?: string
  started_at?: number
  completed_at?: number
  duration_seconds?: number
}

export interface AgentSpec {
  name: string
  system_prompt?: string
  max_iterations?: number
  tools?: string[]
  model?: string
}

// 配置相关类型
export interface AppConfig {
  llm: {
    provider: string
    model: string
    base_url: string
    temperature: number
    timeout: number
    streaming: boolean
  }
  agent: {
    max_iterations: number
    work_dir: string
    system_prompt: string
  }
  session: {
    dir: string
    max_history: number
    auto_save: boolean
  }
  memory: {
    enabled: boolean
  }
  observation: {
    enabled: boolean
    db_path: string
  }
  vectordb: {
    enabled: boolean
  }
  memory_search: {
    enabled: boolean
    search_limit: number
    promotion_threshold: number
  }
}

// API 响应类型
export interface ApiResponse<T> {
  data: T
  message?: string
}

export interface PaginatedResponse<T> {
  items: T[]
  total: number
  page: number
  page_size: number
}
