import { useState, useEffect } from 'react'
import MarketWatchWidget from '../components/MarketWatchWidget'
import MarketSummaryWidget from '../components/MarketSummaryWidget'
import MarketWidget from '../components/MarketWidget'
import TradeWidget from '../components/TradeWidget'
import NewsWidget from '../components/NewsWidget'
import ChatWidget from '../components/ChatWidget'
import AccountWidget from '../components/AccountWidget'
import ContractsWidget from '../components/ContractsWidget'
import PropagandaWidget from '../components/PropagandaWidget'
import NewsBroadcastWidget from '../components/NewsBroadcastWidget'
import { Api, WsClient, type NewsFeedItem } from '../api'
import { useAppSession } from '../app/context'

export default function DashboardPage() {
  const [focusWidget, setFocusWidget] = useState<string | null>(null)
  const [systemLoad, setSystemLoad] = useState(72)
  const [netSync, setNetSync] = useState(12)
  const [logs, setLogs] = useState<{ id: string; text: string; type: 'info' | 'warn' | 'err' }[]>([])
  const [aiHosting, setAiHosting] = useState(false)
  const [viewportWidth, setViewportWidth] = useState(() =>
    typeof window === 'undefined' ? 1400 : window.innerWidth,
  )
  const { playerId } = useAppSession()
  const isTabletLayout = viewportWidth <= 1280
  
  // News Popup State
  const [activePopupNews, setActivePopupNews] = useState<NewsFeedItem | null>(null)

  // Fetch AI Hosting status
  useEffect(() => {
    if (!playerId) return
    Api.hostingStatus(`user:${playerId}`).then(res => {
      setAiHosting(res.enabled)
    }).catch(e => console.error('Failed to fetch hosting status', e))
  }, [playerId])

  const toggleAiHosting = async () => {
    if (!playerId) return
    const targetState = !aiHosting
    try {
      if (targetState) {
        await Api.hostingEnable(`user:${playerId}`)
        setLogs(prev => [{ id: Math.random().toString(36).slice(2, 9), text: 'AI_PROXY_PROTOCOL_ENGAGED', type: 'info' as const }, ...prev].slice(0, 8))
      } else {
        await Api.hostingDisable(`user:${playerId}`)
        setLogs(prev => [{ id: Math.random().toString(36).slice(2, 9), text: 'AI_PROXY_PROTOCOL_TERMINATED', type: 'warn' as const }, ...prev].slice(0, 8))
      }
      setAiHosting(targetState)
    } catch (e) {
      console.error('Failed to toggle AI hosting', e)
      setLogs(prev => [{ id: Math.random().toString(36).slice(2, 9), text: 'AI_PROXY_SYNCHRONIZATION_ERROR', type: 'err' as const }, ...prev].slice(0, 8))
    }
  }

  useEffect(() => {
    const logPool = [
      { text: 'QUANTUM_LINK_ESTABLISHED', type: 'info' },
      { text: 'DECRYPTING_NEWS_PACKET_722', type: 'info' },
      { text: 'MARKET_DATA_SYNC_COMPLETED', type: 'info' },
      { text: 'NEURAL_INTERFACE_STABLE', type: 'info' },
      { text: 'ENCRYPTED_THREAD_OPENED', type: 'info' },
      { text: 'SUBSYSTEM_LATENCY_NOMINAL', type: 'info' },
      { text: 'HEURISTIC_DRAFTING_ACTIVE', type: 'info' },
      { text: 'INFLUENCE_ARRAY_SCANNING', type: 'info' },
      { text: 'ANOMALY_DETECTED_IN_SECTOR_4', type: 'warn' },
      { text: 'BUFFER_OVERFLOW_PREVENTED', type: 'warn' },
      { text: 'CORE_TEMPERATURE_INCREASING', type: 'warn' },
    ] as const;

    const timer = setInterval(() => {
      setSystemLoad(prev => Math.min(99, Math.max(40, prev + (Math.random() * 10 - 5))))
      setNetSync(Math.floor(Math.random() * 5 + 10))
      
      // Randomly add a log
      if (Math.random() > 0.6) {
        const item = logPool[Math.floor(Math.random() * logPool.length)];
        setLogs(prev => [{ id: Math.random().toString(36).slice(2, 9), ...item }, ...prev].slice(0, 8));
      }
    }, 3000)
    return () => clearInterval(timer)
  }, [])

  useEffect(() => {
    const handleEsc = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        if (activePopupNews) setActivePopupNews(null)
        else setFocusWidget(null)
      }
    }
    window.addEventListener('keydown', handleEsc)
    return () => window.removeEventListener('keydown', handleEsc)
  }, [activePopupNews])

  useEffect(() => {
    const handleResize = () => setViewportWidth(window.innerWidth)
    window.addEventListener('resize', handleResize)
    return () => window.removeEventListener('resize', handleResize)
  }, [])

  // Subscribe to news for auto-popup
  useEffect(() => {
    const ws = new WsClient()
    ws.connect('events', (data: unknown) => {
      const ev = data as { event_type: string; payload: NewsFeedItem };
      if (ev?.event_type === 'NEWS_VARIANT_EMITTED' || ev?.event_type === 'NEWS_BROADCASTED') {
        const item = ev.payload;
        // If it's a major event or has an image, show popup
        if (item && (item.kind === 'MAJOR_EVENT' || item.kind === 'WORLD_EVENT' || item.image_uri)) {
          setActivePopupNews(item)
        }
      }
    })
    return () => ws.close()
  }, [])

  const renderWidget = <P extends { isFocused?: boolean }>(
    id: string, 
    Component: React.ComponentType<P>, 
    props: Omit<P, 'isFocused'> = {} as Omit<P, 'isFocused'>
  ) => {
    const isFocused = focusWidget === id
    const canFocus = id !== 'watch'
    
    const widgetContent = (
      <div 
        key={id}
        onMouseDown={(e) => {
          const target = e.target as HTMLElement;
          const interactiveTags = ['BUTTON', 'INPUT', 'SELECT', 'TEXTAREA', 'A', 'LABEL'];
          
          const rect = e.currentTarget.getBoundingClientRect();
          // Detect if clicking on the resize handle (bottom-right 24x24 area)
          const isResizeHandle = (e.clientX > rect.right - 24) && (e.clientY > rect.bottom - 24);

          if (canFocus && !isFocused && !interactiveTags.includes(target.tagName) && !target.closest('.cyber-button') && !isResizeHandle) {
            setFocusWidget(id);
          }
        }}
        className="custom-scrollbar cockpit-panel"
        style={{ 
          position: isFocused ? 'fixed' : 'relative',
          top: isFocused ? '50%' : 'auto',
          left: isFocused ? '50%' : 'auto',
          transform: isFocused ? 'translate(-50%, -50%)' : 'none',
          width: isFocused ? '80vw' : '100%',
          height: isFocused ? '80vh' : '100%',
          maxWidth: isFocused ? '1200px' : 'none',
          maxHeight: isFocused ? '850px' : 'none',
          zIndex: isFocused ? 1000 : 1,
          transition: focusWidget === null || isFocused ? 'all 0.3s cubic-bezier(0.4, 0, 0.2, 1)' : 'none',
          background: isFocused ? 'rgba(10, 15, 25, 0.98)' : 'var(--panel-bg)',
          padding: isFocused ? '24px' : '0',
          borderRadius: isFocused ? '8px' : '2px',
          border: isFocused ? '2px solid var(--terminal-info)' : '1px solid var(--terminal-border)',
          boxSizing: 'border-box',
          overflow: isFocused ? 'auto' : 'hidden',
          boxShadow: isFocused ? '0 0 100px rgba(0, 0, 0, 0.9), 0 0 30px var(--terminal-glow)' : 'none',
          resize: canFocus && !isFocused ? 'both' : 'none',
          cursor: canFocus && !isFocused ? 'zoom-in' : 'default',
        }}
      >
        {canFocus && !isFocused && (
          <div style={{ 
            position: 'absolute', bottom: '2px', right: '2px', 
            width: '12px', height: '12px', 
            borderRight: '2px solid rgba(59, 130, 246, 0.4)', 
            borderBottom: '2px solid rgba(59, 130, 246, 0.4)', 
            pointerEvents: 'none',
            zIndex: 10
          }} />
        )}
        {isFocused && (
          <div style={{ 
            position: 'absolute', 
            top: '10px', 
            right: '10px', 
            zIndex: 1001,
            display: 'flex',
            gap: '10px'
          }}>
            <button 
              className="cyber-button"
              onClick={(e) => { e.stopPropagation(); setFocusWidget(null); }}
              style={{ background: 'rgba(239, 68, 68, 0.2)', borderColor: '#ef4444' }}
            >
              CLOSE [ESC]
            </button>
          </div>
        )}
        <div 
          style={{ 
            height: '100%', 
            width: '100%', 
            pointerEvents: 'auto', 
            overflow: 'hidden'
          }}
        >
          <Component {...({ ...(props as Omit<P, 'isFocused'>), isFocused } as P)} />
        </div>
      </div>
    )

    return (
      <div key={id} style={{ width: '100%', height: '100%', position: 'relative' }}>
        {/* Placeholder to keep layout stable when widget is fixed */}
        {isFocused && (
          <div style={{ 
            width: '100%', height: '100%', 
            background: 'rgba(0,0,0,0.1)', 
            border: '1px dashed var(--terminal-border)',
            borderRadius: '2px'
          }} />
        )}
        {widgetContent}
      </div>
    )
  }

  return (
    <div style={{ 
      height: isTabletLayout ? 'auto' : 'calc(100vh - 68px)', 
      minHeight: isTabletLayout ? 'calc(100vh - 68px)' : undefined,
      display: 'grid', 
      gridTemplateColumns: isTabletLayout
        ? 'repeat(2, minmax(320px, 1fr))'
        : 'minmax(300px, 1fr) 2fr minmax(350px, 1.2fr)', 
      gridTemplateRows: isTabletLayout ? 'none' : 'repeat(12, 1fr)',
      gridAutoRows: isTabletLayout ? 'minmax(260px, auto)' : undefined,
      gap: '10px',
      overflowX: 'hidden',
      overflowY: isTabletLayout ? 'auto' : 'hidden',
      padding: isTabletLayout ? '34px 10px 10px' : '10px',
      boxSizing: 'border-box',
      background: 'radial-gradient(circle at center, #1e293b 0%, #0f172a 100%)',
      position: 'relative',
      alignContent: 'start',
    }}>
      {/* HUD Background Decorations */}
      <div style={{ 
        position: 'absolute', 
        top: 0, left: 0, right: 0, bottom: 0, 
        pointerEvents: 'none', 
        opacity: 0.03,
        background: 'linear-gradient(90deg, var(--terminal-border) 1px, transparent 1px) 0 0 / 40px 40px, linear-gradient(var(--terminal-border) 1px, transparent 1px) 0 0 / 40px 40px'
      }} />
      
      <div className="scanlines-overlay" />
      {focusWidget && <div className="zoom-backdrop" onClick={() => setFocusWidget(null)} />}

      {/* News Popup Modal */}
      {activePopupNews && (
        <div style={{
          position: 'fixed',
          top: 0, left: 0, right: 0, bottom: 0,
          background: 'rgba(0,0,0,0.85)',
          zIndex: 2000,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          backdropFilter: 'blur(4px)'
        }} onClick={() => setActivePopupNews(null)}>
          <div 
            style={{
              width: 'min(600px, 90vw)',
              background: 'var(--panel-bg)',
              border: '2px solid var(--terminal-info)',
              boxShadow: '0 0 30px var(--terminal-glow)',
              padding: '20px',
              position: 'relative',
              animation: 'glitch-in 0.3s ease-out'
            }}
            onClick={e => e.stopPropagation()}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '15px', borderBottom: '1px solid var(--terminal-border)', paddingBottom: '10px' }}>
              <div>
                <span style={{ color: 'var(--terminal-info)', fontWeight: 'bold', fontSize: '14px' }}>[{activePopupNews.kind}]</span>
                <span style={{ marginLeft: '10px', fontSize: '12px', opacity: 0.6 }}>{new Date(activePopupNews.created_at).toLocaleString()}</span>
              </div>
              <button className="cyber-button" onClick={() => setActivePopupNews(null)} style={{ padding: '2px 8px' }}>X</button>
            </div>
            
            {activePopupNews.image_uri && (
              <div style={{ marginBottom: '15px', border: '1px solid var(--terminal-border)', overflow: 'hidden' }}>
                <img src={activePopupNews.image_uri} alt="News" style={{ width: '100%', display: 'block' }} />
              </div>
            )}
            
            <div style={{ fontSize: '16px', lineHeight: '1.6', color: '#fff', whiteSpace: 'pre-wrap' }}>
              {activePopupNews.text}
            </div>
            
            {activePopupNews.symbols && activePopupNews.symbols.length > 0 && (
              <div style={{ marginTop: '20px', display: 'flex', gap: '10px' }}>
                {activePopupNews.symbols.map(s => (
                  <span key={s} style={{ fontSize: '10px', background: 'rgba(59, 130, 246, 0.2)', padding: '2px 6px', border: '1px solid var(--terminal-info)', color: 'var(--terminal-info)' }}>
                    ${s}
                  </span>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {/* Top Status Bar */}
      <div style={{ 
        position: 'absolute', 
        top: '2px', 
        left: '50%', 
        transform: 'translateX(-50%)',
        fontSize: '9px',
        fontFamily: 'monospace',
        color: 'var(--terminal-info)',
        display: 'flex',
        alignItems: 'center',
        gap: '20px',
        zIndex: 10,
        background: 'rgba(15, 23, 42, 0.8)',
        padding: '2px 15px',
        borderRadius: '0 0 10px 10px',
        border: '1px solid rgba(59, 130, 246, 0.2)',
        borderTop: 'none',
        backdropFilter: 'blur(4px)'
      }}>
        <span className="neon-text">SYS_LOAD: {systemLoad.toFixed(1)}%</span>
        <span>NET_SYNC: {netSync}ms</span>
        
        {/* AI Proxy Toggle */}
        <div 
          onClick={toggleAiHosting}
          style={{ 
            display: 'flex', 
            alignItems: 'center', 
            gap: '6px', 
            cursor: 'pointer',
            padding: '2px 6px',
            borderRadius: '4px',
            background: aiHosting ? 'rgba(59, 130, 246, 0.2)' : 'rgba(255,255,255,0.05)',
            border: `1px solid ${aiHosting ? 'var(--terminal-info)' : 'rgba(255,255,255,0.1)'}`,
            transition: 'all 0.2s'
          }}
        >
          <div style={{ 
            width: '6px', height: '6px', borderRadius: '50%', 
            background: aiHosting ? 'var(--terminal-info)' : '#475569',
            boxShadow: aiHosting ? '0 0 8px var(--terminal-info)' : 'none',
            animation: aiHosting ? 'blink-anim 1s step-end infinite' : 'none'
          }} />
          <span style={{ color: aiHosting ? '#fff' : '#64748b', fontWeight: 'bold' }}>AI_PROXY: {aiHosting ? 'ACTIVE' : 'OFF'}</span>
        </div>

        <span style={{ color: 'var(--terminal-warn)' }}>THREAT: NOMINAL</span>
      </div>

      {/* Column 1: Left - Market & Account */}
      <div style={isTabletLayout ? { gridColumn: 'span 1' } : { gridColumn: '1', gridRow: '1 / span 5' }}>
        {renderWidget('watch', MarketWatchWidget)}
      </div>
      <div style={isTabletLayout ? { gridColumn: 'span 1' } : { gridColumn: '1', gridRow: '6 / span 4' }}>
        {renderWidget('summary', MarketSummaryWidget)}
      </div>
      <div style={isTabletLayout ? { gridColumn: 'span 1' } : { gridColumn: '1', gridRow: '10 / span 4' }}>
        {renderWidget('account', AccountWidget)}
      </div>

      {/* Column 2: Center - Focus & Feed */}
      <div style={isTabletLayout ? { gridColumn: '1 / -1' } : { gridColumn: '2', gridRow: '1 / span 6' }}>
        {renderWidget('market', MarketWidget)}
      </div>
      <div style={isTabletLayout ? { gridColumn: '1 / -1' } : { gridColumn: '2', gridRow: '7 / span 3' }}>
        {renderWidget('broadcast', NewsBroadcastWidget, { onShowNews: setActivePopupNews })}
      </div>
      <div
        style={isTabletLayout
          ? { gridColumn: '1 / -1', display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: '10px' }
          : { gridColumn: '2', gridRow: '10 / span 3', display: 'flex', gap: '10px' }}
      >
        <div style={{ flex: 1 }}>{renderWidget('trade', TradeWidget)}</div>
        <div style={{ flex: 1.2 }}>{renderWidget('contracts', ContractsWidget)}</div>
      </div>

      {/* Column 3: Right - Propaganda & Comms */}
      <div style={isTabletLayout ? { gridColumn: 'span 1' } : { gridColumn: '3', gridRow: '1 / span 5' }}>
        {renderWidget('propaganda', PropagandaWidget)}
      </div>
      <div style={isTabletLayout ? { gridColumn: 'span 1' } : { gridColumn: '3', gridRow: '6 / span 3' }}>
        {renderWidget('news', NewsWidget, { onShowNews: setActivePopupNews })}
      </div>
      <div style={isTabletLayout ? { gridColumn: 'span 1' } : { gridColumn: '3', gridRow: '9 / span 4' }}>
        {renderWidget('chat', ChatWidget)}
      </div>
    </div>
  )
}
