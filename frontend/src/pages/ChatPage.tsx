import { useEffect, useMemo, useState } from 'react'
import { Api, ApiError, WsClient, type ChatListMessagesResponse, type ChatOpenPmResponse } from '../api'
import { useAppSession } from '../app/context'

export default function ChatPage() {
  const { playerId } = useAppSession()
  const [err, setErr] = useState<string>('')

  const [publicMessages, setPublicMessages] = useState<ChatListMessagesResponse | null>(null)
  const [publicText, setPublicText] = useState<string>('')

  const [pmTarget, setPmTarget] = useState<string>('user:bob')
  const [pmThread, setPmThread] = useState<ChatOpenPmResponse | null>(null)
  const [pmMessages, setPmMessages] = useState<ChatListMessagesResponse | null>(null)
  const [pmText, setPmText] = useState<string>('')

  const ws = useMemo(() => new WsClient({ baseUrl: import.meta.env.VITE_API_BASE_URL }), [])
  const [wsLines, setWsLines] = useState<string[]>([])

  async function refreshPublic(): Promise<void> {
    setErr('')
    try {
      const r = await Api.chatPublicMessages(50)
      setPublicMessages(r)
    } catch (e) {
      if (e instanceof ApiError) setErr(`${e.status}: ${e.message}`)
      else setErr(e instanceof Error ? e.message : String(e))
    }
  }

  async function sendPublic(): Promise<void> {
    setErr('')
    try {
      await Api.chatPublicSend({
        sender_id: `user:${playerId}`,
        message_type: 'TEXT',
        content: publicText,
        payload: {},
      })
      setPublicText('')
      await refreshPublic()
    } catch (e) {
      if (e instanceof ApiError) setErr(`${e.status}: ${e.message}`)
      else setErr(e instanceof Error ? e.message : String(e))
    }
  }

  async function openPm(): Promise<void> {
    setErr('')
    try {
      const r = await Api.chatOpenPm({ requester_id: `user:${playerId}`, target_id: pmTarget })
      setPmThread(r)
      const msgs = await Api.chatPmMessages(r.thread_id, 50)
      setPmMessages(msgs)

      ws.connect(`chat.pm.${r.thread_id}`, (payload) => {
        const line = typeof payload === 'string' ? payload : JSON.stringify(payload)
        setWsLines((prev) => [line, ...prev].slice(0, 50))
      })
    } catch (e) {
      if (e instanceof ApiError) setErr(`${e.status}: ${e.message}`)
      else setErr(e instanceof Error ? e.message : String(e))
    }
  }

  async function sendPm(): Promise<void> {
    if (!pmThread) return
    setErr('')
    try {
      await Api.chatPmSend({
        thread_id: pmThread.thread_id,
        sender_id: `user:${playerId}`,
        message_type: 'TEXT',
        content: pmText,
        payload: {},
      })
      setPmText('')
      const msgs = await Api.chatPmMessages(pmThread.thread_id, 50)
      setPmMessages(msgs)
    } catch (e) {
      if (e instanceof ApiError) setErr(`${e.status}: ${e.message}`)
      else setErr(e instanceof Error ? e.message : String(e))
    }
  }

  useEffect(() => {
    refreshPublic()
    return () => ws.close()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [playerId])

  return (
    <div style={{ display: 'grid', gap: 12 }}>
      <div className="card" style={{ textAlign: 'left' }}>
        <h3 style={{ marginTop: 0 }}>Public Chat</h3>
        {err ? <div style={{ color: 'crimson' }}>{err}</div> : null}
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
          <input
            style={{ minWidth: 320 }}
            value={publicText}
            onChange={(e) => setPublicText(e.target.value)}
            placeholder="message"
          />
          <button onClick={sendPublic}>Send</button>
          <button onClick={refreshPublic}>Refresh</button>
        </div>
        <pre style={{ whiteSpace: 'pre-wrap' }}>{publicMessages ? JSON.stringify(publicMessages, null, 2) : 'N/A'}</pre>
      </div>

      <div className="card" style={{ textAlign: 'left' }}>
        <h3 style={{ marginTop: 0 }}>PM</h3>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
          <input value={pmTarget} onChange={(e) => setPmTarget(e.target.value)} style={{ minWidth: 240 }} />
          <button onClick={openPm}>Open</button>
        </div>

        {pmThread ? (
          <div style={{ marginTop: 10 }}>
            <div>
              thread: <code>{pmThread.thread_id}</code>
            </div>
            <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap', marginTop: 8 }}>
              <input
                style={{ minWidth: 320 }}
                value={pmText}
                onChange={(e) => setPmText(e.target.value)}
                placeholder="pm message"
              />
              <button onClick={sendPm}>Send</button>
            </div>
            <pre style={{ whiteSpace: 'pre-wrap' }}>{pmMessages ? JSON.stringify(pmMessages, null, 2) : 'N/A'}</pre>
          </div>
        ) : (
          <div style={{ marginTop: 10 }}>Open a thread first.</div>
        )}
      </div>

      <div className="card" style={{ textAlign: 'left' }}>
        <h3 style={{ marginTop: 0 }}>WS: chat.pm.&lt;thread_id&gt; (latest 50)</h3>
        <pre style={{ whiteSpace: 'pre-wrap', maxHeight: 220, overflow: 'auto' }}>{wsLines.join('\n')}</pre>
      </div>
    </div>
  )
}
