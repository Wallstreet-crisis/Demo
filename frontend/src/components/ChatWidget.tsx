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
            marginBottom: '10px',
            display: 'flex',
            flexDirection: 'column',
            gap: '8px',
            paddingRight: '5px'
          }}
        >
          {messages?.items?.map((m) => {
            const isMine = m.sender_id === `user:${playerId}`
            return (
              <div key={m.message_id} style={{ fontSize: '11px', lineHeight: 1.4 }}>
                <span style={{ color: isMine ? '#fff' : 'var(--terminal-text)', fontWeight: 'bold' }}>
                  {m.sender_display}:
                </span>{' '}
                <span style={{ color: isMine ? 'rgba(255,255,255,0.8)' : 'inherit' }}>
                  {m.content}
                </span>
              </div>
            )
          })}
          {messages?.items?.length === 0 && (
            <div style={{ opacity: 0.3, textAlign: 'center', padding: '20px' }}>SILENCE_IN_SECTOR</div>
          )}
        </div>

        <div style={{ display: 'flex', gap: '5px' }}>
          <input 
            className="cyber-input"
            value={text}
            onChange={e => setText(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && send()}
            placeholder="BROADCAST_MSG..."
            style={{ flex: 1, fontSize: '11px' }}
          />
          <button 
            className="cyber-button" 
            onClick={send}
            disabled={loading || !text.trim()}
            style={{ fontSize: '10px', padding: '2px 8px' }}
          >
            TX
          </button>
        </div>
      </div>
    </CyberWidget>
  )
}
