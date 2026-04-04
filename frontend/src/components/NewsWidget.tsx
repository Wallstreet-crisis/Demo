import { Link } from 'react-router-dom'
import { useEffect, useMemo, useRef, useState } from 'react'
import { Api, type NewsFeedItem, type NewsInboxResponse, type NewsInboxResponseItem } from '../api'
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

export default function NewsWidget({ onShowNews, isFocused }: { onShowNews?: (item: NewsFeedItem) => void, isFocused?: boolean }) {
  void isFocused
  const { playerId } = useAppSession()
  const [inbox, setInbox] = useState<NewsInboxResponse | null>(null)
  const [selectedItem, setSelectedItem] = useState<NewsInboxResponseItem | null>(null)

  const ws = useMemo(() => new WsClient({ baseUrl: import.meta.env.VITE_API_BASE_URL }), [])
  const refreshTimerRef = useRef<number | null>(null)

  const refreshInbox = async () => {
    if (!playerId) return
    try {
      const r = await Api.newsInbox(`user:${playerId}`, 50)
      setInbox(r)
    } catch (e) {
      console.error('Failed to refresh inbox', e)
    }
  }

  useEffect(() => {
    refreshInbox()
    
    ws.connect('events', (payload: unknown) => {
      const t = getEventType(payload)
      if (typeof t === 'string' && t.startsWith('news.')) {
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
      actions={
        <div style={{ display: 'flex', gap: '4px' }}>
          <Link to="/news">
            <button className="cyber-button" style={{ fontSize: '11px', padding: '2px 8px', color: 'var(--terminal-info)' }}>CENTER</button>
          </Link>
          <button className="cyber-button" style={{ fontSize: '11px', padding: '2px 8px' }} onClick={refreshInbox}>SYNC</button>
        </div>
      }
    >
      <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
        {(isFocused ? (inbox?.items || []) : (inbox?.items || []).slice(0, 5)).map((it) => (
          <div
            key={it.delivery_id}
            onClick={() => {
              if (onShowNews) {
                const truth = (it.truth_payload && typeof it.truth_payload === 'object')
                  ? (it.truth_payload as Record<string, unknown>)
                  : null
                const imageUri = truth && typeof truth.image_uri === 'string' ? truth.image_uri : null
                // Prepare feed-like item for the popup
                onShowNews({
                  variant_id: it.variant_id,
                  card_id: it.card_id,
                  kind: it.kind,
                  author_id: it.from_actor_id,
                  text: it.text,
                  image_uri: imageUri,
                  created_at: it.delivered_at,
                  symbols: it.symbols || [],
                  tags: it.tags || []
                });
              } else {
                setSelectedItem(it === selectedItem ? null : it);
              }
            }}
            style={{
              borderBottom: '1px solid rgba(51, 65, 85, 0.3)',
              padding: '10px 8px',
              fontSize: '13px',
              cursor: 'pointer',
              background: selectedItem === it ? 'rgba(59, 130, 246, 0.1)' : 'transparent',
              transition: 'background 0.1s'
            }}
            onMouseOver={e => selectedItem !== it && (e.currentTarget.style.background = 'rgba(255,255,255,0.02)')}
            onMouseOut={e => selectedItem !== it && (e.currentTarget.style.background = 'transparent')}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '10px', marginBottom: '4px', color: '#64748b', fontWeight: '600' }}>
              <span style={{ color: it.from_actor_id === 'SYSTEM' ? 'var(--terminal-warn)' : '#3b82f6' }}>
                [{it.delivery_reason}]
              </span>
              <span>{formatTime(it.delivered_at)}</span>
            </div>
            <div style={{ 
              lineHeight: 1.5, 
              color: '#f1f5f9',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              display: '-webkit-box',
              WebkitLineClamp: selectedItem === it ? 'none' : 2,
              WebkitBoxOrient: 'vertical'
            }}>
              {it.text}
            </div>
            {selectedItem === it && (
              <div style={{ 
                marginTop: '12px', 
                padding: '10px', 
                background: 'rgba(0,0,0,0.2)', 
                border: '1px solid var(--terminal-border)',
                borderRadius: '2px',
                fontSize: '11px' 
              }}>
                <div style={{ color: '#94a3b8', marginBottom: '4px' }}>SOURCE: <code style={{ color: '#3b82f6' }}>{it.from_actor_id}</code></div>
                <div style={{ color: '#94a3b8', marginBottom: '8px' }}>VARIANT: <code style={{ color: '#94a3b8' }}>{it.variant_id}</code></div>
                {it.truth_payload !== undefined && it.truth_payload !== null && (
                  <pre style={{ 
                    fontSize: '10px', 
                    color: 'var(--terminal-success)', 
                    marginTop: '8px', 
                    background: '#0f172a', 
                    padding: '8px',
                    borderLeft: '2px solid var(--terminal-success)',
                    overflow: 'auto'
                  }}>
                    {JSON.stringify(it.truth_payload as Record<string, unknown>, null, 2)}
                  </pre>
                )}
              </div>
            )}
          </div>
        ))}
        {inbox?.items?.length === 0 && (
          <div style={{ textAlign: 'center', color: '#64748b', padding: '40px 20px', fontSize: '13px' }}>
            NO_INTEL_STREAM_DETECTED
          </div>
        )}
      </div>
    </CyberWidget>
  )
}
