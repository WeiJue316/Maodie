import { Routes, Route } from 'react-router-dom'
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
  )
}

export default App
