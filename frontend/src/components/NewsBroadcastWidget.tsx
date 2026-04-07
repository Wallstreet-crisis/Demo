import { useEffect, useMemo, useState } from 'react'
import { Api, type NewsFeedItem, WsClient } from '../api'
import CyberWidget from './CyberWidget'
import { 
  Building2, 
  Fingerprint, 
  ShieldCheck, 
  Globe, 
  Sword, 
  Cpu,
  Zap,
  Flame,
  Newspaper,
  TrendingUp,
  Clock,
  ShieldAlert
} from 'lucide-react'

const KIND_CONFIG: Record<string, { color: string; icon: any; label: string }> = {
  RUMOR: { color: '#ff4d4f', icon: ShieldAlert, label: '传闻' },
  LEAK: { color: '#fa8c16', icon: Flame, label: '泄密' },
  ANALYST_REPORT: { color: '#1890ff', icon: TrendingUp, label: '研报' },
  OMEN: { color: '#722ed1', icon: Zap, label: '征兆' },
  DISCLOSURE: { color: '#52c41a', icon: Newspaper, label: '公告' },
  EARNINGS: { color: '#eb2f96', icon: TrendingUp, label: '财报' },
  MAJOR_EVENT: { color: '#faad14', icon: Flame, label: '要闻' },
  WORLD_EVENT: { color: '#13c2c2', icon: Globe, label: '全服' },
  SYSTEM: { color: '#8c8c8c', icon: Clock, label: '系统' },
}

const FACTION_CONFIG: Record<string, { icon: any; label: string; color: string }> = {
  CORPORATE: { icon: Building2, label: '企业联盟', color: '#1890ff' },
  UNDERGROUND: { icon: Fingerprint, label: '地下阵线', color: '#ff4d4f' },
  GOVERNMENT: { icon: ShieldCheck, label: '联邦政府', color: '#52c41a' },
  NEUTRAL: { icon: Globe, label: '中立势力', color: '#8c8c8c' },
  MERCENARY: { icon: Sword, label: '雇佣兵团', color: '#faad14' },
  HACKER: { icon: Cpu, label: '黑客组织', color: '#722ed1' },
}

const RARITY_CONFIG: Record<string, { color: string; label: string; animation?: string }> = {
  COMMON: { color: '#8c8c8c', label: '基础' },
  UNCOMMON: { color: '#52c41a', label: '罕见' },
  RARE: { color: '#1890ff', label: '珍稀' },
  EPIC: { color: '#722ed1', label: '史诗', animation: 'rarity-pulse-epic-widget 3s infinite' },
  LEGENDARY: { color: '#faad14', label: '传说', animation: 'rarity-pulse-legendary-widget 2s infinite' },
}

