import { useState, useEffect } from 'react'
import { useSelector, useDispatch } from 'react-redux'
import { RootState, AppDispatch } from '../../store'
import { fetchObservations, fetchMemoryStats } from '../../store/memorySlice'
import { memoryApi } from '../../services/api'
import { Observation } from '../../types'
import { Card, CardContent } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { ScrollArea } from '@/components/ui/scroll-area'
import { SpotlightCard } from '@/components/effects/SpotlightCard'
import { FadeIn } from '@/components/effects/FadeIn'
import { Search, ArrowUp, Database, FileText } from 'lucide-react'

const typeColors: Record<string, string> = {
  bugfix: 'bg-[#FF453A]/10 text-[#FF453A]',
  feature: 'bg-[#2997FF]/10 text-[#2997FF]',
  refactor: 'bg-[#30D158]/10 text-[#30D158]',
  change: 'bg-[#FF9F0A]/10 text-[#FF9F0A]',
  discovery: 'bg-[#BF5AF2]/10 text-[#BF5AF2]',
  decision: 'bg-[#2997FF]/10 text-[#2997FF]',
}

export default function MemoryPage() {
  const dispatch = useDispatch<AppDispatch>()
  const { observations, stats, loading } = useSelector((state: RootState) => state.memory)
  const [searchText, setSearchText] = useState('')
  const [searchResults, setSearchResults] = useState<Observation[]>([])


  useEffect(() => { dispatch(fetchObservations()); dispatch(fetchMemoryStats()) }, [dispatch])

  const handleSearch = async () => {
    if (!searchText.trim()) return
    try { setSearchResults(await memoryApi.search(searchText)) } catch {}
  }

  const handlePromote = async (id: string) => {
    try { await memoryApi.promote(id); dispatch(fetchObservations()); dispatch(fetchMemoryStats()) } catch {}
  }

  const displayObs = searchText ? searchResults : observations

  return (
    <div className="flex flex-col p-6 gap-6 h-full overflow-y-auto">
      {/* Stats */}
      {stats && (
        <div className="grid grid-cols-4 gap-4">
          {[
            { label: '总记忆数', value: stats.total_observations, color: '#2997FF' },
            { label: '已晋升', value: stats.promoted_count, color: '#30D158' },
            { label: 'FTS5', value: stats.fts5_available ? '可用' : '不可用', color: '#FF9F0A' },
            { label: '向量索引', value: stats.vectordb_count, color: '#BF5AF2' },
          ].map((s, i) => (
            <FadeIn key={s.label} delay={i * 80}>
              <Card className="bg-white/[0.03] border-white/[0.06] relative overflow-hidden">
                <div className="absolute top-0 left-0 right-0 h-[2px]" style={{ background: s.color }} />
                <CardContent className="p-5">
                  <div className="text-[11px] font-semibold text-white/30 uppercase tracking-wider mb-2">{s.label}</div>
                  <div className="text-[28px] font-bold tracking-tight text-white" style={{ fontVariantNumeric: 'tabular-nums' }}>
                    {s.value}
                  </div>
                </CardContent>
              </Card>
            </FadeIn>
          ))}
        </div>
      )}

      {/* Tabs */}
      <Tabs defaultValue="observations" className="flex-1 flex flex-col">
        <TabsList className="bg-transparent border-b border-white/[0.04] rounded-none h-auto p-0 w-full justify-start gap-0">
          <TabsTrigger value="observations" className="rounded-none border-b-2 border-transparent data-[state=active]:border-[#2997FF] data-[state=active]:bg-transparent data-[state=active]:text-white text-white/40 px-4 py-2 text-sm font-medium">
            <Database className="w-4 h-4 mr-1.5" />
            Observations
          </TabsTrigger>
          <TabsTrigger value="long-term" className="rounded-none border-b-2 border-transparent data-[state=active]:border-[#2997FF] data-[state=active]:bg-transparent data-[state=active]:text-white text-white/40 px-4 py-2 text-sm font-medium">
            <FileText className="w-4 h-4 mr-1.5" />
            长期记忆
          </TabsTrigger>
        </TabsList>

        <TabsContent value="observations" className="flex-1 flex flex-col gap-4 mt-4">
          {/* Search */}
          <div className="flex gap-2 items-center">
            <div className="relative flex-1 max-w-[400px]">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-white/30" />
              <Input
                placeholder="搜索记忆…"
                value={searchText}
                onChange={(e) => setSearchText(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter') handleSearch() }}
                className="pl-9 bg-white/[0.06] border-white/[0.06] text-white placeholder:text-white/25"
              />
            </div>
            {searchText && (
              <Button variant="ghost" size="sm" onClick={() => { setSearchText(''); setSearchResults([]) }} className="text-white/40">
                清除
              </Button>
            )}
          </div>

          {/* Observation list */}
          <ScrollArea className="flex-1">
            <div className="space-y-2">
              {loading ? (
                <div className="text-center py-10 text-white/30 text-sm">加载中...</div>
              ) : displayObs.length === 0 ? (
                <div className="text-center py-10 text-white/30 text-sm">暂无记忆</div>
              ) : (
                displayObs.map((obs, i) => (
                  <FadeIn key={obs.id} delay={i * 40}>
                    <SpotlightCard>
                      <div className="p-4">
                        <div className="flex items-start justify-between mb-2">
                          <div className="flex items-center gap-2">
                            <Badge variant="secondary" className={`text-[11px] font-medium ${typeColors[obs.type] || ''}`}>
                              {obs.type}
                            </Badge>
                            {obs.title && <span className="text-[13px] font-medium text-white">{obs.title}</span>}
                          </div>
                          <div className="flex items-center gap-2">
                            <span className="text-[12px] text-white/40 flex items-center gap-1">
                              <span className={`w-1.5 h-1.5 rounded-full ${obs.relevance_count >= 3 ? 'bg-[#30D158]' : 'bg-[#FF9F0A]'}`} />
                              引用 {obs.relevance_count}
                            </span>
                            {obs.promoted === 1 ? (
                              <Badge variant="secondary" className="text-[11px] bg-[#30D158]/10 text-[#30D158]">已晋升</Badge>
                            ) : obs.relevance_count >= 3 ? (
                              <Button size="sm" variant="ghost" className="h-6 px-2 text-[11px] text-[#2997FF] hover:bg-[#2997FF]/10" onClick={() => handlePromote(obs.id)}>
                                <ArrowUp className="w-3 h-3 mr-0.5" />
                                晋升
                              </Button>
                            ) : null}
                          </div>
                        </div>
                        <p className="text-[13.5px] leading-relaxed text-white/70 mb-2">{obs.narrative}</p>
                        {obs.facts.length > 0 && (
                          <div className="text-[12px] text-white/40 mb-1">事实：{obs.facts.join(' · ')}</div>
                        )}
                        <div className="text-[11.5px] text-white/25 flex items-center gap-3">
                          <span>来源: {obs.session_id.slice(0, 16)}...</span>
                          <span>{new Date(obs.created_at).toLocaleString('zh-CN')}</span>
                          {obs.concepts.length > 0 && <span>概念: {obs.concepts.join(', ')}</span>}
                        </div>
                      </div>
                    </SpotlightCard>
                  </FadeIn>
                ))
              )}
            </div>
          </ScrollArea>
        </TabsContent>

        <TabsContent value="long-term" className="flex-1 mt-4">
          <LongTermMemoryView />
        </TabsContent>
      </Tabs>
    </div>
  )
}

function LongTermMemoryView() {
  const [content, setContent] = useState('')
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    memoryApi.getLongTerm().then(d => setContent(d.content)).catch(() => {}).finally(() => setLoading(false))
  }, [])

  if (loading) return <div className="text-center py-10 text-white/30 text-sm">加载中...</div>

  return (
    <Card className="bg-white/[0.03] border-white/[0.06]">
      <CardContent className="p-5">
        <pre className="text-[13px] leading-relaxed text-white/60 whitespace-pre-wrap font-mono">
          {content || '暂无长期记忆'}
        </pre>
      </CardContent>
    </Card>
  )
}
