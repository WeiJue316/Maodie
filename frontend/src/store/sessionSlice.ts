import { createSlice, createAsyncThunk, PayloadAction } from '@reduxjs/toolkit'
import { sessionApi } from '../services/api'
import { Session } from '../types'

interface SessionState {
  sessions: Session[]
  currentSessionId: string | null
  loading: boolean
  error: string | null
}

const initialState: SessionState = {
  sessions: [],
  currentSessionId: null,
  loading: false,
  error: null,
}

export const fetchSessions = createAsyncThunk(
  'session/fetchSessions',
  async () => {
    const response = await sessionApi.list()
    return response
  }
)

export const createSession = createAsyncThunk(
  'session/createSession',
  async (data?: { work_dir?: string }) => {
    const response = await sessionApi.create(data || {})
    return response
  }
)

export const deleteSession = createAsyncThunk(
  'session/deleteSession',
  async (id: string) => {
    await sessionApi.delete(id)
    return id
  }
)

const sessionSlice = createSlice({
  name: 'session',
  initialState,
  reducers: {
    setCurrentSession: (state, action: PayloadAction<string | null>) => {
      state.currentSessionId = action.payload
    },
    addSession: (state, action: PayloadAction<Session>) => {
      state.sessions.unshift(action.payload)
    },
    removeSession: (state, action: PayloadAction<string>) => {
      state.sessions = state.sessions.filter(s => s.id !== action.payload)
      if (state.currentSessionId === action.payload) {
        state.currentSessionId = state.sessions[0]?.id || null
      }
    },
    updateSession: (state, action: PayloadAction<Session>) => {
      const index = state.sessions.findIndex(s => s.id === action.payload.id)
      if (index !== -1) {
        state.sessions[index] = action.payload
      }
    },
  },
  extraReducers: (builder) => {
    builder
      .addCase(fetchSessions.pending, (state) => {
        state.loading = true
        state.error = null
      })
      .addCase(fetchSessions.fulfilled, (state, action) => {
        state.loading = false
        const fresh: Session[] = action.payload
        // 记录当前已展示会话的位置，合并时保持不变，避免每次发送消息后整表按 updated_at
        // 重新排序，把用户选中的历史会话「挤走」；仅新增的会话才会被放到最前。
        const keepIndex = new Map<string, number>()
        state.sessions.forEach((s, i) => keepIndex.set(s.id, i))
        state.sessions = fresh
          .map(s => ({ s, ord: keepIndex.get(s.id) ?? -1 }))
          .sort((a, b) => a.ord - b.ord)
          .map(x => x.s)
          // 过滤掉没有任何对话的空会话；刚新建、正选中在用的空会话仍保留可见
          .filter(s => (s.message_count || 0) > 0 || s.id === state.currentSessionId)
        if (!state.currentSessionId && state.sessions.length > 0) {
          state.currentSessionId = state.sessions[0].id
        }
      })
      .addCase(fetchSessions.rejected, (state, action) => {
        state.error = action.error.message || 'Failed to fetch sessions'
        state.loading = false
      })
      .addCase(createSession.fulfilled, (state, action) => {
        state.sessions.unshift(action.payload)
        state.currentSessionId = action.payload.id
      })
      .addCase(deleteSession.fulfilled, (state, action) => {
        state.sessions = state.sessions.filter(s => s.id !== action.payload)
        if (state.currentSessionId === action.payload) {
          state.currentSessionId = state.sessions[0]?.id || null
        }
      })
  },
})

export const { setCurrentSession, addSession, removeSession, updateSession } = sessionSlice.actions
export default sessionSlice.reducer
