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
import { Plus, Send, Trash2, MessageSquare } from 'lucide-react'

export default function SessionPage() {
  const dispatch = useDispatch<AppDispatch>()
  const { sessions, currentSessionId, loading } = useSelector((state: RootState) => state.session)
  const [messages, setMessages] = useState<Message[]>([])
  const [inputValue, setInputValue] = useState('')
  const [sending, setSending] = useState(false)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => { dispatch(fetchSessions()) }, [dispatch])
  useEffect(() => { if (currentSessionId) loadMessages(currentSessionId) }, [currentSessionId])

  const loadMessages = async (sessionId: string) => {
    try { setMessages(await sessionApi.getMessages(sessionId)) }
    catch (e) { console.error('Failed to load messages:', e) }
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
    const content = inputValue
    setInputValue('')
    setSending(true)
    setMessages(prev => [...prev, { role: 'user', content }])

    try {
      const response = await fetch(`/api/sessions/${currentSessionId}/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content }),
      })
      const reader = response.body?.getReader()
      const decoder = new TextDecoder()
      let assistantContent = ''

      setMessages(prev => [...prev, { role: 'assistant', content: '' }])

      while (reader) {
        const { done, value } = await reader.read()
        if (done) break
        const text = decoder.decode(value)
        for (const line of text.split('\n')) {
          if (!line.startsWith('data: ')) continue
          try {
            const data = JSON.parse(line.slice(6))
            if (data.type === 'token') {
              assistantContent += data.content
              setMessages(prev => {
                const msgs = [...prev]
                const last = msgs[msgs.length - 1]
                if (last.role === 'assistant') last.content = assistantContent
                return msgs
              })
            }
          } catch {}
        }
      }
      dispatch(fetchSessions())
    } catch {
      setMessages(prev => prev.slice(0, -1))
    } finally {
      setSending(false)
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
    <div className="flex h-full">
      {/* Session list */}
      <div className="w-[280px] border-r border-white/[0.06] flex flex-col shrink-0">
        <div className="px-4 py-3 border-b border-white/[0.04] flex items-center justify-between">
          <span className="text-[13px] font-semibold text-white/50">会话列表</span>
          <Button size="sm" onClick={handleCreateSession} className="h-7 px-2.5 text-xs bg-[#2997FF] hover:bg-[#40A9FF] text-white">
            <Plus className="w-3 h-3 mr-1" />
            新建
          </Button>
        </div>
        <ScrollArea className="flex-1">
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
      <div className="flex-1 flex flex-col">
        {currentSessionId ? (
          <>
            <ScrollArea className="flex-1 p-6">
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
            </ScrollArea>

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
