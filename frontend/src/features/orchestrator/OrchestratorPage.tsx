import { useState, useEffect } from 'react'
import { orchestratorApi } from '../../services/api'
import { OrchestratorTask, AgentSpec } from '../../types'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { FadeIn } from '@/components/effects/FadeIn'
import { Avatar, AvatarFallback } from '@/components/ui/avatar'
import { Plus, StopCircle } from 'lucide-react'

const statusStyle: Record<string, { bg: string; color: string; label: string }> = {
  pending: { bg: 'bg-white/[0.04]', color: 'text-white/30', label: '等待中' },
  running: { bg: 'bg-[#2997FF]/10', color: 'text-[#2997FF]', label: '运行中' },
  completed: { bg: 'bg-[#30D158]/10', color: 'text-[#30D158]', label: '已完成' },
  failed: { bg: 'bg-[#FF453A]/10', color: 'text-[#FF453A]', label: '失败' },
  timeout: { bg: 'bg-[#FF9F0A]/10', color: 'text-[#FF9F0A]', label: '超时' },
  cancelled: { bg: 'bg-white/[0.04]', color: 'text-white/30', label: '已取消' },
}

const agentAvatarColors = [
  'bg-gradient-to-br from-[#2997FF] to-[#1A7AE6]',
  'bg-gradient-to-br from-[#30D158] to-[#28A745]',
  'bg-gradient-to-br from-[#FF9F0A] to-[#FF6B00]',
]

