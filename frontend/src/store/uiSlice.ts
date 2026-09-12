import { createSlice, PayloadAction } from '@reduxjs/toolkit'

type ModuleType = 'session' | 'memory' | 'tools' | 'skill' | 'mcp' | 'orchestrator' | 'settings'

interface UIState {
  sidebarCollapsed: boolean
  activeModule: ModuleType
  theme: 'dark' | 'light'
}

const initialState: UIState = {
  sidebarCollapsed: false,
  activeModule: 'session',
  theme: 'dark',
}

const uiSlice = createSlice({
  name: 'ui',
  initialState,
  reducers: {
    toggleSidebar: (state) => {
      state.sidebarCollapsed = !state.sidebarCollapsed
    },
    setSidebarCollapsed: (state, action: PayloadAction<boolean>) => {
      state.sidebarCollapsed = action.payload
    },
    setActiveModule: (state, action: PayloadAction<ModuleType>) => {
      state.activeModule = action.payload
    },
    setTheme: (state, action: PayloadAction<'dark' | 'light'>) => {
      state.theme = action.payload
    },
  },
})

export const { toggleSidebar, setSidebarCollapsed, setActiveModule, setTheme } = uiSlice.actions
export default uiSlice.reducer
