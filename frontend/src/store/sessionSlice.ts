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
        state.sessions = action.payload
        state.loading = false
        if (!state.currentSessionId && action.payload.length > 0) {
          state.currentSessionId = action.payload[0].id
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
