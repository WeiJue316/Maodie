import { useState, useEffect } from 'react'
import { toolsApi } from '../../services/api'
import { ToolLog } from '../../types'
import { Card, CardContent } from '@/components/ui/card'
import { ScrollArea } from '@/components/ui/scroll-area'
import { FadeIn } from '@/components/effects/FadeIn'
import { CheckCircle, XCircle } from 'lucide-react'

export default function ToolsPage() {
  const [logs, setLogs] = useState<ToolLog[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    toolsApi.getLogs({}).then(setLogs).catch(() => {}).finally(() => setLoading(false))
  }, [])

  const totalCalls = logs.length
  const successCalls = logs.filter(l => l.status === 'success').length
  const avgDuration = logs.length > 0
    ? (logs.reduce((sum, l) => sum + l.duration, 0) / logs.length).toFixed(1)
    : '0'

  return (
    <div className="flex flex-col p-6 gap-5 h-full overflow-y-auto">
      {/* Stats */}
      <div className="grid grid-cols-3 gap-4">
        {[
          { label: '已注册工具', value: '6', color: '#2997FF' },
          { label: '今日调用', value: totalCalls, color: '#30D158', sub: totalCalls > 0 ? `成功 ${successCalls}` : '' },
          { label: '平均耗时', value: avgDuration + 's', color: '#FF9F0A' },
        ].map((s, i) => (
          <FadeIn key={s.label} delay={i * 80}>
            <Card className="bg-white/[0.03] border-white/[0.06] relative overflow-hidden">
              <div className="absolute top-0 left-0 right-0 h-[2px]" style={{ background: s.color }} />
              <CardContent className="p-5">
                <div className="text-[11px] font-semibold text-white/30 uppercase tracking-wider mb-2">{s.label}</div>
                <div className="text-[28px] font-bold tracking-tight text-white">{s.value}</div>
                {s.sub && <div className="text-[12px] text-[#30D158] mt-1">{s.sub}</div>}
              </CardContent>
            </Card>
          </FadeIn>
        ))}
      </div>

      {/* Table */}
      <Card className="bg-white/[0.03] border-white/[0.06] flex-1">
        <div className="grid grid-cols-[120px_1fr_100px_100px_160px] px-5 py-3 border-b border-white/[0.04] text-[11.5px] font-semibold text-white/30 uppercase tracking-wider">
          <span>工具名</span><span>状态</span><span>耗时</span><span>结果</span><span>时间</span>
        </div>
        <ScrollArea className="flex-1">
          {loading ? (
            <div className="text-center py-10 text-white/30 text-sm">加载中...</div>
          ) : logs.length === 0 ? (
            <div className="text-center py-10 text-white/30 text-sm">暂无工具调用记录</div>
          ) : (
            logs.map((log, i) => (
              <FadeIn key={log.id} delay={i * 20}>
                <div className="grid grid-cols-[120px_1fr_100px_100px_160px] px-5 py-3.5 border-b border-white/[0.03] items-center text-[13px] hover:bg-white/[0.02] transition-colors">
                  <span className="font-mono text-[12.5px] text-[#2997FF] font-medium">{log.tool_name}</span>
                  <span className="flex items-center gap-1.5 text-[12px] font-medium" style={{ color: log.status === 'success' ? '#30D158' : '#FF453A' }}>
                    {log.status === 'success' ? <CheckCircle className="w-3.5 h-3.5" /> : <XCircle className="w-3.5 h-3.5" />}
                    {log.status === 'success' ? '成功' : '失败'}
                  </span>
                  <span className="text-white/50" style={{ fontVariantNumeric: 'tabular-nums' }}>{log.duration.toFixed(2)}s</span>
                  <span className="text-white/30 text-xs truncate">{log.result?.slice(0, 30) || '-'}</span>
                  <span className="text-white/30" style={{ fontVariantNumeric: 'tabular-nums' }}>
                    {new Date(log.created_at).toLocaleString('zh-CN')}
                  </span>
                </div>
              </FadeIn>
            ))
          )}
        </ScrollArea>
      </Card>
    </div>
  )
}
