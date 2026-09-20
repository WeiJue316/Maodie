import { Outlet, useNavigate, useLocation } from 'react-router-dom'
import { useDispatch } from 'react-redux'
import { setActiveModule } from '../store/uiSlice'
import { ClickSpark } from '../components/effects'
import Dock from '../components/dock/Dock'
import {
  MessageSquare,
  Database,
  Wrench,
  Sparkles,
  Server,
  Network,
  Settings,
} from 'lucide-react'

const navItems = [
  { key: '/', label: '会话', module: 'session' as const, Icon: MessageSquare },
  { key: '/memory', label: '记忆', module: 'memory' as const, Icon: Database },
  { key: '/tools', label: '工具', module: 'tools' as const, Icon: Wrench },
  { key: '/skill', label: '技能', module: 'skill' as const, Icon: Sparkles },
  { key: '/mcp', label: 'MCP', module: 'mcp' as const, Icon: Server },
  { key: '/orchestrator', label: '编排器', module: 'orchestrator' as const, Icon: Network },
  { key: '/settings', label: '设置', module: 'settings' as const, Icon: Settings },
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
    <ClickSpark sparkColor="#2997FF" sparkCount={8} sparkRadius={16} sparkSize={6} duration={400}>
      <div style={{ display: 'flex', flexDirection: 'column', height: '100vh', background: '#0A0A0A' }}>
        <header
          style={{
            height: 52,
            padding: '0 20px',
            display: 'flex',
            alignItems: 'center',
            gap: 12,
            borderBottom: '1px solid rgba(255,255,255,0.04)',
            background: 'rgba(10,10,10,0.6)',
            flexShrink: 0,
          }}
        >
          <div style={{ width: 28, height: 28, background: 'linear-gradient(135deg, #2997FF, #1A7AE6)', borderRadius: 8, display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 700, fontSize: 13, color: '#fff' }}>A</div>
          <span style={{ fontWeight: 600, fontSize: 14, color: '#F5F5F7' }}>Project Agent</span>
          <span style={{ fontSize: 11, color: 'rgba(255,255,255,0.35)' }}>v2.0</span>
          <span style={{ flex: 1 }} />
          <span style={{ fontSize: 15, fontWeight: 600, color: '#F5F5F7' }}>{titles[location.pathname] || ''}</span>
        </header>

        <div style={{ flex: 1, minHeight: 0, overflow: 'hidden' }}>
          <Outlet />
        </div>

        {/* 底部导航 Dock */}
        <div style={{ position: 'relative', height: 104, flexShrink: 0 }}>
          <Dock
            items={navItems.map(item => ({
              key: item.key,
              icon: <item.Icon size={20} strokeWidth={1.8} />,
              label: item.label,
              className: location.pathname === item.key ? 'dock-active' : '',
              onClick: () => {
                navigate(item.key)
                dispatch(setActiveModule(item.module))
              },
            }))}
            magnification={62}
            baseItemSize={46}
            panelHeight={52}
            dockHeight={64}
          />
        </div>
      </div>
    </ClickSpark>
  )
}