export default function OrchestratorPage() {
  const [tasks, setTasks] = useState<OrchestratorTask[]>([])
  const [agents, setAgents] = useState<AgentSpec[]>([])
  const [loading, setLoading] = useState(true)
  const [showCreate, setShowCreate] = useState(false)
  const [form, setForm] = useState({ agent_name: '', task_description: '', context: '' })
  const [creating, setCreating] = useState(false)

  useEffect(() => { loadData() }, [])

  const loadData = async () => {
    setLoading(true)
    try {
      const [t, a] = await Promise.all([orchestratorApi.getTasks(), orchestratorApi.getAgents()])
      setTasks(t); setAgents(a)
    } catch {}
    finally { setLoading(false) }
  }

  const handleCreate = async () => {
    if (!form.agent_name || !form.task_description) return
    setCreating(true)
    try {
      await orchestratorApi.createTask(form)
      setShowCreate(false); setForm({ agent_name: '', task_description: '', context: '' })
      loadData()
    } catch {}
    finally { setCreating(false) }
  }

  const handleCancel = async (id: string) => {
    try { await orchestratorApi.cancelTask(id); loadData() } catch {}
  }

  return (
    <div className="flex flex-col p-6 gap-5 h-full overflow-y-auto">
      <div className="flex items-center justify-between">
        <span className="text-lg font-semibold text-white">Agent 编排器</span>
        <Button size="sm" onClick={() => setShowCreate(true)} className="bg-[#2997FF] hover:bg-[#40A9FF] text-white">
          <Plus className="w-4 h-4 mr-1" />
          创建任务
        </Button>
      </div>

      {/* Agent grid + stats */}
      <div className="grid grid-cols-[2fr_1fr] gap-4">
        <Card className="bg-white/[0.03] border-white/[0.06]">
          <CardContent className="p-5">
            <div className="text-[11px] font-semibold text-white/30 uppercase tracking-wider mb-3">Agent 列表</div>
            <div className="space-y-2.5">
              {agents.map((agent, i) => (
                <div key={agent.name} className="flex items-center gap-2.5 p-2.5 rounded-md bg-white/[0.02]">
                  <Avatar className="w-7 h-7">
                    <AvatarFallback className={`${agentAvatarColors[i % agentAvatarColors.length]} text-white text-xs font-semibold`}>
                      {agent.name[0].toUpperCase()}
                    </AvatarFallback>
                  </Avatar>
                  <div className="flex-1 min-w-0">
                    <div className="text-[13px] font-medium text-white">{agent.name}</div>
                    <div className="text-[11.5px] text-white/30 truncate">
                      {agent.system_prompt?.slice(0, 30) || 'Agent'}
                    </div>
                  </div>
                  <div className="w-2 h-2 rounded-full bg-white/15" />
                </div>
              ))}
              {agents.length === 0 && (
                <div className="text-center py-5 text-white/30 text-[13px]">暂无 Agent</div>
              )}
            </div>
          </CardContent>
        </Card>

        <Card className="bg-white/[0.03] border-white/[0.06]">
          <CardContent className="p-5">
            <div className="text-[11px] font-semibold text-white/30 uppercase tracking-wider mb-3">任务统计</div>
            <div className="space-y-3 mt-2">
              {[
                { label: '运行中', value: tasks.filter(t => t.status === 'running').length, color: '#2997FF' },
                { label: '已完成', value: tasks.filter(t => t.status === 'completed').length, color: '#30D158' },
                { label: '总计', value: tasks.length, color: 'rgba(255,255,255,0.3)' },
              ].map(s => (
                <div key={s.label} className="flex justify-between items-center">
                  <span className="text-[13px] text-white/50">{s.label}</span>
                  <span className="text-[20px] font-bold" style={{ color: s.color }}>{s.value}</span>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Task list */}
      <div>
        <div className="text-lg font-semibold text-white mb-3">任务列表</div>
        <div className="space-y-2">
          {loading ? (
            <div className="text-center py-5 text-white/30 text-[13px]">加载中...</div>
          ) : tasks.length === 0 ? (
            <div className="text-center py-5 text-white/30 text-[13px]">暂无任务</div>
          ) : (
            tasks.map((task, i) => {
              const st = statusStyle[task.status] || statusStyle.pending
              return (
                <FadeIn key={task.task_id} delay={i * 40}>
                  <div className="flex items-center gap-2.5 p-3 rounded-md bg-white/[0.02] text-[13px]">
                    <span className="flex-1 text-white/70">{task.task_description}</span>
                    <Badge variant="secondary" className={`text-[11px] font-medium ${st.bg} ${st.color}`}>{st.label}</Badge>
                    <span className="text-[12px] text-white/30">{task.agent}</span>
                    {task.status === 'running' && (
                      <Button variant="ghost" size="sm" onClick={() => handleCancel(task.task_id)} className="h-6 px-2 text-[11px] text-[#FF453A] hover:bg-[#FF453A]/10">
                        <StopCircle className="w-3 h-3 mr-0.5" />
                        取消
                      </Button>
                    )}
                  </div>
                </FadeIn>
              )
            })
          )}
        </div>
      </div>

      {/* Create modal */}
      <Dialog open={showCreate} onOpenChange={setShowCreate}>
        <DialogContent className="bg-[#1A1A1A] border-white/[0.08] text-white">
          <DialogHeader>
            <DialogTitle className="text-white">创建任务</DialogTitle>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <label className="text-[12.5px] font-medium text-white/50 mb-1.5 block">Agent</label>
              <select
                className="w-full h-9 rounded-md bg-white/[0.06] border border-white/[0.06] px-3 text-[13px] text-white outline-none"
                value={form.agent_name}
                onChange={e => setForm(f => ({ ...f, agent_name: e.target.value }))}
              >
                <option value="">选择 Agent</option>
                {agents.map(a => <option key={a.name} value={a.name}>{a.name}</option>)}
              </select>
            </div>
            <div>
              <label className="text-[12.5px] font-medium text-white/50 mb-1.5 block">任务描述</label>
              <textarea
                className="w-full rounded-md bg-white/[0.06] border border-white/[0.06] px-3 py-2 text-[13px] text-white outline-none resize-vertical min-h-[80px]"
                value={form.task_description}
                onChange={e => setForm(f => ({ ...f, task_description: e.target.value }))}
                placeholder="描述任务..."
              />
            </div>
            <div>
              <label className="text-[12.5px] font-medium text-white/50 mb-1.5 block">上下文（可选）</label>
              <textarea
                className="w-full rounded-md bg-white/[0.06] border border-white/[0.06] px-3 py-2 text-[13px] text-white outline-none resize-vertical min-h-[60px]"
                value={form.context}
                onChange={e => setForm(f => ({ ...f, context: e.target.value }))}
                placeholder="补充上下文..."
              />
            </div>
            <div className="flex justify-end gap-2">
              <Button variant="ghost" onClick={() => setShowCreate(false)} className="text-white/50">取消</Button>
              <Button onClick={handleCreate} disabled={creating} className="bg-[#2997FF] hover:bg-[#40A9FF] text-white">
                {creating ? '创建中...' : '创建'}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  )
}
