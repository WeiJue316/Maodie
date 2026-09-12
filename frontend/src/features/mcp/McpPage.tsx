import { useState, useEffect } from 'react'
import { mcpApi } from '../../services/api'
import { MCPServer, MCPTool } from '../../types'
import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { FadeIn } from '@/components/effects/FadeIn'
import { Cpu, RefreshCw, ChevronDown } from 'lucide-react'

export default function McpPage() {
  const [servers, setServers] = useState<MCPServer[]>([])
  const [tools, setTools] = useState<MCPTool[]>([])
  const [loading, setLoading] = useState(true)
  const [reconnecting, setReconnecting] = useState<string | null>(null)

  useEffect(() => { loadData() }, [])

  const loadData = async () => {
    setLoading(true)
    try {
      const [s, t] = await Promise.all([mcpApi.getServers(), mcpApi.getTools()])
      setServers(s); setTools(t)
    } catch {}
    finally { setLoading(false) }
  }

  const handleReconnect = async (name: string) => {
    setReconnecting(name)
    try { await mcpApi.reconnect(name); loadData() } catch {}
    finally { setReconnecting(null) }
  }

  const toolsByServer = tools.reduce((acc, t) => {
    (acc[t.server] = acc[t.server] || []).push(t)
    return acc
  }, {} as Record<string, MCPTool[]>)

  return (
    <div className="flex flex-col p-6 gap-5 h-full overflow-y-auto">
      <div className="flex items-center justify-between">
        <span className="text-lg font-semibold text-white">MCP 服务器</span>
        <Button variant="ghost" size="sm" onClick={loadData} disabled={loading} className="text-white/50">
          <RefreshCw className="w-4 h-4 mr-1.5" />
          刷新
        </Button>
      </div>

      {loading ? (
        <div className="text-center py-10 text-white/30 text-sm">加载中...</div>
      ) : (
        <ScrollArea className="flex-1">
          <div className="space-y-3">
            {servers.length === 0 ? (
              <div className="text-center py-10 text-white/30 text-sm">暂无 MCP 服务器</div>
            ) : (
              servers.map((server, i) => (
                <FadeIn key={server.name} delay={i * 80}>
                  <Card className="bg-white/[0.03] border-white/[0.06]">
                    <CardContent className="p-5">
                      <div className="flex items-center justify-between mb-3">
                        <div className="flex items-center gap-3">
                          <div className={`w-[34px] h-[34px] rounded-lg flex items-center justify-center ${server.connected ? 'bg-[#2997FF]/10' : 'bg-[#FF453A]/10'}`}>
                            <Cpu className="w-[18px] h-[18px]" style={{ color: server.connected ? '#2997FF' : '#FF453A' }} />
                          </div>
                          <div>
                            <div className="font-semibold text-[14px] text-white">{server.name}</div>
                            <div className="text-[11.5px] text-white/30 font-mono">{server.transport}</div>
                          </div>
                        </div>
                        <div className="flex items-center gap-2">
                          <Badge variant="secondary" className={`text-[12px] font-medium ${server.connected ? 'bg-[#30D158]/10 text-[#30D158]' : 'bg-[#FF453A]/10 text-[#FF453A]'}`}>
                            {server.connected ? '在线' : '离线'}
                          </Badge>
                          <Button variant="ghost" size="sm" onClick={() => handleReconnect(server.name)} disabled={reconnecting === server.name} className="text-white/40 h-7 px-2 text-[12px]">
                            {reconnecting === server.name ? '重连中...' : '重连'}
                          </Button>
                        </div>
                      </div>
                      {server.error && (
                        <div className="px-3 py-2 bg-[#FF453A]/10 rounded-md text-[12px] text-[#FF453A] mb-3">
                          {server.error}
                        </div>
                      )}
                      {server.tools.length > 0 && (
                        <div className="border-t border-white/[0.04] pt-3 mt-1">
                          <div className="text-[12px] text-white/30 font-medium mb-2">可用工具 ({server.tools.length})</div>
                          <div className="flex flex-wrap gap-1.5">
                            {server.tools.map(t => (
                              <Badge key={t} variant="secondary" className="text-[11px] bg-white/[0.04] text-white/50 font-mono">
                                {t}
                              </Badge>
                            ))}
                          </div>
                        </div>
                      )}
                    </CardContent>
                  </Card>
                </FadeIn>
              ))
            )}

            {/* Tools by server */}
            {Object.keys(toolsByServer).length > 0 && (
              <div className="mt-4">
                <div className="text-lg font-semibold text-white mb-3">MCP 工具</div>
                {Object.entries(toolsByServer).map(([server, serverTools], i) => (
                  <FadeIn key={server} delay={i * 60}>
                    <Collapsible>
                      <Card className="bg-white/[0.03] border-white/[0.06] mb-2">
                        <CollapsibleTrigger className="w-full">
                          <CardContent className="p-4 flex items-center justify-between">
                            <div className="flex items-center gap-2">
                              <span className="text-[13px] font-medium text-white">{server}</span>
                              <Badge variant="secondary" className="text-[11px] bg-[#2997FF]/10 text-[#2997FF]">{serverTools.length} 工具</Badge>
                            </div>
                            <ChevronDown className="w-4 h-4 text-white/30" />
                          </CardContent>
                        </CollapsibleTrigger>
                        <CollapsibleContent>
                          <div className="px-4 pb-4 space-y-2">
                            {serverTools.map(t => (
                              <div key={t.name} className="py-2.5 border-t border-white/[0.04]">
                                <div className="font-mono text-[12.5px] text-[#2997FF] mb-1">{t.name}</div>
                                <div className="text-[12px] text-white/40">{t.description}</div>
                              </div>
                            ))}
                          </div>
                        </CollapsibleContent>
                      </Card>
                    </Collapsible>
                  </FadeIn>
                ))}
              </div>
            )}
          </div>
        </ScrollArea>
      )}
    </div>
  )
}
