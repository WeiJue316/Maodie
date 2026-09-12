import { useState, useEffect } from 'react'
import { configApi } from '../../services/api'
import { AppConfig } from '../../types'
import { Card, CardContent } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { Separator } from '@/components/ui/separator'
import { FadeIn } from '@/components/effects/FadeIn'

export default function SettingsPage() {
  const [, setConfig] = useState<AppConfig | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [form, setForm] = useState<any>({})

  useEffect(() => { loadConfig() }, [])

  const loadConfig = async () => {
    setLoading(true)
    try {
      const data = await configApi.get()
      setConfig(data)
      setForm(JSON.parse(JSON.stringify(data)))
    } catch {}
    finally { setLoading(false) }
  }

  const handleSave = async () => {
    setSaving(true)
    try { await configApi.update(form); loadConfig() } catch {}
    finally { setSaving(false) }
  }

  const updateField = (path: string[], value: any) => {
    setForm((prev: any) => {
      const next = { ...prev }
      let obj = next
      for (let i = 0; i < path.length - 1; i++) {
        obj[path[i]] = { ...obj[path[i]] }
        obj = obj[path[i]]
      }
      obj[path[path.length - 1]] = value
      return next
    })
  }

  if (loading) return <div className="flex-1 flex items-center justify-center text-white/30 text-sm">加载中...</div>

  return (
    <div className="flex flex-col p-6 gap-6 h-full overflow-y-auto max-w-[720px]">
      {/* LLM */}
      <FadeIn>
        <Card className="bg-white/[0.03] border-white/[0.06]">
          <CardContent className="p-6">
            <div className="text-[15px] font-semibold text-white mb-5">LLM 配置</div>
            <div className="space-y-4">
              <div>
                <label className="text-[12.5px] font-medium text-white/50 mb-1.5 block">Provider</label>
                <select
                  className="w-full h-9 rounded-md bg-white/[0.06] border border-white/[0.06] px-3 text-[13px] text-white outline-none"
                  value={form.llm?.provider || ''}
                  onChange={e => updateField(['llm', 'provider'], e.target.value)}
                >
                  <option value="mimo">mimo</option>
                  <option value="minimax">MiniMax</option>
                  <option value="deepseek">DeepSeek</option>
                  <option value="openai">OpenAI</option>
                </select>
              </div>
              <div>
                <label className="text-[12.5px] font-medium text-white/50 mb-1.5 block">模型</label>
                <Input value={form.llm?.model || ''} onChange={e => updateField(['llm', 'model'], e.target.value)} className="bg-white/[0.06] border-white/[0.06] text-white" />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-[12.5px] font-medium text-white/50 mb-1.5 block">Base URL</label>
                  <Input value={form.llm?.base_url || ''} onChange={e => updateField(['llm', 'base_url'], e.target.value)} className="bg-white/[0.06] border-white/[0.06] text-white" />
                </div>
                <div>
                  <label className="text-[12.5px] font-medium text-white/50 mb-1.5 block">Temperature</label>
                  <Input type="number" step="0.1" min="0" max="2" value={form.llm?.temperature ?? 0.7} onChange={e => updateField(['llm', 'temperature'], parseFloat(e.target.value))} className="bg-white/[0.06] border-white/[0.06] text-white" />
                </div>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-[12.5px] font-medium text-white/50 mb-1.5 block">超时 (秒)</label>
                  <Input type="number" min="1" value={form.llm?.timeout ?? 180} onChange={e => updateField(['llm', 'timeout'], parseInt(e.target.value))} className="bg-white/[0.06] border-white/[0.06] text-white" />
                </div>
                <div>
                  <label className="text-[12.5px] font-medium text-white/50 mb-1.5 block">流式输出</label>
                  <div className="flex items-center h-9">
                    <button
                      className={`w-10 h-[22px] rounded-full relative transition-colors ${form.llm?.streaming ? 'bg-[#2997FF]' : 'bg-white/12'}`}
                      onClick={() => updateField(['llm', 'streaming'], !form.llm?.streaming)}
                      type="button"
                    >
                      <span className={`absolute top-[2px] left-[2px] w-[18px] h-[18px] bg-white rounded-full transition-transform ${form.llm?.streaming ? 'translate-x-[18px]' : ''}`} />
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </CardContent>
        </Card>
      </FadeIn>

      {/* Agent */}
      <FadeIn delay={100}>
        <Card className="bg-white/[0.03] border-white/[0.06]">
          <CardContent className="p-6">
            <div className="text-[15px] font-semibold text-white mb-5">Agent 配置</div>
            <div className="space-y-0">
              {[
                { label: '自动保存会话', desc: '每轮对话后自动持久化', path: ['session', 'auto_save'] },
                { label: 'Observation 提取', desc: '会话结束时自动提取记忆', path: ['observation', 'enabled'] },
                { label: '自动晋升', desc: '引用次数达标后自动晋升为长期记忆', path: ['memory_search', 'auto_promote'] },
              ].map((item, i) => (
                <div key={item.label}>
                  <div className="flex items-center justify-between py-3">
                    <div>
                      <div className="text-[13px] text-white">{item.label}</div>
                      <div className="text-[11.5px] text-white/30">{item.desc}</div>
                    </div>
                    <button
                      className={`w-10 h-[22px] rounded-full relative transition-colors ${item.path.reduce((o: any, k) => o?.[k], form) ? 'bg-[#2997FF]' : 'bg-white/12'}`}
                      onClick={() => updateField(item.path, !item.path.reduce((o: any, k) => o?.[k], form))}
                      type="button"
                    >
                      <span className={`absolute top-[2px] left-[2px] w-[18px] h-[18px] bg-white rounded-full transition-transform ${item.path.reduce((o: any, k) => o?.[k], form) ? 'translate-x-[18px]' : ''}`} />
                    </button>
                  </div>
                  {i < 2 && <Separator className="bg-white/[0.04]" />}
                </div>
              ))}
            </div>
            <div className="mt-4">
              <label className="text-[12.5px] font-medium text-white/50 mb-1.5 block">最大迭代次数</label>
              <Input type="number" min="1" style={{ width: 120 }} value={form.agent?.max_iterations ?? 40} onChange={e => updateField(['agent', 'max_iterations'], parseInt(e.target.value))} className="bg-white/[0.06] border-white/[0.06] text-white" />
            </div>
          </CardContent>
        </Card>
      </FadeIn>

      {/* Session */}
      <FadeIn delay={200}>
        <Card className="bg-white/[0.03] border-white/[0.06]">
          <CardContent className="p-6">
            <div className="text-[15px] font-semibold text-white mb-5">会话配置</div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-[12.5px] font-medium text-white/50 mb-1.5 block">存储目录</label>
                <Input value={form.session?.dir || ''} onChange={e => updateField(['session', 'dir'], e.target.value)} className="bg-white/[0.06] border-white/[0.06] text-white" />
              </div>
              <div>
                <label className="text-[12.5px] font-medium text-white/50 mb-1.5 block">最大历史条数</label>
                <Input type="number" min="1" value={form.session?.max_history ?? 100} onChange={e => updateField(['session', 'max_history'], parseInt(e.target.value))} className="bg-white/[0.06] border-white/[0.06] text-white" />
              </div>
            </div>
          </CardContent>
        </Card>
      </FadeIn>

      {/* Actions */}
      <div className="flex gap-2 justify-end pb-4">
        <Button variant="ghost" onClick={loadConfig} className="text-white/50">重置</Button>
        <Button onClick={handleSave} disabled={saving} className="bg-[#2997FF] hover:bg-[#40A9FF] text-white">
          {saving ? '保存中...' : '保存设置'}
        </Button>
      </div>
    </div>
  )
}
