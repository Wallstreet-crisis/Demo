import { useEffect, useMemo, useRef, useState } from 'react'
import { Api, type NewsInboxResponse, type NewsInboxResponseItem } from '../api'
import { useAppSession } from '../app/context'
import { WsClient } from '../api'
import CyberWidget from './CyberWidget'

function getEventType(payload: unknown): string | null {
  if (!payload || typeof payload !== 'object') return null
  const v = (payload as Record<string, unknown>).event_type
  return typeof v === 'string' ? v : null
}

function formatTime(s: string): string {
  if (!s) return ''
  const d = new Date(s)
  if (Number.isNaN(d.getTime())) return s
  return d.toLocaleTimeString()
}

export default function NewsWidget() {
  const { playerId } = useAppSession()
  const [loading, setLoading] = useState(true)
  const [inbox, setInbox] = useState<NewsInboxResponse | null>(null)
  const [selectedItem, setSelectedItem] = useState<NewsInboxResponseItem | null>(null)

  const ws = useMemo(() => new WsClient({ baseUrl: import.meta.env.VITE_API_BASE_URL }), [])
  const refreshTimerRef = useRef<number | null>(null)

  const refreshInbox = async () => {
    if (!playerId) return
    setLoading(true)
    try {
      const r = await Api.newsInbox(`user:${playerId}`, 20)
      setInbox(r)
    } catch (e) {
      console.error('Failed to refresh inbox', e)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    refreshInbox()
    
    ws.connect('events', (payload) => {
      const t = getEventType(payload)
      if (typeof t === 'string' && t.startsWith('NEWS_')) {
        if (refreshTimerRef.current === null) {
          refreshTimerRef.current = window.setTimeout(() => {
            refreshTimerRef.current = null
            refreshInbox()
          }, 1000)
        }
      }
    })

    return () => {
      ws.close()
      if (refreshTimerRef.current !== null) window.clearTimeout(refreshTimerRef.current)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [playerId])

  return (
    <CyberWidget 
      title="INTELLIGENCE_INBOX" 
      subtitle="ENCRYPTED_FEED_STREAM"
      actions={<button className="cyber-button" style={{ fontSize: '9px', padding: '2px 6px' }} onClick={refreshInbox}>SYNC</button>}
    >
      {loading && !inbox && <div style={{ fontSize: '11px', opacity: 0.5 }}>DECRYPTING...</div>}
      
      <div style={{ display: 'grid', gap: 8 }}>
        {inbox?.items?.map((it) => (
          <div
            key={it.delivery_id}
            onClick={() => setSelectedItem(it === selectedItem ? null : it)}
            style={{
              border: `1px solid ${selectedItem === it ? 'var(--terminal-border)' : '#222'}`,
              padding: '8px',
              fontSize: '12px',
              cursor: 'pointer',
              background: selectedItem === it ? 'rgba(0, 255, 65, 0.1)' : 'transparent',
              position: 'relative'
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '9px', marginBottom: 4, opacity: 0.6 }}>
              <span>[{it.delivery_reason}]</span>
              <span>{formatTime(it.delivered_at)}</span>
            </div>
            <div style={{ 
              lineHeight: 1.4, 
              color: it.from_actor_id === 'SYSTEM' ? 'var(--terminal-warn)' : 'inherit',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              display: '-webkit-box',
              WebkitLineClamp: selectedItem === it ? 'none' : 2,
              WebkitBoxOrient: 'vertical'
            }}>
              {it.text}
            </div>
            {selectedItem === it && (
              <div style={{ marginTop: 8, paddingTop: 8, borderTop: '1px dashed #444', fontSize: '10px' }}>
                <div style={{ opacity: 0.5 }}>SOURCE_ID: {it.from_actor_id}</div>
                <div style={{ opacity: 0.5 }}>VARIANT_ID: {it.variant_id}</div>
                {it.truth_payload !== undefined && it.truth_payload !== null && (
                  <pre style={{ fontSize: '9px', color: 'var(--terminal-info)', marginTop: 4, background: '#000', padding: 4 }}>
                    {JSON.stringify(it.truth_payload as Record<string, unknown>, null, 2)}
                  </pre>
                )}
              </div>
            )}
          </div>
        ))}
        {inbox?.items?.length === 0 && <div style={{ textAlign: 'center', opacity: 0.3, padding: 20 }}>NO_DATA_IN_FEED</div>}
      </div>
    </CyberWidget>
  )
}
