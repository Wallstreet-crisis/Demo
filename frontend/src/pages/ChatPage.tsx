import { useCallback, useEffect, useMemo, useRef, useState, type SetStateAction, type Dispatch } from 'react'
import {
  Api,
  ApiError,
  WsClient,
  type ChatListMessagesResponse,
  type ChatListThreadsResponse,
  type ChatOpenPmResponse,
  type WealthPublicResponse,
} from '../api'
import { useAppSession } from '../app/context'
import { useNotification } from '../app/NotificationContext'

interface ChatWsEvent {
  event_type?: string;
  payload?: Record<string, unknown>;
}

function formatTime(s: string): string {
  if (!s) return ''
  const d = new Date(s)
  if (Number.isNaN(d.getTime())) return s
  return d.toLocaleString()
}

export default function ChatPage() {
  const { playerId, roomId } = useAppSession()
  const { notify } = useNotification()
  const [err, setErr] = useState<string>('')
  const [loadingThreads, setLoadingThreads] = useState(true)
  const [loadingPublic, setLoadingPublic] = useState(true)

  const [publicMessages, setPublicMessages] = useState<ChatListMessagesResponse | null>(null)
  const [publicText, setPublicText] = useState<string>('')

  const [threads, setThreads] = useState<ChatListThreadsResponse | null>(null)

  const [pmTarget, setPmTarget] = useState<string>('user:bob')
  const [pmThread, setPmThread] = useState<ChatOpenPmResponse | null>(null)
  const [pmMessages, setPmMessages] = useState<ChatListMessagesResponse | null>(null)
  const [pmText, setPmText] = useState<string>('')
  const [peerWealth, setPeerWealth] = useState<WealthPublicResponse | null>(null)

  const ws = useMemo(() => new WsClient({ baseUrl: import.meta.env.VITE_API_BASE_URL }), [])
  const [wsLines, setWsLines] = useState<string[]>([])
  const publicSeenRef = useRef<Set<string>>(new Set())
  const pmSeenRef = useRef<Set<string>>(new Set())

  const refreshPublic = useCallback(async (): Promise<void> => {
    setErr('')
    setLoadingPublic(true)
    try {
      const r = await Api.chatPublicMessages(50)
      publicSeenRef.current = new Set((r.items || []).map(m => m.message_id))
      setPublicMessages(r)
    } catch (e) {
      if (e instanceof ApiError) setErr(`${e.status}: ${e.message}`)
      else setErr(e instanceof Error ? e.message : String(e))
    } finally {
      setLoadingPublic(false)
    }
  }, [])

  const refreshThreads = useCallback(async (): Promise<void> => {
    setErr('')
    setLoadingThreads(true)
    try {
      const r = await Api.chatThreads(`user:${playerId}`, 200)
      setThreads(r)
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : (e instanceof Error ? e.message : String(e))
      setErr(msg)
      notify('error', `获取对话列表失败: ${msg}`)
    } finally {
      setLoadingThreads(false)
    }
  }, [playerId, notify])

  const refreshPmMessages = useCallback(async (threadId: string): Promise<void> => {
    try {
      const msgs = await Api.chatPmMessages(threadId, 50)
      pmSeenRef.current = new Set((msgs.items || []).map(m => m.message_id))
      setPmMessages(msgs)
    } catch (e) {
      console.error('Failed to refresh PM messages', e)
    }
  }, [])

  const appendWsMsg = useCallback((ev: ChatWsEvent, seenRef: React.MutableRefObject<Set<string>>, setter: Dispatch<SetStateAction<ChatListMessagesResponse | null>>) => {
    if (ev?.event_type !== 'chat.message.sent' || !ev.payload) return
    const p = ev.payload
    const msgId = String(p.message_id || '')
    if (!msgId || seenRef.current.has(msgId)) return
    seenRef.current.add(msgId)
    const newMsg = {
      message_id: msgId,
      thread_id: String(p.thread_id || ''),
      sender_id: p.sender_id != null ? String(p.sender_id) : null,
      sender_display: String(p.sender_display || p.sender_id || ''),
      message_type: String(p.message_type || 'TEXT'),
      content: String(p.content || ''),
      payload: (p.payload && typeof p.payload === 'object' ? p.payload : {}) as Record<string, unknown>,
      created_at: String(p.sent_at || new Date().toISOString()),
    }
    setter(prev => {
      const items = prev?.items ? [...prev.items, newMsg] : [newMsg]
      return { items: items.slice(-100) }
    })
  }, [])

  async function openThread(threadId: string, targetUserId?: string): Promise<void> {
    setErr('')
    try {
      const actualTarget = targetUserId?.startsWith('user:') ? targetUserId : (targetUserId ? `user:${targetUserId}` : undefined)
      if (actualTarget) {
        const r = await Api.chatOpenPm({ requester_id: `user:${playerId}`, target_id: actualTarget })
        setPmThread(r)
        await refreshPmMessages(r.thread_id)
        
        // Fetch peer wealth
        try {
          const w = await Api.wealthPublicGet(actualTarget)
          setPeerWealth(w)
        } catch (e) { console.error('Peer wealth fetch failed', e) }

        ws.connect(`chat.pm.${r.thread_id}`, (payload) => {
          const ev = payload as ChatWsEvent;
          appendWsMsg(ev, pmSeenRef, setPmMessages)
          const line = typeof payload === 'string' ? payload : JSON.stringify(payload)
          setWsLines((prev) => [line, ...prev].slice(0, 50))
        })
        notify('success', `已进入与 ${actualTarget} 的私聊`)
        return
      }

      setPmThread({ thread_id: threadId, paid_intro_fee: false, intro_fee_cash: 0 })
      ws.connect(`chat.pm.${threadId}`, (payload) => {
        const ev = payload as ChatWsEvent;
        appendWsMsg(ev, pmSeenRef, setPmMessages)
        const line = typeof payload === 'string' ? payload : JSON.stringify(payload)
        setWsLines((prev) => [line, ...prev].slice(0, 50))
      })
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : (e instanceof Error ? e.message : String(e))
      setErr(msg)
      notify('error', msg)
    }
  }

  async function sendPublic(): Promise<void> {
    if (!publicText.trim()) return
    setErr('')
    try {
      await Api.chatPublicSend({
        sender_id: `user:${playerId}`,
        message_type: 'TEXT',
        content: publicText,
        payload: {},
      })
      setPublicText('')
      notify('success', '消息已发送到广场')
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : (e instanceof Error ? e.message : String(e))
      setErr(msg)
      notify('error', msg)
    }
  }

  async function openPm(): Promise<void> {
    if (!pmTarget.trim()) return
    setErr('')
    try {
      const target = pmTarget.startsWith('user:') ? pmTarget : `user:${pmTarget}`
      const r = await Api.chatOpenPm({ requester_id: `user:${playerId}`, target_id: target })
      setPmThread(r)
      await refreshPmMessages(r.thread_id)
      
      try {
        const w = await Api.wealthPublicGet(target)
        setPeerWealth(w)
      } catch (e) { console.error('Peer wealth fetch failed', e) }

      ws.connect(`chat.pm.${r.thread_id}`, (payload) => {
        const ev = payload as ChatWsEvent;
        appendWsMsg(ev, pmSeenRef, setPmMessages)
        const line = typeof payload === 'string' ? payload : JSON.stringify(payload)
        setWsLines((prev) => [line, ...prev].slice(0, 50))
      })
      notify('success', `已开启私聊: ${target}`)
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : (e instanceof Error ? e.message : String(e))
      setErr(msg)
      notify('error', msg)
    }
  }

  async function sendPm(): Promise<void> {
    if (!pmThread || !pmText.trim()) return
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
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : (e instanceof Error ? e.message : String(e))
      setErr(msg)
      notify('error', msg)
    }
  }

  useEffect(() => {
    refreshPublic()
    refreshThreads()

    ws.connect('chat.public.global', (payload) => {
      const ev = payload as ChatWsEvent;
      appendWsMsg(ev, publicSeenRef, setPublicMessages)
    })

    return () => {
      ws.close()
    }
  }, [playerId, refreshPublic, refreshThreads, ws, appendWsMsg, roomId])

  return (
    <div style={{ display: 'grid', gap: 12 }}>
      <div className="card" style={{ textAlign: 'left' }}>
        <h3 style={{ marginTop: 0 }}>Threads</h3>
        {err ? <div style={{ color: 'crimson' }}>{err}</div> : null}
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
          <button onClick={refreshThreads} disabled={loadingThreads}>{loadingThreads ? '刷新中...' : 'Refresh'}</button>
        </div>

        {loadingThreads && (!threads || !threads.items) ? (
          <div style={{ padding: 20, color: '#999' }}>加载线程中...</div>
        ) : threads?.items && threads.items.length > 0 ? (
          <div style={{ display: 'grid', gap: 8, marginTop: 10 }}>
            {threads.items.map((t) => {
              const other = t.participant_a === `user:${playerId}` ? t.participant_b : t.participant_a
              return (
                <div
                  key={t.thread_id}
                  style={{
                    display: 'flex',
                    gap: 10,
                    alignItems: 'center',
                    flexWrap: 'wrap',
                    border: '1px solid #eee',
                    borderRadius: 10,
                    padding: 10,
                    background: '#fff',
                  }}
                >
                  <div style={{ display: 'grid' }}>
                    <div style={{ fontWeight: 700 }}>{other}</div>
                    <div style={{ color: '#888', fontSize: 12 }}>
                      <code>{t.thread_id}</code>
                    </div>
                  </div>

                  <div style={{ marginLeft: 'auto', display: 'flex', gap: 8, alignItems: 'center' }}>
                    <span style={{ color: '#666', fontSize: 12 }}>{t.status}</span>
                    <button onClick={() => openThread(t.thread_id, other)}>Open</button>
                  </div>
                </div>
              )
            })}
          </div>
        ) : (
          <div style={{ marginTop: 10, color: '#666' }}>No threads.</div>
        )}

        <details style={{ marginTop: 12 }}>
          <summary>Raw JSON</summary>
          <pre style={{ whiteSpace: 'pre-wrap' }}>{threads ? JSON.stringify(threads, null, 2) : 'N/A'}</pre>
        </details>
      </div>

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
          <button onClick={refreshPublic} disabled={loadingPublic}>{loadingPublic ? '刷新中...' : 'Refresh'}</button>
        </div>

        {loadingPublic && (!publicMessages || !publicMessages.items) ? (
          <div style={{ padding: 20, color: '#999' }}>加载消息中...</div>
        ) : publicMessages?.items && publicMessages.items.length > 0 ? (
          <div style={{ display: 'grid', gap: 8, marginTop: 10 }}>
            {publicMessages.items.map((m) => {
              const mine = (m.sender_id ?? '') === `user:${playerId}`
              return (
                <div
                  key={m.message_id}
                  style={{
                    display: 'flex',
                    justifyContent: mine ? 'flex-end' : 'flex-start',
                  }}
                >
                  <div
                    style={{
                      maxWidth: 720,
                      border: '1px solid #eee',
                      borderRadius: 12,
                      padding: 10,
                      background: mine ? '#e6f4ff' : '#fff',
                    }}
                  >
                    <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'baseline' }}>
                      <span style={{ fontWeight: 700 }}>{m.sender_display}</span>
                      <span style={{ color: '#888', fontSize: 12 }}>{formatTime(m.created_at)}</span>
                    </div>
                    <div style={{ marginTop: 6, whiteSpace: 'pre-wrap' }}>{m.content}</div>
                  </div>
                </div>
              )
            })}
          </div>
        ) : (
          <div style={{ marginTop: 10, color: '#666' }}>暂无消息。</div>
        )}

        <details style={{ marginTop: 12 }}>
          <summary>Raw JSON</summary>
          <pre style={{ whiteSpace: 'pre-wrap' }}>{publicMessages ? JSON.stringify(publicMessages, null, 2) : 'N/A'}</pre>
        </details>
      </div>

      <div className="card" style={{ textAlign: 'left' }}>
        <h3 style={{ marginTop: 0 }}>私聊 (PM)</h3>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
          <input 
            value={pmTarget} 
            onChange={(e) => setPmTarget(e.target.value)} 
            style={{ minWidth: 240, padding: '8px', borderRadius: 4, border: '1px solid #ddd' }} 
            placeholder="输入玩家 ID (如 user:bob)"
          />
          <button onClick={openPm}>开启/进入对话</button>
        </div>

        {pmThread ? (
          <div style={{ marginTop: 15, border: '1px solid #eee', borderRadius: 12, padding: 15, background: '#fafafa' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12, paddingBottom: 10, borderBottom: '1px solid #eee' }}>
              <div>
                对话 ID: <code>{pmThread.thread_id}</code>
                {pmThread.paid_intro_fee && <span style={{ marginLeft: 8, fontSize: 12, color: '#faad14' }}>✨ 已付门槛费: {pmThread.intro_fee_cash}</span>}
              </div>
              {peerWealth && (
                <div style={{ fontSize: 13, color: '#666' }}>
                  对方公开资产: <strong style={{ color: '#1890ff' }}>{peerWealth.public_total_value?.toLocaleString() ?? '--'}</strong>
                </div>
              )}
            </div>
            
            <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap', marginBottom: 15 }}>
              <input
                style={{ flex: 1, minWidth: 300, padding: '8px', borderRadius: 4, border: '1px solid #ddd' }}
                value={pmText}
                onChange={(e) => setPmText(e.target.value)}
                placeholder="输入私聊消息..."
                onKeyDown={(e) => e.key === 'Enter' && sendPm()}
              />
              <button onClick={sendPm} style={{ background: '#52c41a', color: '#fff', border: 'none' }}>发送</button>
            </div>

            {pmMessages?.items?.length ? (
              <div style={{ display: 'grid', gap: 8, marginTop: 10 }}>
                {pmMessages.items.map((m) => {
                  const mine = (m.sender_id ?? '') === `user:${playerId}`
                  return (
                    <div
                      key={m.message_id}
                      style={{
                        display: 'flex',
                        justifyContent: mine ? 'flex-end' : 'flex-start',
                      }}
                    >
                      <div
                        style={{
                          maxWidth: 720,
                          border: '1px solid #eee',
                          borderRadius: 12,
                          padding: 10,
                          background: mine ? '#f6ffed' : '#fff',
                        }}
                      >
                        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'baseline' }}>
                          <span style={{ fontWeight: 700 }}>{m.sender_display}</span>
                          <span style={{ color: '#888', fontSize: 12 }}>{formatTime(m.created_at)}</span>
                        </div>
                        <div style={{ marginTop: 6, whiteSpace: 'pre-wrap' }}>{m.content}</div>
                      </div>
                    </div>
                  )
                })}
              </div>
            ) : (
              <div style={{ marginTop: 10, color: '#666' }}>暂无消息。</div>
            )}

            <details style={{ marginTop: 12 }}>
              <summary>Raw JSON</summary>
              <pre style={{ whiteSpace: 'pre-wrap' }}>{pmMessages ? JSON.stringify(pmMessages, null, 2) : 'N/A'}</pre>
            </details>
          </div>
        ) : (
          <div style={{ marginTop: 10 }}>Open a thread first.</div>
        )}
      </div>

      <div className="card" style={{ textAlign: 'left' }}>
        <h3 style={{ marginTop: 0 }}>WS: chat.pm.&lt;thread_id&gt; (latest 50)</h3>
        <pre style={{ whiteSpace: 'pre-wrap', maxHeight: 220, overflow: 'auto' }}>{wsLines.join('\n')}</pre>

        <details style={{ marginTop: 12 }}>
          <summary>Raw JSON</summary>
          <pre style={{ whiteSpace: 'pre-wrap' }}>{JSON.stringify(wsLines, null, 2)}</pre>
        </details>
      </div>
    </div>
  )
}