export default function NewsBroadcastWidget({ isFocused, onShowNews }: { isFocused?: boolean, onShowNews?: (item: NewsFeedItem) => void }) {
  void isFocused
  const [feed, setFeed] = useState<NewsFeedItem[]>([])
  const [currentIndex, setCurrentItemIndex] = useState(0)
  const [isGlitching, setIsGlitching] = useState(false)
  const ws = useMemo(() => new WsClient({ baseUrl: import.meta.env.VITE_API_BASE_URL }), [])

  const getNewsItemKey = (item: NewsFeedItem, index: number) => {
    return item.variant_id || item.card_id || `${item.kind}-${item.created_at}-${index}`
  }

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
      if (ev?.event_type?.startsWith('news.')) {
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
      setIsGlitching(true)
      setTimeout(() => {
        setCurrentItemIndex((prev) => (prev + 1) % feed.length)
        setIsGlitching(false)
      }, 150)
    }, 8000)
    return () => clearInterval(timer)
  }, [feed])

  const handleManualNav = (dir: 'next' | 'prev') => {
    setIsGlitching(true)
    setTimeout(() => {
      if (dir === 'next') {
        setCurrentItemIndex((prev) => (prev + 1) % feed.length)
      } else {
        setCurrentItemIndex((prev) => (prev - 1 + feed.length) % feed.length)
      }
      setIsGlitching(false)
    }, 150)
  }

  const activeItem = feed[currentIndex]
  const rarity = (activeItem?.rarity || 'COMMON').toUpperCase()
  const rarityConfig = RARITY_CONFIG[rarity] || RARITY_CONFIG.COMMON
  
  const kind = (activeItem?.kind || 'SYSTEM').toUpperCase()
  const kindConfig = KIND_CONFIG[kind] || KIND_CONFIG.SYSTEM
  
  const faction = (activeItem?.faction || 'NEUTRAL').toUpperCase()
  const factionConfig = FACTION_CONFIG[faction] || FACTION_CONFIG.NEUTRAL
  const FactionIcon = factionConfig.icon

  return (
    <CyberWidget 
      title="GLOBAL_BROADCAST" 
      subtitle="LIVE_NEURAL_FEED"
      style={{ 
        background: '#000', 
        borderWidth: '2px',
        borderStyle: 'solid',
        borderColor: rarityConfig.color,
        animation: rarityConfig.animation || 'none',
        transition: 'all 0.5s ease'
      }}
      actions={
        <div style={{ display: 'flex', gap: '4px' }}>
          <button className="cyber-button" style={{ fontSize: '10px', padding: '2px 6px' }} onClick={() => handleManualNav('prev')}>◄</button>
          <button className="cyber-button" style={{ fontSize: '10px', padding: '2px 6px' }} onClick={() => handleManualNav('next')}>►</button>
        </div>
      }
    >
      <div 
        onClick={() => activeItem && onShowNews?.(activeItem)}
        style={{ height: '100%', display: 'flex', flexDirection: 'column', position: 'relative', overflow: 'hidden', cursor: onShowNews ? 'pointer' : 'default' }}
      >
        {/* Main Broadcast Area */}
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', padding: '10px', paddingBottom: '30px' }}>
          {activeItem ? (
            <div key={getNewsItemKey(activeItem, currentIndex)} className={`news-fade-in ${isGlitching ? 'glitch-effect' : ''}`} style={{ flex: 1, display: 'flex', flexDirection: 'column' }}>
              {activeItem.image_uri && (
                <div style={{ 
                  width: '100%', 
                  height: '140px', 
                  overflow: 'hidden', 
                  marginBottom: '12px',
                  borderWidth: '1px',
                  borderStyle: 'solid',
                  borderColor: 'rgba(255,255,255,0.1)',
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
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' }}>
                <span style={{ 
                  background: rarityConfig.color, 
                  color: '#000', 
                  fontSize: '9px', 
                  fontWeight: 'bold', 
                  padding: '1px 6px',
                  borderRadius: '2px',
                  textTransform: 'uppercase'
                }}>
                  {kindConfig.label}
                </span>
                <div style={{ 
                  display: 'flex', 
                  alignItems: 'center', 
                  gap: '4px',
                  fontSize: '9px',
                  color: factionConfig.color,
                  background: 'rgba(0,0,0,0.4)',
                  padding: '1px 6px',
                  borderRadius: '2px',
                  border: `1px solid ${factionConfig.color}44`
                }}>
                  <FactionIcon size={10} />
                  {factionConfig.label}
                </div>
                <span style={{ color: '#64748b', fontSize: '9px', marginLeft: 'auto' }}>
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
                borderLeftWidth: '3px',
                borderLeftStyle: 'solid',
                borderLeftColor: rarityConfig.color,
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
            {feed.map((it, index) => (
              <span key={getNewsItemKey(it, index)} style={{ fontSize: '11px', color: 'var(--terminal-warn)', marginRight: '40px' }}>
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
        @keyframes rarity-pulse-epic-widget {
          0% { box-shadow: 0 0 5px rgba(114, 46, 209, 0.2); }
          50% { box-shadow: 0 0 15px rgba(114, 46, 209, 0.4); }
          100% { box-shadow: 0 0 5px rgba(114, 46, 209, 0.2); }
        }
        @keyframes rarity-pulse-legendary-widget {
          0% { box-shadow: 0 0 8px rgba(250, 173, 20, 0.3); }
          50% { box-shadow: 0 0 25px rgba(250, 173, 20, 0.6); }
          100% { box-shadow: 0 0 8px rgba(250, 173, 20, 0.3); }
        }
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
        .glitch-effect {
          animation: glitch 0.2s linear infinite;
          filter: hue-rotate(90deg) contrast(150%);
        }
        @keyframes glitch {
          0% { transform: translate(0); }
          20% { transform: translate(-2px, 2px); }
          40% { transform: translate(-2px, -2px); }
          60% { transform: translate(2px, 2px); }
          80% { transform: translate(2px, -2px); }
          100% { transform: translate(0); }
        }
      `}</style>
    </CyberWidget>
  )
}
