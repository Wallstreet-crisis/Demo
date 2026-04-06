import { Link } from 'react-router-dom'
import { useEffect, useMemo, useRef, useState } from 'react'
import { Api, type NewsFeedItem, type NewsInboxResponse } from '../api'
import { useAppSession } from '../app/context'
import { WsClient } from '../api'
import IntelligenceCard from './IntelligenceCard'
import { Newspaper, ChevronRight } from 'lucide-react'

function getEventType(payload: unknown): string | null {
  if (!payload || typeof payload !== 'object') return null
  const v = (payload as Record<string, unknown>).event_type
  return typeof v === 'string' ? v : null
}

export default function NewsWidget({ isFocused }: { onShowNews?: (item: NewsFeedItem) => void, isFocused?: boolean }) {
  void isFocused
  const { playerId, roomId } = useAppSession()
  const [inbox, setInbox] = useState<NewsInboxResponse | null>(null)
  const [selectedId, setSelectedId] = useState<string | null>(null)

  const ws = useMemo(() => new WsClient({ baseUrl: import.meta.env.VITE_API_BASE_URL }), [])
  const refreshTimerRef = useRef<number | null>(null)

  const refreshInbox = async () => {
    if (!playerId) return
    try {
      const r = await Api.newsInbox(`user:${playerId}`, 10)
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
  }, [playerId, roomId])

  const items = useMemo(() => {
    return (inbox?.items || []).slice(0, 6)
  }, [inbox])

  return (
    <div style={{ 
      display: 'flex', 
      flexDirection: 'column', 
      height: '100%',
      background: 'rgba(0,0,0,0.2)',
      borderRadius: '12px',
      overflow: 'hidden'
    }}>
      {/* Header */}
      <div style={{ 
        padding: '12px 16px', 
        display: 'flex', 
        justifyContent: 'space-between', 
        alignItems: 'center',
        borderBottom: '1px solid rgba(255,255,255,0.05)'
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <Newspaper size={16} color="var(--terminal-info)" />
          <span style={{ fontWeight: 'bold', fontSize: '13px', letterSpacing: '1px' }}>INTELLIGENCE_INBOX</span>
        </div>
        <Link to="/news" style={{ textDecoration: 'none' }}>
          <button className="cyber-button mini" style={{ display: 'flex', alignItems: 'center', gap: '4px', fontSize: '10px' }}>
            ALL_FILES <ChevronRight size={12} />
          </button>
        </Link>
      </div>

      {/* Card Content */}
      <div style={{ 
        flex: 1, 
        overflowX: 'auto', 
        overflowY: 'hidden',
        display: 'flex',
        gap: '16px',
        padding: '16px',
        alignItems: 'center',
        background: 'linear-gradient(180deg, transparent 0%, rgba(0,0,0,0.3) 100%)'
      }}>
        {items.length > 0 ? (
          items.map((it) => (
            <div key={it.delivery_id} style={{ flexShrink: 0 }}>
              <IntelligenceCard 
                item={it}
                isSelected={selectedId === it.delivery_id}
                onClick={() => setSelectedId(it.delivery_id === selectedId ? null : it.delivery_id)}
                showActions={false} // Dashboard don't show full actions to save space
                className="dashboard-mini-card"
              />
            </div>
          ))
        ) : (
          <div style={{ 
            width: '100%', 
            height: '100%', 
            display: 'flex', 
            flexDirection: 'column', 
            alignItems: 'center', 
            justifyContent: 'center',
            color: '#444',
            gap: '8px'
          }}>
            <Newspaper size={32} opacity={0.1} />
            <span style={{ fontSize: '12px', letterSpacing: '2px' }}>NO_ACTIVE_INTEL</span>
          </div>
        )}
      </div>

      <style>{`
        .dashboard-mini-card {
          transform: scale(0.85);
          transform-origin: center center;
          transition: all 0.3s ease !important;
        }
        .dashboard-mini-card:hover {
          transform: scale(0.9) translateY(-5px) !important;
        }
        .dashboard-mini-card.selected {
          transform: scale(0.95) !important;
          box-shadow: 0 0 20px rgba(0, 140, 255, 0.3) !important;
        }
      `}</style>
    </div>
  )
}

