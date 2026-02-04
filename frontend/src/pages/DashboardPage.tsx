import { useState, useEffect } from 'react'
import MarketWatchWidget from '../components/MarketWatchWidget'
import MarketSummaryWidget from '../components/MarketSummaryWidget'
import MarketWidget from '../components/MarketWidget'
import TradeWidget from '../components/TradeWidget'
import NewsWidget from '../components/NewsWidget'
import ChatWidget from '../components/ChatWidget'
import AccountWidget from '../components/AccountWidget'
import HostingWidget from '../components/HostingWidget'
import ContractsWidget from '../components/ContractsWidget'
import PropagandaWidget from '../components/PropagandaWidget'
import NewsBroadcastWidget from '../components/NewsBroadcastWidget'

export default function DashboardPage() {
  const [focusWidget, setFocusWidget] = useState<string | null>(null)
  const [systemLoad, setSystemLoad] = useState(72)
  const [netSync, setNetSync] = useState(12)

  useEffect(() => {
    const timer = setInterval(() => {
      setSystemLoad(prev => Math.min(99, Math.max(40, prev + (Math.random() * 10 - 5))))
      setNetSync(Math.floor(Math.random() * 5 + 10))
    }, 3000)
    return () => clearInterval(timer)
  }, [])

  useEffect(() => {
    const handleEsc = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setFocusWidget(null)
    }
    window.addEventListener('keydown', handleEsc)
    return () => window.removeEventListener('keydown', handleEsc)
  }, [])

  const renderWidget = (id: string, Component: React.ComponentType<any>, props = {}) => {
    const isFocused = focusWidget === id
    
    return (
      <div 
        key={id}
        className={`custom-scrollbar ${!isFocused ? 'cyber-glitch' : ''}`}
        style={{ 
          position: isFocused ? 'fixed' : 'relative',
          top: isFocused ? '50%' : 'auto',
          left: isFocused ? '50%' : 'auto',
          transform: isFocused ? 'translate(-50%, -50%)' : 'none',
          width: isFocused ? 'min(1000px, 80vw)' : '100%',
          height: isFocused ? 'min(700px, 80vh)' : '100%',
          zIndex: isFocused ? 1000 : 1,
          transition: 'all 0.4s cubic-bezier(0.4, 0, 0.2, 1)',
          background: isFocused ? 'rgba(10, 15, 25, 0.98)' : 'var(--panel-bg)',
          padding: isFocused ? '20px' : '0',
          borderRadius: isFocused ? '8px' : '2px',
          border: isFocused ? '2px solid var(--terminal-info)' : '1px solid var(--terminal-border)',
          boxSizing: 'border-box',
          overflow: isFocused ? 'auto' : 'hidden',
          boxShadow: isFocused ? '0 0 100px rgba(0, 0, 0, 0.9), 0 0 30px var(--terminal-glow)' : 'none',
          resize: !isFocused ? 'both' : 'none',
        }}
      >
        {/* Interaction layer: only clicks on background trigger focus */}
        {!isFocused && (
          <div 
            onClick={() => setFocusWidget(id)}
            style={{
              position: 'absolute',
              top: 0, left: 0, right: 0, bottom: 0,
              zIndex: 5,
              cursor: 'zoom-in'
            }}
          />
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
              RETURN [ESC]
            </button>
          </div>
        )}
        <div 
          className="custom-scrollbar" 
          style={{ 
            height: '100%', 
            width: '100%', 
            pointerEvents: 'auto', 
            overflow: 'auto',
            position: 'relative',
            zIndex: 10 
          }}
        >
          <Component {...props} isFocused={isFocused} />
        </div>
      </div>
    )
  }

  return (
    <div style={{ 
      height: 'calc(100vh - 68px)', 
      display: 'grid', 
      gridTemplateColumns: 'minmax(300px, 1fr) 2fr minmax(350px, 1.2fr)', 
      gridTemplateRows: 'repeat(12, 1fr)',
      gap: '10px',
      overflow: 'hidden',
      padding: '10px',
      boxSizing: 'border-box',
      background: 'radial-gradient(circle at center, #1e293b 0%, #0f172a 100%)',
      position: 'relative'
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
        gap: '20px',
        zIndex: 10,
        background: 'rgba(15, 23, 42, 0.8)',
        padding: '2px 15px',
        borderRadius: '0 0 10px 10px',
        border: '1px solid rgba(59, 130, 246, 0.2)',
        borderTop: 'none'
      }}>
        <span className="neon-text">SYS_LOAD: {systemLoad.toFixed(1)}%</span>
        <span>NET_SYNC: {netSync}ms</span>
        <span style={{ color: 'var(--terminal-warn)' }}>THREAT: NOMINAL</span>
      </div>

      {/* Column 1: Left - Market & Account */}
      <div style={{ gridColumn: '1', gridRow: '1 / span 5' }}>
        {renderWidget('watch', MarketWatchWidget)}
      </div>
      <div style={{ gridColumn: '1', gridRow: '6 / span 4' }}>
        {renderWidget('summary', MarketSummaryWidget)}
      </div>
      <div style={{ gridColumn: '1', gridRow: '10 / span 4' }}>
        {renderWidget('account', AccountWidget)}
      </div>

      {/* Column 2: Center - Focus & Feed */}
      <div style={{ gridColumn: '2', gridRow: '1 / span 6' }}>
        {renderWidget('market', MarketWidget)}
      </div>
      <div style={{ gridColumn: '2', gridRow: '7 / span 3' }}>
        {renderWidget('broadcast', NewsBroadcastWidget)}
      </div>
      <div style={{ gridColumn: '2', gridRow: '10 / span 2', display: 'flex', gap: '10px' }}>
        <div style={{ flex: 1 }}>{renderWidget('trade', TradeWidget)}</div>
        <div style={{ flex: 1.2 }}>{renderWidget('contracts', ContractsWidget)}</div>
      </div>

      {/* Column 3: Right - Propaganda & Comms */}
      <div style={{ gridColumn: '3', gridRow: '1 / span 5' }}>
        {renderWidget('propaganda', PropagandaWidget)}
      </div>
      <div style={{ gridColumn: '3', gridRow: '6 / span 3' }}>
        {renderWidget('news', NewsWidget)}
      </div>
      <div style={{ gridColumn: '3', gridRow: '9 / span 4' }}>
        {renderWidget('chat', ChatWidget)}
      </div>
    </div>
  )
}
