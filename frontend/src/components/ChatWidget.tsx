import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Api,
  WsClient,
  type ChatListMessagesResponse,
  type ChatMessageResponse,
  type ChatThreadResponse,
  type ContractBriefResponse,
} from '../api'
import { useAppSession } from '../app/context'
import CyberWidget from './CyberWidget'

interface ChatWsEvent {
  event_type?: string;
  payload?: Record<string, unknown>;
}

export default function ChatWidget({ isFocused }: { isFocused?: boolean }) {
  const { playerId } = useAppSession()
  const nav = useNavigate()
  const [activeThread, setActiveThread] = useState<'global' | ChatThreadResponse>('global')
  const [messages, setMessages] = useState<ChatMessageResponse[]>([])
  const [threads, setThreads] = useState<ChatThreadResponse[]>([])
  const [text, setText] = useState<string>('')
  const [loading, setLoading] = useState(false)

  // Mentions state
  const [showMentionList, setShowMentionList] = useState(false)
  const [mentionType, setMentionType] = useState<'PLAYER' | 'CONTRACT' | null>(null)
  const [mentionQuery, setMentionQuery] = useState('')
  const [mentionIndex, setMentionIndex] = useState(0)
  const [players, setPlayers] = useState<string[]>([])
  const [contracts, setContracts] = useState<ContractBriefResponse[]>([])

  const ws = useMemo(() => new WsClient({ baseUrl: import.meta.env.VITE_API_BASE_URL }), [])
  const scrollRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)
  const sendingRef = useRef(false)

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

  const fetchMentionsData = useCallback(async () => {
    try {
      const [pRes, cRes] = await Promise.all([
        Api.listPlayers(50),
        Api.listContracts(playerId, 50)
      ])
      setPlayers(pRes.items)
      setContracts(cRes.items)
    } catch (e) {
      console.error('Mention data fetch failed', e)
    }
  }, [playerId])

  useEffect(() => {
    refreshMessages()
    if (playerId) {
      refreshThreads()
      fetchMentionsData()
    }

    const channel = activeThread === 'global' ? 'chat.public.global' : `chat.pm.${activeThread.thread_id}`
    ws.connect(channel, (payload) => {
      const ev = payload as ChatWsEvent;
      if (ev?.event_type === 'CHAT_MESSAGE_SENT') {
        refreshMessages()
      }
    })
    return () => ws.close()
  }, [activeThread, refreshMessages, refreshThreads, fetchMentionsData, playerId, ws])

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [messages])

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const val = e.target.value
    const cursor = e.target.selectionStart || 0
    setText(val)

    // Detect @ for players
    const lastAt = val.lastIndexOf('@', cursor - 1)
    if (lastAt !== -1 && (lastAt === 0 || val[lastAt - 1] === ' ')) {
      const query = val.slice(lastAt + 1, cursor)
      if (!query.includes(' ')) {
        setMentionType('PLAYER')
        setMentionQuery(query)
        setMentionIndex(0)
        setShowMentionList(true)
        return
      }
    }

    // Detect # for contracts
    const lastHash = val.lastIndexOf('#', cursor - 1)
    if (lastHash !== -1 && (lastHash === 0 || val[lastHash - 1] === ' ')) {
      const query = val.slice(lastHash + 1, cursor)
      if (!query.includes(' ')) {
        setMentionType('CONTRACT')
        setMentionQuery(query)
        setMentionIndex(0)
        setShowMentionList(true)
        return
      }
    }

    setShowMentionList(false)
  }

  const filteredItems = useMemo(() => {
    if (mentionType === 'PLAYER') {
      return players.filter(p => p.toLowerCase().includes(mentionQuery.toLowerCase()));
    } else if (mentionType === 'CONTRACT') {
      return contracts.filter(c => c.title.toLowerCase().includes(mentionQuery.toLowerCase()) || c.contract_id.includes(mentionQuery));
    }
    return [];
  }, [mentionType, players, contracts, mentionQuery]);

  const selectMention = (item: string | ContractBriefResponse) => {
    const cursor = inputRef.current?.selectionStart || 0
    let replacement = ''
    let startIdx = 0

    if (mentionType === 'PLAYER') {
      replacement = `@${item} `
      startIdx = text.lastIndexOf('@', cursor - 1)
    } else {
      const c = item as ContractBriefResponse
      replacement = `#${c.contract_id} `
      startIdx = text.lastIndexOf('#', cursor - 1)
    }

    const newVal = text.slice(0, startIdx) + replacement + text.slice(cursor)
    setText(newVal)
    setShowMentionList(false)
    inputRef.current?.focus()
  }

  async function send() {
    if (!text.trim() || !playerId) return
    if (sendingRef.current) return
    sendingRef.current = true
    setLoading(true)
    try {
      const payload: Record<string, unknown> = {}
      // Basic detection of contract ID in message to add to payload
      const contractMatch = text.match(/#([a-f0-9-]{36})/i)
      if (contractMatch) {
        payload.referenced_contract_id = contractMatch[1]
      }

      if (activeThread === 'global') {
        await Api.chatPublicSend({
          sender_id: `user:${playerId}`,
          message_type: 'TEXT',
          content: text,
          payload
        })
      } else {
        await Api.chatPmSend({
          thread_id: activeThread.thread_id,
          sender_id: `user:${playerId}`,
          message_type: 'TEXT',
          content: text,
          payload
        })
      }
      setText('')
      setTimeout(refreshMessages, 100)
    } catch (e) {
      console.error('Failed to send message', e)
    } finally {
      setLoading(false)
      sendingRef.current = false
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
    if (caste === 'ELITE' || caste === 'BOT_INSTITUTION') return '#facc15';
    if (caste === 'MIDDLE') return '#3b82f6';
    if (caste === 'WORKING' || caste === 'BOT_RETAIL') return '#10b981';
    if (caste === 'SYSTEM') return '#ef4444';
    
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
        {/* Thread Sidebar - Hidden if not focused and sidebar is wide */}
        {(!isFocused) ? null : (
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
                    boxShadow: isActive ? `0 0 100px ${color}` : 'none'
                  }}
                >
                  {t.participant_b[0].toUpperCase()}
                </div>
              );
            })}
          </div>
        )}

        {/* Chat Area */}
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', height: '100%', minWidth: 0 }}>
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
              const payload = m.payload as { sender_caste?: string, referenced_contract_id?: string }
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
                        boxShadow: color === '#facc15' ? '0 0 100px rgba(250, 204, 21, 0.4)' : 'none'
                      }}
                    >
                      {m.sender_display[0]}
                    </div>
                  )}
                  <div style={{ display: 'flex', flexDirection: 'column', alignItems: isMine ? 'flex-end' : 'flex-start', minWidth: 0 }}>
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
                      {payload?.referenced_contract_id && (
                        <div 
                          style={{ 
                            marginTop: '10px', 
                            padding: '10px', 
                            background: 'rgba(15, 23, 42, 0.6)', 
                            border: '1px solid rgba(59, 130, 246, 0.4)',
                            borderLeft: '4px solid var(--terminal-info)',
                            borderRadius: '4px', 
                            fontSize: '12px',
                            color: '#fff',
                            cursor: 'pointer',
                            display: 'flex',
                            alignItems: 'center',
                            gap: '10px',
                            transition: 'all 0.2s',
                            boxShadow: '0 2px 8px rgba(0,0,0,0.2)'
                          }} 
                          onMouseEnter={e => e.currentTarget.style.borderColor = 'var(--terminal-info)'}
                          onMouseLeave={e => e.currentTarget.style.borderColor = 'rgba(59, 130, 246, 0.4)'}
                          onClick={() => nav(`/contracts/${payload.referenced_contract_id}`)}
                        >
                          <div style={{ 
                            width: '24px', height: '24px', 
                            background: 'rgba(59, 130, 246, 0.2)', 
                            display: 'flex', alignItems: 'center', justifyContent: 'center',
                            borderRadius: '4px', fontSize: '14px'
                          }}>📜</div>
                          <div style={{ flex: 1, minWidth: 0 }}>
                            <div style={{ fontSize: '9px', color: 'var(--terminal-info)', fontWeight: 'bold', letterSpacing: '1px' }}>CERTIFIED_CONTRACT</div>
                            <div style={{ fontFamily: 'monospace', opacity: 0.9, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                              ID: {payload.referenced_contract_id.substring(0, 12)}...
                            </div>
                          </div>
                          <div style={{ fontSize: '10px', opacity: 0.5, flexShrink: 0 }}>DETAILS »</div>
                        </div>
                      )}
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
            background: 'rgba(0,0,0,0.2)',
            position: 'relative'
          }}>
            {/* Mention List UI */}
            {showMentionList && (
              <div style={{
                position: 'absolute',
                bottom: '100%',
                left: '12px',
                right: '12px',
                background: 'rgba(10, 15, 25, 0.98)',
                border: '1px solid var(--terminal-info)',
                boxShadow: '0 -5px 25px rgba(59, 130, 246, 0.4)',
                zIndex: 2000,
                maxHeight: '200px',
                overflowY: 'auto',
                marginBottom: '8px',
                borderRadius: '4px',
                backdropFilter: 'blur(8px)'
              }} className="custom-scrollbar">
                <div style={{ 
                  padding: '6px 12px', 
                  fontSize: '9px', 
                  background: 'rgba(59, 130, 246, 0.2)', 
                  color: 'var(--terminal-info)', 
                  fontWeight: 'bold',
                  letterSpacing: '1px',
                  borderBottom: '1px solid rgba(59, 130, 246, 0.3)'
                }}>
                  SELECT_{mentionType === 'PLAYER' ? 'TARGET_IDENTITY' : 'CONTRACT_REFERENCE'}
                </div>
                {mentionType === 'PLAYER' ? (
                  (filteredItems as string[]).map((p, idx) => {
                    const isSelected = mentionIndex === idx;
                    return (
                      <div 
                        key={p} 
                        onClick={() => selectMention(p)}
                        style={{ 
                          padding: '10px 15px', 
                          cursor: 'pointer', 
                          borderBottom: '1px solid rgba(59, 130, 246, 0.1)',
                          fontSize: '12px',
                          display: 'flex',
                          alignItems: 'center',
                          gap: '10px',
                          background: isSelected ? 'rgba(59, 130, 246, 0.2)' : 'transparent',
                          color: isSelected ? '#fff' : '#cbd5e1',
                          position: 'relative',
                          transition: 'all 0.1s'
                        }}
                      >
                        {isSelected && (
                          <div style={{ 
                            position: 'absolute', left: 0, top: 0, bottom: 0, width: '3px', 
                            background: 'var(--terminal-info)',
                            boxShadow: '0 0 10px var(--terminal-info)'
                          }} />
                        )}
                        <div style={{ 
                          width: '8px', height: '8px', borderRadius: '50%', 
                          background: isSelected ? 'var(--terminal-info)' : 'rgba(59, 130, 246, 0.3)',
                          boxShadow: isSelected ? '0 0 5px var(--terminal-info)' : 'none'
                        }} />
                        <span style={{ fontFamily: 'monospace', fontWeight: isSelected ? 'bold' : 'normal' }}>{p}</span>
                        {isSelected && <span style={{ marginLeft: 'auto', fontSize: '9px', opacity: 0.5 }}>[ENTER_TO_SELECT]</span>}
                      </div>
                    );
                  })
                ) : (
                  (filteredItems as ContractBriefResponse[]).map((c, idx) => {
                    const isSelected = mentionIndex === idx;
                    const partiesText = (c.parties && c.parties.length > 0) ? c.parties.join(',') : ''
                    const total = (c.required_signers && c.required_signers.length > 0) ? c.required_signers.length : 0
                    const signed = (c.signatures && c.signatures.length > 0) ? c.signatures.length : 0
                    const signText = total > 0 ? `${signed}/${total}` : ''
                    const timeText = c.created_at ? String(c.created_at).slice(11, 16) : ''
                    const parts: string[] = []
                    if (partiesText) parts.push(partiesText)
                    if (signText) parts.push(`signed:${signText}`)
                    if (timeText) parts.push(timeText)
                    const summary = parts.length > 0 ? ` | ${parts.join(' | ')}` : ''
                    return (
                      <div 
                        key={c.contract_id} 
                        onClick={() => selectMention(c)}
                        style={{ 
                          padding: '10px 15px', 
                          cursor: 'pointer', 
                          borderBottom: '1px solid rgba(59, 130, 246, 0.1)',
                          background: isSelected ? 'rgba(59, 130, 246, 0.2)' : 'transparent',
                          color: isSelected ? '#fff' : '#cbd5e1',
                          position: 'relative',
                          transition: 'all 0.1s'
                        }}
                      >
                        {isSelected && (
                          <div style={{ 
                            position: 'absolute', left: 0, top: 0, bottom: 0, width: '3px', 
                            background: 'var(--terminal-warn)',
                            boxShadow: '0 0 10px var(--terminal-warn)'
                          }} />
                        )}
                        <div style={{ flex: 1, minWidth: 0 }}>
                          <div style={{ fontWeight: 'bold', fontSize: '13px', display: 'flex', alignItems: 'center', gap: '6px' }}>
                            <span style={{ color: isSelected ? 'var(--terminal-warn)' : '#64748b' }}>#</span>
                            <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{c.title}{summary}</span>
                          </div>
                          <div style={{ fontSize: '9px', opacity: 0.5, marginTop: '2px', fontFamily: 'monospace', display: 'flex', justifyContent: 'space-between' }}>
                            <span>ID: {c.contract_id.slice(0, 12)}...</span>
                            <span style={{ color: c.status === 'ACTIVE' ? 'var(--terminal-success)' : 'inherit' }}>{c.status}</span>
                          </div>
                        </div>
                      </div>
                    );
                  })
                )}
                {filteredItems.length === 0 && (
                  <div style={{ padding: '20px', textAlign: 'center', opacity: 0.5, fontSize: '11px' }}>
                    NO_MATCHES_FOUND
                  </div>
                )}
              </div>
            )}

            <div style={{ display: 'flex', gap: '8px' }}>
              <input 
                ref={inputRef}
                className="cyber-input"
                value={text}
                onChange={handleInputChange}
                onKeyDown={e => {
                  if (showMentionList && filteredItems.length > 0) {
                    if (e.key === 'ArrowDown') {
                      e.preventDefault();
                      setMentionIndex(prev => (prev + 1) % filteredItems.length);
                    } else if (e.key === 'ArrowUp') {
                      e.preventDefault();
                      setMentionIndex(prev => (prev - 1 + filteredItems.length) % filteredItems.length);
                    } else if (e.key === 'Enter' || e.key === 'Tab') {
                      e.preventDefault();
                      selectMention(filteredItems[mentionIndex]);
                    } else if (e.key === 'Escape') {
                      setShowMentionList(false);
                    }
                    return;
                  }

                  if (e.key === 'Enter' && !e.shiftKey) {
                    send()
                  }
                }}
                placeholder={activeThread === 'global' ? "在此发送全服广播 (@玩家, #契约)..." : "输入加密私信..."}
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
