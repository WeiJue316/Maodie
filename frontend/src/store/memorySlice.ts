import { createSlice, createAsyncThunk, PayloadAction } from '@reduxjs/toolkit'
import { memoryApi } from '../services/api'
import { Observation, MemoryStats } from '../types'

interface MemoryState {
  observations: Observation[]
  stats: MemoryStats | null
  loading: boolean
  error: string | null
}

const initialState: MemoryState = {
  observations: [],
  stats: null,
  loading: false,
  error: null,
}

export const fetchObservations = createAsyncThunk(
  'memory/fetchObservations',
  async (params?: { page?: number; page_size?: number; type?: string }) => {
    const response = await memoryApi.getObservations(params)
    return response
  }
)

export const fetchMemoryStats = createAsyncThunk(
  'memory/fetchStats',
  async () => {
    const response = await memoryApi.getStats()
    return response
  }
)

const memorySlice = createSlice({
  name: 'memory',
  initialState,
  reducers: {
    setObservations: (state, action: PayloadAction<Observation[]>) => {
      state.observations = action.payload
    },
    addObservation: (state, action: PayloadAction<Observation>) => {
      state.observations.unshift(action.payload)
    },
  },
  extraReducers: (builder) => {
    builder
      .addCase(fetchObservations.pending, (state) => {
        state.loading = true
        state.error = null
      })
      .addCase(fetchObservations.fulfilled, (state, action) => {
        state.observations = action.payload
        state.loading = false
      })
      .addCase(fetchObservations.rejected, (state, action) => {
        state.error = action.error.message || 'Failed to fetch observations'
        state.loading = false
      })
      .addCase(fetchMemoryStats.fulfilled, (state, action) => {
        state.stats = action.payload
      })
  },
})

export const { setObservations, addObservation } = memorySlice.actions
export default memorySlice.reducer
