import { useState, useEffect, useRef } from 'react'
import { useSelector, useDispatch } from 'react-redux'
import { RootState, AppDispatch } from '../../store'
import { fetchSessions, createSession, deleteSession, setCurrentSession } from '../../store/sessionSlice'
import { sessionApi } from '../../services/api'
import { Message } from '../../types'
import { Button } from '@/components/ui/button'
import { ScrollArea } from '@/components/ui/scroll-area'
import { SpotlightCard } from '@/components/effects/SpotlightCard'
import { FadeIn } from '@/components/effects/FadeIn'
import DecryptedText from '@/components/effects/DecryptedText'
import { Plus, Send, Trash2, MessageSquare } from 'lucide-react'

// 解密动画时长随回复长度伸缩：短回复快速收尾，长回复从容展开。
// 以每帧 speed 反推总时长，约 0.5s ~ 2s。
const revealDurationFor = (totalLen: number) => {
  const maxIterations = 12
  const ms = 420 + totalLen * 5 // ≈5ms/字符，100 字≈0.9s
  const capped = Math.min(ms, 2000)
  return Math.round(capped / maxIterations)
}

export default function SessionPage() {
  const dispatch = useDispatch<AppDispatch>()
  const { sessions, currentSessionId, loading } = useSelector((state: RootState) => state.session)
  const [messages, setMessages] = useState<Message[]>([])
  const [inputValue, setInputValue] = useState('')
  const [sending, setSending] = useState(false)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  // 记录当前正在展示的会话 id，用于在异步加载/流式回填时判断会话是否已被切换
  const activeSessionRef = useRef<string | null>(null)
  // 标记本轮刚生成、需要以「解密」动画呈现的 assistant 消息对象（引用唯一，切换会话时清空）
  const revealSetRef = useRef<Set<Message>>(new Set())

  useEffect(() => { dispatch(fetchSessions()) }, [dispatch])

  useEffect(() => {
    activeSessionRef.current = currentSessionId
    revealSetRef.current.clear()
    if (!currentSessionId) { setMessages([]); return }
    // 切换会话时先立即清空旧消息，避免把上一个会话的内容串到新页面里
    setMessages([])
    loadMessages(currentSessionId)
  }, [currentSessionId])

  const loadMessages = async (sessionId: string) => {
    try {
      const msgs = await sessionApi.getMessages(sessionId)
      // 若请求返回前用户已切走，直接丢弃，防止乱序覆盖别的会话
      if (activeSessionRef.current === sessionId) setMessages(msgs)
    } catch (e) { console.error('Failed to load messages:', e) }
  }

  const handleCreateSession = async () => {
    try { await dispatch(createSession()).unwrap() } catch {}
  }

  const handleDeleteSession = async (id: string, e: React.MouseEvent) => {
    e.stopPropagation()
    try { await dispatch(deleteSession(id)).unwrap() } catch {}
  }

  const handleSend = async () => {
    if (!inputValue.trim() || !currentSessionId || sending) return
    const sessionId = currentSessionId  // 固定本次发送所属的会话，防止流式过程中切走导致串页
    const content = inputValue
    setInputValue('')
    setSending(true)
    if (activeSessionRef.current !== sessionId) return
    setMessages(prev => [...prev, { role: 'user', content }])

    try {
      const response = await fetch(`/api/sessions/${sessionId}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content }),
      })
      const reader = response.body?.getReader()
      const decoder = new TextDecoder()
      let assistantContent = ''

      if (activeSessionRef.current === sessionId)
        setMessages(prev => [...prev, { role: 'assistant', content: '' }])

      while (reader && activeSessionRef.current === sessionId) {
        const { done, value } = await reader.read()
        if (done) break
        const text = decoder.decode(value)
        for (const line of text.split('\n')) {
          if (!line.startsWith('data: ')) continue
          try {
            const data = JSON.parse(line.slice(6))
            if (data.type === 'token') {
              assistantContent += data.content
              // 仅在用户仍停留在这个会话时才继续收流，否则丢弃，避免串进别的会话
              if (activeSessionRef.current !== sessionId) return
            }
          } catch {}
        }
      }
      // 整段回复收完后，一次性写入并标记为「解密」动画呈现（期间气泡只显示思考动画）
      if (activeSessionRef.current === sessionId) {
        setMessages(prev => {
          const msgs = [...prev]
          const last = msgs[msgs.length - 1]
          if (last?.role === 'assistant') {
            last.content = assistantContent
            revealSetRef.current.add(last)
          }
          return msgs
        })
        dispatch(fetchSessions())
      }
    } catch {
      if (activeSessionRef.current === sessionId) setMessages(prev => prev.slice(0, -1))
    } finally {
      if (activeSessionRef.current === sessionId) setSending(false)
    }
  }

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const handleTextareaInput = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInputValue(e.target.value)
    const el = e.target
    el.style.height = 'auto'
    el.style.height = Math.min(el.scrollHeight, 120) + 'px'
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend() }
  }

  return (
    <div className="flex h-full min-h-0">
      {/* Session list */}
      <div className="w-[280px] border-r border-white/[0.06] flex flex-col shrink-0 min-h-0">
        <div className="px-4 py-3 border-b border-white/[0.04] flex items-center justify-between">
          <span className="text-[13px] font-semibold text-white/50">会话列表</span>
          <Button size="sm" onClick={handleCreateSession} className="h-7 px-2.5 text-xs bg-[#2997FF] hover:bg-[#40A9FF] text-white">
            <Plus className="w-3 h-3 mr-1" />
            新建
          </Button>
        </div>
        <ScrollArea className="flex-1 min-h-0">
          <div className="p-2">
            {loading ? (
              <div className="text-center py-8 text-white/30 text-sm">加载中...</div>
            ) : sessions.length === 0 ? (
              <div className="text-center py-8 text-white/30 text-sm">暂无会话</div>
            ) : (
              sessions.map((session, i) => (
                <FadeIn key={session.id} delay={i * 30} direction="up">
                  <SpotlightCard className="mb-1 cursor-pointer">
                    <div
                      onClick={() => dispatch(setCurrentSession(session.id))}
                      className={`p-3 rounded-[var(--radius)] ${currentSessionId === session.id ? 'bg-[#2997FF]/[0.08]' : ''}`}
                    >
                      <div className="flex items-center gap-2 mb-1">
                        <MessageSquare className="w-3.5 h-3.5 text-white/30 shrink-0" />
                        <span className="text-[13.5px] font-medium truncate text-white/80">{session.title || '新会话'}</span>
                      </div>
                      <div className="flex items-center gap-2 text-[11.5px] text-white/30">
                        <span className="w-1.5 h-1.5 rounded-full bg-white/20 shrink-0" />
                        <span>{new Date(session.updated_at).toLocaleDateString('zh-CN')} {new Date(session.updated_at).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })}</span>
                        <button
                          onClick={(e) => handleDeleteSession(session.id, e)}
                          className="ml-auto p-0.5 text-white/20 hover:text-[#FF453A] transition-colors opacity-0 group-hover:opacity-100"
                        >
                          <Trash2 className="w-3 h-3" />
                        </button>
                      </div>
                    </div>
                  </SpotlightCard>
                </FadeIn>
              ))
            )}
          </div>
        </ScrollArea>
      </div>

      {/* Chat */}
      <div className="flex-1 flex flex-col min-h-0">
        {currentSessionId ? (
          <>
            <div className="flex-1 min-h-0 overflow-y-auto p-6 pr-3 [scrollbar-width:thin] [scrollbar-color:rgba(255,255,255,0.3)_transparent]">
              <div className="space-y-5 max-w-[85%]">
                {messages.map((msg, i) => (
                  <FadeIn key={i} delay={i < 5 ? i * 50 : 0} direction={msg.role === 'user' ? 'right' : 'left'}>
                    <div className={`flex gap-3 ${msg.role === 'user' ? 'flex-row-reverse' : ''}`}>
                      <div className={`
                        w-[30px] h-[30px] rounded-full flex items-center justify-center text-xs font-semibold text-white shrink-0
                        ${msg.role === 'user'
                          ? 'bg-gradient-to-br from-[#5856D6] to-[#AF52DE]'
                          : 'bg-gradient-to-br from-[#2997FF] to-[#1A7AE6]'
                        }
                      `}>
                        {msg.role === 'user' ? 'LY' : 'A'}
                      </div>
                      <div className={msg.role === 'user' ? 'text-right' : ''}>
                        <div className={`
                          inline-block px-4 py-3 rounded-2xl text-[13.5px] leading-relaxed max-w-full
                          ${msg.role === 'user'
                            ? 'bg-[#2997FF] text-white rounded-tr-sm'
                            : 'bg-white/[0.04] border border-white/[0.06] text-white/90 rounded-tl-sm'
                          }
                        `}>
                          {msg.role === 'assistant' && !msg.content && sending ? (
                            <div className="dot-spinner"><span /><span /><span /></div>
                          ) : revealSetRef.current.has(msg) ? (
                            <DecryptedText
                              text={msg.content}
                              animateOn="view"
                              revealDirection="center"
                              maxIterations={12}
                              speed={revealDurationFor(msg.content.length)}
                              characters="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789#@$%&*+=?中文字"
                            />
                          ) : (
                            <div className="whitespace-pre-wrap">{msg.content}</div>
                          )}
                        </div>
                        <div className="text-[11px] text-white/25 mt-1">
                          {new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })}
                        </div>
                      </div>
                    </div>
                  </FadeIn>
                ))}
                <div ref={messagesEndRef} />
              </div>
            </div>

            {/* Input */}
            <div className="px-6 pb-5 pt-4 border-t border-white/[0.04]">
              <div className="flex items-end gap-2.5 bg-white/[0.06] border border-white/[0.06] rounded-2xl px-4 py-2.5 focus-within:border-[#2997FF]/50 transition-colors">
                <textarea
                  ref={textareaRef}
                  value={inputValue}
                  onChange={handleTextareaInput}
                  onKeyDown={handleKeyDown}
                  placeholder="输入消息…"
                  rows={1}
                  disabled={sending}
                  className="flex-1 bg-transparent border-none outline-none text-white text-sm resize-none min-h-[20px] max-h-[120px] leading-normal placeholder:text-white/25"
                />
                <Button
                  size="icon"
                  onClick={handleSend}
                  disabled={sending}
                  className="w-8 h-8 rounded-full bg-[#2997FF] hover:bg-[#40A9FF] text-white shrink-0"
                >
                  <Send className="w-4 h-4" />
                </Button>
              </div>
            </div>
          </>
        ) : (
          <div className="flex-1 flex flex-col items-center justify-center text-white/25 gap-3">
            <MessageSquare className="w-12 h-12" strokeWidth={1} />
            <span className="text-sm">选择或创建一个会话</span>
          </div>
        )}
      </div>
    </div>
  )
}
