import { useState, useEffect } from 'react'
import { skillsApi } from '../../services/api'
import { Skill } from '../../types'
import { Badge } from '@/components/ui/badge'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { SpotlightCard } from '@/components/effects/SpotlightCard'
import { FadeIn } from '@/components/effects/FadeIn'
import { BookOpen } from 'lucide-react'

const skillColors = ['bg-[#2997FF]/10 text-[#2997FF]', 'bg-[#30D158]/10 text-[#30D158]', 'bg-[#FF9F0A]/10 text-[#FF9F0A]', 'bg-[#BF5AF2]/10 text-[#BF5AF2]', 'bg-[#FF453A]/10 text-[#FF453A]']

export default function SkillPage() {
  const [skills, setSkills] = useState<Skill[]>([])
  const [loading, setLoading] = useState(true)
  const [selected, setSelected] = useState<Skill | null>(null)
  const [content, setContent] = useState('')
  const [loadingContent, setLoadingContent] = useState(false)

  useEffect(() => {
    skillsApi.list().then(setSkills).catch(() => {}).finally(() => setLoading(false))
  }, [])

  const handleSelect = async (skill: Skill) => {
    setSelected(skill)
    setLoadingContent(true)
    try { const d = await skillsApi.getContent(skill.name); setContent(d.content) }
    catch { setContent('加载失败') }
    finally { setLoadingContent(false) }
  }

  return (
    <div className="flex flex-col p-6 gap-5 h-full overflow-y-auto">
      <div className="flex items-center justify-between">
        <span className="text-lg font-semibold text-white">技能库</span>
        <span className="text-[12px] text-white/30">共 {skills.length} 个技能</span>
      </div>

      {loading ? (
        <div className="text-center py-10 text-white/30 text-sm">加载中...</div>
      ) : skills.length === 0 ? (
        <div className="text-center py-10 text-white/30 text-sm">暂无技能</div>
      ) : (
        <div className="grid grid-cols-[repeat(auto-fill,minmax(300px,1fr))] gap-4">
          {skills.map((skill, i) => (
            <FadeIn key={skill.name} delay={i * 60}>
              <SpotlightCard className="cursor-pointer" >
                <div className="p-5" onClick={() => handleSelect(skill)}>
                  <div className={`w-9 h-9 rounded-lg flex items-center justify-center text-lg mb-3.5 ${skillColors[i % skillColors.length]}`}>
                    <BookOpen className="w-5 h-5" />
                  </div>
                  <div className="text-[14.5px] font-semibold text-white mb-1.5">{skill.name}</div>
                  <div className="text-[12.5px] text-white/45 leading-relaxed line-clamp-2">
                    {skill.description || '无描述'}
                  </div>
                  <div className="flex items-center gap-2 mt-3.5">
                    <Badge variant="secondary" className={`text-[11px] ${skillColors[i % skillColors.length]}`}>
                      {skill.tools.length} 工具
                    </Badge>
                    {skill.unavailable_tools.length > 0 && (
                      <Badge variant="secondary" className="text-[11px] bg-[#FF453A]/10 text-[#FF453A]">
                        {skill.unavailable_tools.length} 不可用
                      </Badge>
                    )}
                  </div>
                </div>
              </SpotlightCard>
            </FadeIn>
          ))}
        </div>
      )}

      {/* Detail Dialog */}
      <Dialog open={!!selected} onOpenChange={(open) => { if (!open) setSelected(null) }}>
        <DialogContent className="bg-[#1A1A1A] border-white/[0.08] text-white max-w-lg">
          <DialogHeader>
            <DialogTitle className="text-white">{selected?.name}</DialogTitle>
          </DialogHeader>
          {selected && (
            <div className="space-y-4">
              <p className="text-[13px] text-white/50">{selected.description}</p>
              {selected.tools.length > 0 && (
                <div>
                  <div className="text-[12px] font-medium text-white/40 mb-2">依赖工具</div>
                  <div className="flex flex-wrap gap-1.5">
                    {selected.tools.map(t => <Badge key={t} variant="secondary" className="text-[11px] bg-[#2997FF]/10 text-[#2997FF]">{t}</Badge>)}
                  </div>
                </div>
              )}
              {selected.unavailable_tools.length > 0 && (
                <div>
                  <div className="text-[12px] font-medium text-[#FF453A] mb-2">不可用工具</div>
                  <div className="flex flex-wrap gap-1.5">
                    {selected.unavailable_tools.map(t => <Badge key={t} variant="secondary" className="text-[11px] bg-[#FF453A]/10 text-[#FF453A]">{t}</Badge>)}
                  </div>
                </div>
              )}
              <div>
                <div className="text-[12px] font-medium text-white/40 mb-2">内容</div>
                {loadingContent ? (
                  <div className="text-white/30 text-[13px]">加载中...</div>
                ) : (
                  <pre className="text-[12px] text-white/50 bg-white/[0.03] p-4 rounded-lg overflow-auto max-h-[300px] font-mono whitespace-pre-wrap">
                    {content}
                  </pre>
                )}
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  )
}
