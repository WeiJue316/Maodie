import { useState, useEffect } from 'react'
import { configApi } from '../../services/api'
import { AppConfig } from '../../types'
import { Card, CardContent } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Button } from '@/components/ui/button'
import { Separator } from '@/components/ui/separator'
import { FadeIn } from '@/components/effects/FadeIn'

// 各 Provider 常见模型建议（供下拉选择；预置配置里的模型会优先列出）
const SUGGESTED_MODELS: Record<string, string[]> = {
  mimo: ['mimo-v2.5-pro', 'mimo-v2.5'],
  minimax: ['MiniMax-M2.7', 'MiniMax-M1.0', 'MiniMax-L1.0'],
  deepseek: ['deepseek-chat', 'deepseek-reasoner'],
  openai: ['gpt-4o', 'gpt-4o-mini', 'gpt-4.1', 'gpt-4.1-mini'],
}

// 各 Provider 的默认模型与默认 Base URL，切换 Provider 时自动带出
const PROVIDER_DEFAULTS: Record<string, { model: string; base_url: string }> = {
  mimo: { model: 'mimo-v2.5-pro', base_url: 'https://token-plan-cn.xiaomimimo.com/v1' },
  minimax: { model: 'MiniMax-M2.7', base_url: 'https://api.minimax.chat/v1' },
  deepseek: { model: 'deepseek-chat', base_url: 'https://api.deepseek.com/v1' },
  openai: { model: 'gpt-4o', base_url: 'https://api.openai.com/v1' },
}

// 原生 <option> 弹层在不同浏览器/系统下默认可能白底白字看不清，
// 显式给深底浅字，Chrome/Firefox 都会遵守，保证下拉可读。
const optionDark = { backgroundColor: '#1b1b1f', color: '#e6e6e6' }

// 内置 Provider 的展示名；其它（用户自行添加模型的 provider）直接用原文显示
const PROVIDER_LABELS: Record<string, string> = {
  mimo: 'mimo',
  minimax: 'MiniMax',
  deepseek: 'DeepSeek',
  openai: 'OpenAI',
}
const BUILTIN_PROVIDERS = ['mimo', 'minimax', 'deepseek', 'openai']

