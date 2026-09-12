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
