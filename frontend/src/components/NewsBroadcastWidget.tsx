import { useEffect, useMemo, useState } from 'react'
import { Api, type NewsFeedItem, WsClient } from '../api'
import CyberWidget from './CyberWidget'

export default function NewsBroadcastWidget() {
  const [feed, setFeed] = useState<NewsFeedItem[]>([])
  const [currentIndex, setCurrentItemIndex] = useState(0)
  const ws = useMemo(() => new WsClient({ baseUrl: import.meta.env.VITE_API_BASE_URL }), [])
  
  const refreshFeed = async () => {
    try {
      const r = await Api.newsPublicFeed(10)
      setFeed(r.items)
    } catch (e) {
      console.error('Failed to fetch public news feed', e)
    }
  }

  useEffect(() => {
    let mounted = true
    const init = async () => {
      if (mounted) await refreshFeed()
    }
    init()
    
    ws.connect('events', (payload: unknown) => {
      const ev = payload as { event_type?: string }
      if (ev?.event_type?.startsWith('NEWS_')) {
        refreshFeed()
      }
    })
    return () => {
      mounted = false
      ws.close()
    }
  }, [ws])

  // Simple auto-cycling for the broadcast effect
  useEffect(() => {
    if (feed.length === 0) return
    const timer = setInterval(() => {
      setCurrentItemIndex((prev) => (prev + 1) % feed.length)
    }, 8000)
    return () => clearInterval(timer)
  }, [feed])

  const activeItem = feed[currentIndex]

  return (
    <CyberWidget 
      title="GLOBAL_BROADCAST" 
      subtitle="LIVE_NEURAL_FEED"
      style={{ background: '#000', border: '2px solid var(--terminal-warn)' }}
    >
      <div style={{ height: '100%', display: 'flex', flexDirection: 'column', position: 'relative', overflow: 'hidden' }}>
        {/* Main Broadcast Area */}
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', padding: '10px', paddingBottom: '30px' }}>
          {activeItem ? (
            <div key={activeItem.variant_id} className="news-fade-in" style={{ flex: 1, display: 'flex', flexDirection: 'column' }}>
              {activeItem.image_uri && (
                <div style={{ 
                  width: '100%', 
                  height: '140px', 
                  overflow: 'hidden', 
                  marginBottom: '12px',
                  border: '1px solid rgba(255,255,255,0.1)',
                  background: '#0a0a0a'
                }}>
                  <img 
                    src={activeItem.image_uri} 
                    alt="news" 
                    style={{ width: '100%', height: '100%', objectFit: 'cover', opacity: 0.8 }}
                    onError={(e) => (e.currentTarget.style.display = 'none')}
                  />
                </div>
              )}
              <div style={{ display: 'flex', gap: '8px', marginBottom: '8px' }}>
                <span style={{ 
                  background: 'var(--terminal-warn)', 
                  color: '#000', 
                  fontSize: '9px', 
                  fontWeight: 'bold', 
                  padding: '1px 4px',
                  borderRadius: '2px'
                }}>
                  {activeItem.kind}
                </span>
                <span style={{ color: '#64748b', fontSize: '9px' }}>
                  {new Date(activeItem.created_at).toLocaleTimeString()}
                </span>
              </div>
              <h2 style={{ 
                fontSize: '16px', 
                color: '#fff', 
                lineHeight: 1.3, 
                textTransform: 'uppercase',
                margin: '0 0 8px 0',
                fontFamily: 'Orbitron, sans-serif',
                letterSpacing: '1px',
                borderLeft: '3px solid var(--terminal-warn)',
                paddingLeft: '10px'
              }}>
                {activeItem.text.split('\n')[0]}
              </h2>
              <p style={{ 
                fontSize: '13px', 
                color: 'var(--terminal-text)', 
                lineHeight: 1.5,
                opacity: 0.85,
                margin: 0
              }}>
                {activeItem.text.length > 200 ? activeItem.text.substring(0, 200) + '...' : activeItem.text}
              </p>
            </div>
          ) : (
            <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#475569', fontSize: '12px' }}>
              <span className="blink">SCANNING_FOR_BROADCASTS...</span>
            </div>
          )}
        </div>

        {/* Ticker Tape Footer */}
        <div style={{ 
          position: 'absolute', 
          bottom: '0', 
          width: '100%', 
          height: '24px', 
          background: 'rgba(245, 158, 11, 0.1)', 
          borderTop: '1px solid var(--terminal-warn)',
          display: 'flex',
          alignItems: 'center',
          overflow: 'hidden'
        }}>
          <div style={{ 
            background: 'var(--terminal-warn)', 
            color: '#000', 
            fontSize: '10px', 
            fontWeight: 'bold', 
            padding: '0 8px', 
            height: '100%', 
            display: 'flex', 
            alignItems: 'center',
            zIndex: 2,
            boxShadow: '5px 0 10px rgba(0,0,0,0.5)'
          }}>
            LATEST
          </div>
          <div className="ticker-scroll" style={{ whiteSpace: 'nowrap', paddingLeft: '20px' }}>
            {feed.map((it) => (
              <span key={it.variant_id} style={{ fontSize: '11px', color: 'var(--terminal-warn)', marginRight: '40px' }}>
                <span style={{ opacity: 0.6 }}>[{new Date(it.created_at).toLocaleTimeString([], {hour:'2-digit', minute:'2-digit'})}]</span> {it.text.replace(/\n/g, ' ')}
              </span>
            ))}
          </div>
        </div>
        
        {/* Progress bar for cycle */}
        <div style={{ 
          position: 'absolute', 
          bottom: '24px', 
          left: 0, 
          height: '1px', 
          background: 'var(--terminal-warn)',
          width: feed.length > 0 ? '100%' : '0%',
          animation: 'news-progress 8s linear infinite',
          opacity: 0.5
        }} />
      </div>
      
      <style>{`
        @keyframes news-progress {
          from { width: 0%; }
          to { width: 100%; }
        }
        .news-fade-in {
          animation: fade-in 0.5s ease-out;
        }
        @keyframes fade-in {
          from { opacity: 0; transform: translateY(5px); }
          to { opacity: 1; transform: translateY(0); }
        }
        .ticker-scroll {
          display: inline-block;
          animation: ticker 30s linear infinite;
        }
        @keyframes ticker {
          0% { transform: translate3d(0, 0, 0); }
          100% { transform: translate3d(-50%, 0, 0); }
        }
        .blink {
          animation: blink-anim 1s step-end infinite;
        }
        @keyframes blink-anim {
          50% { opacity: 0; }
        }
      `}</style>
    </CyberWidget>
  )
}
