import { Outlet, useNavigate, useLocation } from 'react-router-dom'
import { useDispatch } from 'react-redux'
import { setActiveModule } from '../store/uiSlice'

const navItems = [
  { key: '/', label: '会话', module: 'session' as const },
  { key: '/memory', label: '记忆', module: 'memory' as const },
  { key: '/tools', label: '工具', module: 'tools' as const },
  { key: '/skill', label: '技能', module: 'skill' as const },
  { key: '/mcp', label: 'MCP', module: 'mcp' as const },
  { key: '/orchestrator', label: '编排器', module: 'orchestrator' as const },
  { key: '/settings', label: '设置', module: 'settings' as const },
]

const titles: Record<string, string> = {
  '/': '会话', '/memory': '记忆', '/tools': '工具', '/skill': '技能',
  '/mcp': 'MCP', '/orchestrator': '编排器', '/settings': '设置',
}

export default function MainLayout() {
  const navigate = useNavigate()
  const location = useLocation()
  const dispatch = useDispatch()

  return (
    <div style={{ display: 'flex', height: '100vh', background: '#0A0A0A' }}>
      <aside style={{ width: 240, height: '100vh', background: 'rgba(18,18,18,0.92)', borderRight: '1px solid rgba(255,255,255,0.06)', display: 'flex', flexDirection: 'column', flexShrink: 0 }}>
        <div style={{ padding: '20px 16px 12px', borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <div style={{ width: 32, height: 32, background: 'linear-gradient(135deg, #2997FF, #1A7AE6)', borderRadius: 8, display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 700, fontSize: 14, color: '#fff' }}>A</div>
            <div>
              <div style={{ fontWeight: 600, fontSize: 15, color: '#F5F5F7' }}>Project Agent</div>
              <div style={{ fontSize: 11, color: 'rgba(255,255,255,0.4)' }}>v2.0</div>
            </div>
          </div>
        </div>
        <nav style={{ flex: 1, padding: 8, overflowY: 'auto' }}>
          {navItems.map(item => {
            const isActive = location.pathname === item.key
            return (
              <div key={item.key} onClick={() => { navigate(item.key); dispatch(setActiveModule(item.module)) }}
                style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '8px 10px', borderRadius: 6, cursor: 'pointer', fontSize: 13.5, color: isActive ? '#2997FF' : 'rgba(255,255,255,0.5)', fontWeight: isActive ? 500 : 450, background: isActive ? 'rgba(41,151,255,0.12)' : 'transparent', marginBottom: 2 }}>
                {item.label}
              </div>
            )
          })}
        </nav>
      </aside>
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        <div style={{ height: 52, padding: '0 24px', display: 'flex', alignItems: 'center', borderBottom: '1px solid rgba(255,255,255,0.04)', background: 'rgba(10,10,10,0.8)' }}>
          <span style={{ fontSize: 15, fontWeight: 600, color: '#F5F5F7' }}>{titles[location.pathname] || ''}</span>
        </div>
        <div style={{ flex: 1, overflow: 'hidden' }}><Outlet /></div>
      </div>
    </div>
  )
}
