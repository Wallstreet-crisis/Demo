import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  Api,
  WsClient,
  type ChatListMessagesResponse,
  type ChatMessageResponse,
  type ChatThreadResponse,
} from '../api'
import { useAppSession } from '../app/context'
import CyberWidget from './CyberWidget'

interface ChatWsEvent {
  event_type?: string;
  payload?: Record<string, unknown>;
}

export default function ChatWidget() {
  const { playerId } = useAppSession()
  const [activeThread, setActiveThread] = useState<'global' | ChatThreadResponse>('global')
  const [messages, setMessages] = useState<ChatMessageResponse[]>([])
  const [threads, setThreads] = useState<ChatThreadResponse[]>([])
  const [text, setText] = useState<string>('')
  const [loading, setLoading] = useState(false)

  const ws = useMemo(() => new WsClient({ baseUrl: import.meta.env.VITE_API_BASE_URL }), [])
  const scrollRef = useRef<HTMLDivElement>(null)

  const refreshMessages = useCallback(async () => {
    try {
      let r: ChatListMessagesResponse
      if (activeThread === 'global') {
        r = await Api.chatPublicMessages(50)
      } else {
        r = await Api.chatPmMessages(activeThread.thread_id, 50)
      }
      setMessages(r.items.slice().reverse()) // Newest at bottom
    } catch (e) {
      console.error('Failed to fetch chat messages', e)
    }
  }, [activeThread])

  const refreshThreads = useCallback(async () => {
    if (!playerId) return
    try {
      const r = await Api.chatThreads(`user:${playerId}`)
      setThreads(r.items)
    } catch (e) {
      console.error('Failed to fetch threads', e)
    }
  }, [playerId])

  useEffect(() => {
    refreshMessages()
    if (playerId) refreshThreads()

    const channel = activeThread === 'global' ? 'chat.public.global' : `chat.pm.${activeThread.thread_id}`
    ws.connect(channel, (payload) => {
      const ev = payload as ChatWsEvent;
      if (ev?.event_type === 'CHAT_MESSAGE_SENT') {
        refreshMessages()
      }
    })
    return () => ws.close()
  }, [activeThread, refreshMessages, refreshThreads, playerId, ws])

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [messages])

  async function send() {
    if (!text.trim() || !playerId) return
    setLoading(true)
    try {
      if (activeThread === 'global') {
        await Api.chatPublicSend({
          sender_id: `user:${playerId}`,
          message_type: 'TEXT',
          content: text,
        })
      } else {
        await Api.chatPmSend({
          thread_id: activeThread.thread_id,
          sender_id: `user:${playerId}`,
          message_type: 'TEXT',
          content: text,
        })
      }
      setText('')
      // Small delay to allow backend to process and WS to trigger
      setTimeout(refreshMessages, 100)
    } catch (e) {
      console.error('Failed to send message', e)
    } finally {
      setLoading(false)
    }
  }

  const openDm = async (targetId: string) => {
    if (!playerId || targetId === `user:${playerId}`) return
    try {
      const res = await Api.chatOpenPm({
        requester_id: `user:${playerId}`,
        target_id: targetId
      })
      await refreshThreads()
      // Switch to the newly opened or existing thread
      const threadId = res.thread_id
      const found = threads.find(t => t.thread_id === threadId)
      if (found) {
        setActiveThread(found)
      } else {
        const updatedThreads = await Api.chatThreads(`user:${playerId}`)
        const newThread = updatedThreads.items.find(t => t.thread_id === threadId)
        if (newThread) setActiveThread(newThread)
      }
    } catch (e: unknown) {
      console.error('Failed to open DM', e)
      // Enhanced error reporting for wealth gap / intro fee
      const err = e as { response?: { data?: { detail?: string } }, message?: string }
      const detail = err?.response?.data?.detail || err?.message || 'SECURE_LINE_FAILED'
      setMessages(prev => [...prev, {
        message_id: `err-${Date.now()}`,
        thread_id: 'internal',
        sender_id: 'system',
        sender_display: 'SYSTEM_ENCRYPTION_ERROR',
        message_type: 'TEXT',
        content: `[!] CONNECTION_DENIED: ${detail}`,
        payload: { sender_caste: 'SYSTEM' },
        created_at: new Date().toISOString()
      }])
    }
  }

  const getAvatarColor = (id: string, caste?: string) => {
    if (caste === 'ELITE' || caste === 'BOT_INSTITUTION') return '#facc15'; // Gold for elite
    if (caste === 'MIDDLE') return '#3b82f6'; // Blue for middle
    if (caste === 'WORKING' || caste === 'BOT_RETAIL') return '#10b981'; // Green for working
    if (caste === 'SYSTEM') return '#ef4444'; // Red for system
    
    const colors = ['#94a3b8', '#64748b', '#475569', '#334155'];
    let hash = 0;
    for (let i = 0; i < id.length; i++) {
      hash = id.charCodeAt(i) + ((hash << 5) - hash);
    }
    return colors[Math.abs(hash) % colors.length];
  }

  return (
    <CyberWidget 
      title={activeThread === 'global' ? "PUBLIC_COMMS" : `SECURE_LINE: ${activeThread.participant_b}`} 
      subtitle={activeThread === 'global' ? "UNENCRYPTED_GLOBAL_BROADCAST" : "P2P_ENCRYPTED_SESSION"}
    >
      <div style={{ display: 'flex', height: '100%', position: 'relative' }}>
        {/* Thread Sidebar */}
        <div style={{ 
          width: '60px', 
          borderRight: '1px solid var(--terminal-border)',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          padding: '10px 0',
          gap: '12px',
          background: 'rgba(0,0,0,0.2)'
        }}>
          <div 
            onClick={() => setActiveThread('global')}
            title="Global Comms"
            style={{ 
              width: '36px', 
              height: '36px', 
              borderRadius: '8px', 
              background: activeThread === 'global' ? '#3b82f6' : 'rgba(51, 65, 85, 0.5)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              cursor: 'pointer',
              fontSize: '18px',
              border: activeThread === 'global' ? '2px solid #fff' : '1px solid transparent',
              transition: 'all 0.2s'
            }}
          >
            🌐
          </div>
          
          <div style={{ width: '30px', height: '1px', background: 'var(--terminal-border)' }} />
          
          {threads.map(t => {
            const color = getAvatarColor(t.participant_b);
            const isActive = typeof activeThread !== 'string' && activeThread.thread_id === t.thread_id;
            return (
              <div 
                key={t.thread_id}
                onClick={() => setActiveThread(t)}
                title={`DM: ${t.participant_b}`}
                style={{ 
                  width: '36px', 
                  height: '36px', 
                  borderRadius: '18px', 
                  background: color,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  cursor: 'pointer',
                  fontSize: '14px',
                  fontWeight: 'bold',
                  color: '#000',
                  border: isActive ? '2px solid #fff' : '1px solid rgba(255,255,255,0.2)',
                  transition: 'all 0.2s',
                  boxShadow: isActive ? `0 0 10px ${color}` : 'none'
                }}
              >
                {t.participant_b[0].toUpperCase()}
              </div>
            );
          })}
        </div>

        {/* Chat Area */}
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', height: '100%' }}>
          <div 
            ref={scrollRef}
            style={{ 
              flex: 1, 
              overflowY: 'auto', 
              display: 'flex',
              flexDirection: 'column',
              gap: '12px',
              padding: '10px',
              fontSize: '13px'
            }}
          >
            {messages.map((m) => {
              const isMine = m.sender_id === `user:${playerId}`
              const payload = m.payload as { sender_caste?: string }
              const senderCaste = payload?.sender_caste || 'UNKNOWN'
              const color = getAvatarColor(m.sender_id || 'system', senderCaste)
              return (
                <div key={m.message_id} style={{ 
                  display: 'flex', 
                  flexDirection: 'row',
                  alignItems: 'flex-start',
                  gap: '10px',
                  alignSelf: isMine ? 'flex-end' : 'flex-start',
                  maxWidth: '85%'
                }}>
                  {!isMine && (
                    <div 
                      onClick={() => m.sender_id && openDm(m.sender_id)}
                      title={`Click to open secure line. Class: ${senderCaste}`}
                      style={{ 
                        width: '32px', 
                        height: '32px', 
                        borderRadius: '4px', 
                        background: color,
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        fontSize: '14px',
                        fontWeight: 'bold',
                        color: '#000',
                        cursor: 'pointer',
                        flexShrink: 0,
                        border: `2px solid ${color === '#facc15' ? 'rgba(255,255,255,0.5)' : 'rgba(255,255,255,0.2)'}`,
                        boxShadow: color === '#facc15' ? '0 0 10px rgba(250, 204, 21, 0.4)' : 'none'
                      }}
                    >
                      {m.sender_display[0]}
                    </div>
                  )}
                  <div style={{ display: 'flex', flexDirection: 'column', alignItems: isMine ? 'flex-end' : 'flex-start' }}>
                    <div style={{ fontSize: '10px', color: '#64748b', marginBottom: '2px', fontWeight: '600', display: 'flex', alignItems: 'center', gap: '4px' }}>
                      <span style={{ color: color }}>{m.sender_display}</span>
                      {senderCaste !== 'UNKNOWN' && (
                        <span style={{ 
                          fontSize: '8px', 
                          background: 'rgba(255,255,255,0.05)', 
                          padding: '0 4px', 
                          borderRadius: '2px',
                          border: `1px solid ${color}44`,
                          color: color
                        }}>
                          {senderCaste}
                        </span>
                      )}
                      • {new Date(m.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                    </div>
                    <div style={{ 
                      padding: '8px 12px', 
                      borderRadius: isMine ? '12px 2px 12px 12px' : '2px 12px 12px 12px', 
                      background: isMine ? 'linear-gradient(135deg, #3b82f6 0%, #2563eb 100%)' : 'rgba(30, 41, 59, 0.8)',
                      color: isMine ? '#fff' : '#f1f5f9',
                      border: isMine ? 'none' : '1px solid rgba(51, 65, 85, 0.5)',
                      lineHeight: 1.4,
                      wordBreak: 'break-word',
                      boxShadow: isMine ? '0 4px 12px rgba(37, 99, 235, 0.2)' : '0 4px 12px rgba(0, 0, 0, 0.1)',
                      position: 'relative'
                    }}>
                      {m.content}
                    </div>
                  </div>
                </div>
              )
            })}
            {messages.length === 0 && (
              <div style={{ opacity: 0.3, textAlign: 'center', padding: '40px 20px', fontSize: '12px' }}>
                {activeThread === 'global' ? 'SILENCE_IN_SECTOR' : 'ENCRYPTED_CHANNEL_READY'}
              </div>
            )}
          </div>

          {/* Input Area */}
          <div style={{ 
            padding: '12px', 
            borderTop: '1px solid var(--terminal-border)',
            background: 'rgba(0,0,0,0.2)'
          }}>
            <div style={{ display: 'flex', gap: '8px' }}>
              <input 
                className="cyber-input"
                value={text}
                onChange={e => setText(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && !e.shiftKey && send()}
                placeholder={activeThread === 'global' ? "在此发送全服广播..." : "输入加密私信..."}
                style={{ 
                  flex: 1, 
                  height: '36px', 
                  background: 'rgba(15, 23, 42, 0.8)',
                  border: '1px solid rgba(59, 130, 246, 0.3)',
                  boxShadow: text.trim() ? '0 0 10px rgba(59, 130, 246, 0.2)' : 'none',
                  transition: 'all 0.2s'
                }}
              />
              <button 
                className="cyber-button" 
                onClick={send}
                disabled={loading || !text.trim()}
                style={{ 
                  padding: '0 16px', 
                  height: '36px', 
                  background: loading ? '#1e293b' : '#3b82f6', 
                  borderColor: '#3b82f6', 
                  color: '#fff',
                  fontWeight: 'bold'
                }}
              >
                {loading ? "..." : "SEND"}
              </button>
            </div>
          </div>
        </div>
      </div>
    </CyberWidget>
  )
}