export default function SettingsPage() {
  const [, setConfig] = useState<AppConfig | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [form, setForm] = useState<any>({})
  const [addModelOpen, setAddModelOpen] = useState(false)
  const [newModel, setNewModel] = useState({ name: '', provider: '', base_url: '', api_key: '' })
  const provider = form.llm?.provider || ''
  const currentModel = form.llm?.model || ''
  const presets: { name: string; provider: string; base_url: string; api_key?: string }[] = form.llm?.models || []
  // Provider 下拉 = 内置四个 + 各预置里出现的自定义 provider，去重
  const providerOptions = Array.from(new Set([...BUILTIN_PROVIDERS, ...presets.map(p => p.provider).filter(Boolean)]))
  // 下拉可选模型 = 已注册预置 + 建议模型 + 当前模型，去重
  const presetNames = new Set(presets.map(p => p.name))
  const suggestions = (SUGGESTED_MODELS[provider] || []).filter(m => !presetNames.has(m))
  const modelOptions = Array.from(new Set([...presets.map(p => p.name), ...suggestions, currentModel].filter(Boolean)))
  const modelInList = !!currentModel && modelOptions.includes(currentModel)
  const isCurrentAPreset = presets.some(p => p.name === currentModel)

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

  const openNewModel = () => {
    // 从空白开始，不带入当前 Provider（mimo）的模型/URL，让用户自己填
    setNewModel({ name: '', provider: '', base_url: '', api_key: '' })
    setAddModelOpen(true)
  }

  const addModel = () => {
    const name = newModel.name.trim()
    if (!name) return
    const key = newModel.api_key.trim()
    // 预置带上 api_key；若填写了 key，同时把当前生效的全局 key 切到它（仅写，不回读）
    const modelProvider = newModel.provider.trim() || provider
    updateField(['llm', 'models'], [...presets, { name, provider: modelProvider, base_url: newModel.base_url, api_key: key }])
    // 模型归属的 provider 即为当前生效 provider（该值会显示在 Provider 下拉）
    updateField(['llm', 'provider'], modelProvider)
    updateField(['llm', 'model'], name)
    if (key) updateField(['llm', 'base_url'], newModel.base_url)
    if (key) updateField(['llm', 'api_key'], key)
    setAddModelOpen(false)
    setNewModel({ name: '', provider: '', base_url: '', api_key: '' })
  }

  const onChangeProvider = (p: string) => {
    updateField(['llm', 'provider'], p)
    // 优先选用该 Provider 已注册的模型预置；否则用该 Provider 的默认模型 / Base URL
    const presetForProvider = presets.find(x => x.provider === p)
    const def = PROVIDER_DEFAULTS[p] || { model: '', base_url: '' }
    updateField(['llm', 'model'], presetForProvider?.name || def.model)
    updateField(['llm', 'base_url'], presetForProvider?.base_url || def.base_url)
  }

  const onDeleteModel = () => {
    const remaining = presets.filter(p => p.name !== currentModel)
    updateField(['llm', 'models'], remaining)
    // 删除的是当前模型时，回落到一个剩余预置或该 Provider 默认
    const next = remaining[0]?.name || PROVIDER_DEFAULTS[provider]?.model || ''
    updateField(['llm', 'model'], next)
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
                  className="w-full h-9 rounded-md bg-white/[0.06] border border-white/[0.06] px-3 text-[13px] text-white outline-none [color-scheme:dark]"
                  value={form.llm?.provider || ''}
                  onChange={e => onChangeProvider(e.target.value)}
                >
                  {providerOptions.map(p => (
                    <option key={p} value={p} style={optionDark}>{PROVIDER_LABELS[p] || p}</option>
                  ))}
                </select>
              </div>
              <div className="flex items-center justify-end gap-4">
                {isCurrentAPreset && (
                  <button type="button" onClick={onDeleteModel} className="text-[12px] text-[#FF453A] hover:text-[#FF6B5E]">删除当前模型</button>
                )}
                <button type="button" onClick={openNewModel} className="text-[12px] text-[#2997FF] hover:text-[#40A9FF]">＋ 添加新模型</button>
              </div>
              {addModelOpen && (
                <div className="mt-2 space-y-2 rounded-md border border-white/[0.08] bg-white/[0.03] p-3">
                  <div className="text-[12px] font-medium text-white/40">添加新模型</div>
                  <Input
                    placeholder="模型名称，如 deepseek-r1"
                    value={newModel.name}
                    onChange={e => setNewModel({ ...newModel, name: e.target.value })}
                    className="bg-white/[0.06] border-white/[0.06] text-white"
                    autoFocus
                  />
                  <div className="grid grid-cols-2 gap-2">
                    <Input
                      placeholder="Provider（默认当前）"
                      value={newModel.provider}
                      onChange={e => setNewModel({ ...newModel, provider: e.target.value })}
                      className="bg-white/[0.06] border-white/[0.06] text-white"
                    />
                    <Input
                      placeholder="Base URL（可选）"
                      value={newModel.base_url}
                      onChange={e => setNewModel({ ...newModel, base_url: e.target.value })}
                      className="bg-white/[0.06] border-white/[0.06] text-white"
                    />
                  </div>
                  <Input
                    type="password"
                    placeholder="API Key（可选，仅保存在服务端，界面不回显）"
                    value={newModel.api_key}
                    onChange={e => setNewModel({ ...newModel, api_key: e.target.value })}
                    className="bg-white/[0.06] border-white/[0.06] text-white"
                    autoComplete="off"
                  />
                  <div className="flex gap-2 justify-end">
                    <Button variant="ghost" size="sm" onClick={() => setAddModelOpen(false)} className="text-white/50 h-7">取消</Button>
                    <Button size="sm" disabled={!newModel.name.trim()} onClick={addModel} className="bg-[#2997FF] hover:bg-[#40A9FF] text-white h-7">添加</Button>
                  </div>
                </div>
              )}
              <div>
                <label className="text-[12.5px] font-medium text-white/50 mb-1.5 block">模型</label>
                <select
                  className="w-full h-9 rounded-md bg-white/[0.06] border border-white/[0.06] px-3 text-[13px] text-white outline-none [color-scheme:dark]"
                  value={modelInList || !currentModel ? currentModel : '__CUSTOM__'}
                  onChange={e => {
                    const v = e.target.value
                    if (v === '__CUSTOM__') openNewModel()
                    else updateField(['llm', 'model'], v)
                  }}
                >
                  {modelOptions.map(m => <option key={m} value={m} style={optionDark}>{m}</option>)}
                  {!modelInList && currentModel && (
                    <option value="__CUSTOM__" style={optionDark}>{currentModel}（当前自定义）</option>
                  )}
                </select>
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
