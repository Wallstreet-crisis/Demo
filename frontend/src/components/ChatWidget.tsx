import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  Api,
  WsClient,
  type ChatListMessagesResponse,
} from '../api'
import { useAppSession } from '../app/context'
import CyberWidget from './CyberWidget'

interface ChatWsEvent {
  event_type?: string;
  payload?: Record<string, unknown>;
}

export default function ChatWidget() {
  const { playerId } = useAppSession()
  const [messages, setMessages] = useState<ChatListMessagesResponse | null>(null)
  const [text, setText] = useState<string>('')
  const [loading, setLoading] = useState(false)

  const ws = useMemo(() => new WsClient({ baseUrl: import.meta.env.VITE_API_BASE_URL }), [])
  const scrollRef = useRef<HTMLDivElement>(null)

  const refresh = useCallback(async () => {
    try {
      const r = await Api.chatPublicMessages(20)
      setMessages(r)
    } catch (e) {
      console.error('Failed to fetch chat messages', e)
    }
  }, [])

  useEffect(() => {
    refresh()
    ws.connect('chat.public.global', (payload) => {
      const ev = payload as ChatWsEvent;
      if (ev?.event_type === 'CHAT_MESSAGE_SENT') {
        refresh()
      }
    })
    return () => ws.close()
  }, [refresh, ws])

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [messages])

  async function send() {
    if (!text.trim() || !playerId) return
    setLoading(true)
    try {
      await Api.chatPublicSend({
        sender_id: `user:${playerId}`,
        message_type: 'TEXT',
        content: text,
        payload: {},
      })
      setText('')
      setTimeout(refresh, 200)
    } catch (e) {
      console.error('Failed to send message', e)
    } finally {
      setLoading(false)
    }
  }

  return (
    <CyberWidget 
      title="PUBLIC_COMMS" 
      subtitle="UNENCRYPTED_GLOBAL_BROADCAST"
    >
      <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
        <div 
          ref={scrollRef}
          style={{ 
            flex: 1, 
            overflowY: 'auto', 
            marginBottom: '12px',
            display: 'flex',
            flexDirection: 'column',
            gap: '6px',
            paddingRight: '8px',
            fontSize: '13px'
          }}
        >
          {messages?.items?.map((m) => {
            const isMine = m.sender_id === `user:${playerId}`
            return (
              <div key={m.message_id} style={{ lineHeight: 1.4, padding: '4px 0', borderBottom: '1px solid rgba(51, 65, 85, 0.2)' }}>
                <span style={{ color: isMine ? '#3b82f6' : '#94a3b8', fontWeight: '700', fontSize: '11px', marginRight: '6px' }}>
                  {m.sender_display}
                </span>
                <span style={{ color: '#f1f5f9' }}>
                  {m.content}
                </span>
              </div>
            )
          })}
          {messages?.items?.length === 0 && (
            <div style={{ opacity: 0.3, textAlign: 'center', padding: '40px 20px', fontSize: '12px' }}>SILENCE_IN_SECTOR</div>
          )}
        </div>

        <div style={{ display: 'flex', gap: '8px', paddingTop: '10px', borderTop: '1px solid var(--terminal-border)' }}>
          <input 
            className="cyber-input"
            value={text}
            onChange={e => setText(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && send()}
            placeholder="BROADCAST_MSG..."
            style={{ flex: 1, height: '32px' }}
          />
          <button 
            className="cyber-button" 
            onClick={send}
            disabled={loading || !text.trim()}
            style={{ padding: '0 16px', height: '32px', background: '#3b82f6', borderColor: '#3b82f6', color: '#fff' }}
          >
            SEND
          </button>
        </div>
      </div>
    </CyberWidget>
  )
}
