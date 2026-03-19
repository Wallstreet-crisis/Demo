import { Link, Navigate, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { useAppSession } from './context'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { Api, WsClient, type MarketSessionResponse } from '../api'

import { CASTES } from './constants'
import SettingsModal from '../components/SettingsModal'

function NavItem(props: { to: string; label: string }) {
  const loc = useLocation()
  const active = loc.pathname === props.to
  return (
    <Link
      to={props.to}
      className={active ? 'cyber-button active' : 'cyber-button'}
      style={{
        fontSize: '12px',
        padding: '4px 12px',
        textDecoration: 'none',
        background: active ? 'var(--terminal-info)' : 'transparent',
        border: 'none',
        color: active ? '#fff' : '#94a3b8',
        fontWeight: active ? '600' : '500'
      }}
    >
      {props.label}
    </Link>
  )
}

function NewsTicker() {
  const { playerId } = useAppSession()
  const [news, setNews] = useState<string[]>([])

  useEffect(() => {
    if (!playerId) return
    const fetchNews = async () => {
      try {
        const res = await Api.newsInbox(`user:${playerId}`, 5)
        setNews(res.items.map(it => it.text))
      } catch (e) {
        console.error('Ticker fetch failed', e)
      }
    }
    fetchNews()
    const t = setInterval(fetchNews, 30000)
    return () => clearInterval(t)
  }, [playerId])

  if (news.length === 0) return <div>SYSTEM_READY // NO_CRITICAL_ALERTS</div>

  return (
    <div style={{ display: 'flex', overflow: 'hidden', whiteSpace: 'nowrap', width: '100%' }}>
      <div style={{ 
        display: 'inline-block', 
        paddingLeft: '100%', 
        animation: 'ticker 60s linear infinite',
        color: 'var(--terminal-warn)'
      }}>
        {news.map((text, i) => (
          <span key={i} style={{ marginRight: '50px' }}>
            [BREAKING] {text.toUpperCase()}
          </span>
        ))}
      </div>
      <style>{`
        @keyframes ticker {
          0% { transform: translate3d(0, 0, 0); }
          100% { transform: translate3d(-100%, 0, 0); }
        }
      `}</style>
    </div>
  )
}

export default function Layout() {
  const sess = useAppSession()
  const nav = useNavigate()
  const [cash, setCash] = useState<number | null>(null)
  const [totalValue, setTotalValue] = useState<number | null>(null)
  const [valuationOk, setValuationOk] = useState<boolean>(true)
  const [hostingLoading, setHostingLoading] = useState(false)
  const [marketSession, setMarketSession] = useState<MarketSessionResponse | null>(null)
  const [settingsOpen, setSettingsOpen] = useState(false)

  const [systemMenuOpen, setSystemMenuOpen] = useState(false)
  const [disconnectConfirm, setDisconnectConfirm] = useState(false)

  const presenceWs = useMemo(() => new WsClient({ baseUrl: import.meta.env.VITE_API_BASE_URL }), [])

  const caste = useMemo(() => {
    return CASTES.find(c => c.id === sess.casteId)
  }, [sess.casteId])

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        if (settingsOpen) {
          setSettingsOpen(false)
        } else {
          setSystemMenuOpen(prev => {
            if (prev) setDisconnectConfirm(false)
            return !prev
          })
        }
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [settingsOpen])

  const fetchStatus = useCallback(async () => {
    if (!sess.playerId) return
    try {
      const [hRes, mRes] = await Promise.all([
        Api.hostingStatus(`user:${sess.playerId}`),
        Api.marketSession()
      ])
      sess.setAiHosting(hRes.enabled)
      setMarketSession(mRes)
    } catch (e) {
      console.error('Failed to fetch status', e)
    }
  }, [sess])

  useEffect(() => {
    fetchStatus()
    const t = setInterval(fetchStatus, 10000)
    return () => clearInterval(t)
  }, [fetchStatus])

  useEffect(() => {
    const playerId = sess.playerId
    if (!playerId) return
    if (!/^[a-zA-Z0-9_]{3,20}$/.test(playerId)) return

    presenceWs.connect('presence', () => {})
    return () => presenceWs.close()
  }, [sess.playerId, presenceWs])

  const handleReAuth = async () => {
    // 尝试通知后端当前玩家离开。如果当前是该房间的唯一玩家，后端可以关闭引擎
    if (sess.roomId && sess.roomId !== 'default') {
      try {
        await Api.closeRoom(sess.roomId)
      } catch (e) {
        console.warn('Failed to close room:', e)
      }
    }
    sess.setPlayerId('')
    sess.setCasteId('' as any)
    nav('/menu')
  }

  const toggleHosting = async () => {
    if (!sess.playerId || hostingLoading) return
    setHostingLoading(true)
    try {
      const targetState = !sess.aiHosting
      if (targetState) {
        await Api.hostingEnable(`user:${sess.playerId}`)
      } else {
        await Api.hostingDisable(`user:${sess.playerId}`)
      }
      sess.setAiHosting(targetState)
    } catch (e) {
      console.error('Failed to toggle hosting', e)
    } finally {
      setHostingLoading(false)
    }
  }

  useEffect(() => {
    const playerId = sess.playerId
    if (!playerId) return
    if (!/^[a-zA-Z0-9_]{3,20}$/.test(playerId)) return
    let canceled = false

    let retryMs = 5000
    let loggedErrOnce = false
    let timer: number | null = null

    const refresh = async () => {
      if (!playerId || !/^[a-zA-Z0-9_]{3,20}$/.test(playerId)) return
      try {
        const res = await Api.accountValuation(`user:${playerId}`)
        if (!canceled) {
          setCash(res.cash)
          setTotalValue(res.total_value)
          setValuationOk(true)
        }

        // success: reset retry
        retryMs = 5000
        loggedErrOnce = false
        if (timer !== null) window.clearTimeout(timer)
        timer = window.setTimeout(refresh, retryMs)
      } catch (e) {
        if (!canceled) setValuationOk(false)
        if (!loggedErrOnce) {
          loggedErrOnce = true
          console.error('Failed to fetch valuation in layout', e)
        }

        // backoff up to 60s to avoid console spam and request storms
        retryMs = Math.min(60000, Math.max(5000, retryMs * 2))
        if (timer !== null) window.clearTimeout(timer)
        timer = window.setTimeout(refresh, retryMs)
      }
    }

    refresh()
    return () => {
      canceled = true
      if (timer !== null) window.clearTimeout(timer)
    }
  }, [sess.playerId])

  const playerId = sess.playerId
  if (!playerId || !/^[a-zA-Z0-9_]{3,20}$/.test(playerId)) {
    return <Navigate to="/onboarding" replace />
  }

  return (
    <div style={{ 
      minHeight: '100vh', 
      background: 'var(--terminal-bg)', 
      color: 'var(--terminal-text)',
      display: 'flex',
      flexDirection: 'column'
    }}>
      {sess.scanlinesEnabled && <div className="scanlines" />}
      
      {/* HUD Header */}
      <header style={{ 
        padding: '0 15px', 
        height: '40px',
        borderBottom: '1px solid var(--terminal-border)',
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        background: 'var(--header-bg)',
        fontSize: '12px',
        zIndex: 100
      }}>
        <div style={{ display: 'flex', gap: '30px', alignItems: 'center' }}>
          <div style={{ fontWeight: '800', fontSize: '14px', color: '#fff' }}>
            TERMINAL_<span style={{ color: '#3b82f6' }}>IF</span>
          </div>
          {marketSession && (
            <div style={{ 
              display: 'flex', 
              alignItems: 'center', 
              gap: '12px', 
              padding: '0 12px', 
              borderLeft: '1px solid var(--terminal-border)',
              fontFamily: 'monospace',
              fontSize: '11px'
            }}>
              <div style={{ display: 'flex', flexDirection: 'column' }}>
                <span style={{ color: '#64748b', fontSize: '9px' }}>MARKET_STATUS</span>
                <span style={{ 
                  color: marketSession.phase === 'TRADING' ? 'var(--terminal-success)' : 'var(--terminal-error)',
                  fontWeight: 'bold',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '4px'
                }}>
                  <div style={{ 
                    width: '6px', height: '6px', borderRadius: '50%', 
                    background: marketSession.phase === 'TRADING' ? 'var(--terminal-success)' : 'var(--terminal-error)',
                    boxShadow: marketSession.phase === 'TRADING' ? '0 0 5px var(--terminal-success)' : 'none'
                  }} />
                  {marketSession.phase}
                </span>
              </div>
              <div style={{ display: 'flex', flexDirection: 'column' }}>
                <span style={{ color: '#64748b', fontSize: '9px' }}>GAME_DAY</span>
                <span style={{ color: '#fff' }}>D{marketSession.game_day_index}</span>
              </div>
            </div>
          )}
          <nav style={{ display: 'flex', gap: '4px' }}>
            <NavItem to="/dashboard" label="DASHBOARD" />
            <NavItem to="/news" label="INTELLIGENCE" />
            <NavItem to="/account" label="PORTFOLIO" />
          </nav>
        </div>

        <div style={{ display: 'flex', gap: '15px', alignItems: 'center' }}>
          {sess.playerId && (
            <>
              <button 
                onClick={toggleHosting}
                disabled={hostingLoading}
                className={`cyber-button ${sess.aiHosting ? 'active' : ''}`}
                style={{ 
                  fontSize: '10px', 
                  height: '28px', 
                  padding: '0 10px',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '6px',
                  borderColor: sess.aiHosting ? 'var(--terminal-success)' : 'var(--terminal-border)',
                  color: sess.aiHosting ? 'var(--terminal-success)' : '#94a3b8'
                }}
              >
                <div style={{ 
                  width: '8px', 
                  height: '8px', 
                  borderRadius: '50%', 
                  background: sess.aiHosting ? 'var(--terminal-success)' : '#475569',
                  boxShadow: sess.aiHosting ? '0 0 8px var(--terminal-success)' : 'none'
                }} />
                {sess.aiHosting ? 'AI_ACTIVE' : 'START_AI'}
              </button>

              <div style={{ display: 'flex', gap: '12px', alignItems: 'center', color: '#94a3b8' }}>
                <span>{sess.playerId}</span>
                {caste && <span style={{ color: caste.color, fontSize: '11px', fontWeight: 'bold' }}>[{caste.id}]</span>}
              </div>
              <div style={{ display: 'flex', gap: '15px', paddingLeft: '15px', borderLeft: '1px solid var(--terminal-border)' }}>
                <div style={{ display: 'flex', flexDirection: 'column' }}>
                  <span style={{ fontSize: '10px', color: '#64748b' }}>CASH</span>
                  <span style={{ fontWeight: '600', color: '#fff' }}>${typeof cash === 'number' ? cash.toLocaleString() : '--'}</span>
                </div>
                <div style={{ display: 'flex', flexDirection: 'column' }}>
                  <span style={{ fontSize: '10px', color: '#64748b' }}>EQUITY</span>
                  <span style={{ fontWeight: '600', color: '#fff' }}>${typeof totalValue === 'number' ? totalValue.toLocaleString() : '--'}</span>
                </div>
                {!valuationOk && <span style={{ color: 'var(--terminal-error)', alignSelf: 'center' }}>[SYNC_ERR]</span>}
              </div>
            </>
          )}
          
          <button onClick={() => setSystemMenuOpen(true)} className="cyber-button" style={{ fontSize: '11px', height: '28px', padding: '0 12px' }}>
            SYSTEM
          </button>
        </div>
      </header>

      {!sess.playerId && (
        <div style={{ 
          margin: '20px', 
          padding: '10px', 
          border: '1px solid var(--terminal-warn)', 
          color: 'var(--terminal-warn)',
          textAlign: 'center'
        }}>
          SYSTEM_ACCESS_DENIED: IDENTITY_NOT_FOUND. PLEASE <Link to="/onboarding" style={{ color: 'inherit', textDecoration: 'underline' }}>PROCEED_TO_ONBOARDING</Link>
        </div>
      )}

      <main style={{ flex: 1, padding: '5px', overflow: 'hidden' }}>
        <Outlet />
      </main>

      {sess.playerId && (
        <SettingsModal actorId={`user:${sess.playerId}`} open={settingsOpen} onClose={() => setSettingsOpen(false)} />
      )}

      {/* System Menu Overlay */}
      {systemMenuOpen && (
        <div style={{
          position: 'fixed',
          top: 0, left: 0, right: 0, bottom: 0,
          backgroundColor: 'rgba(0,0,0,0.85)',
          zIndex: 200,
          display: 'flex',
          justifyContent: 'center',
          alignItems: 'center',
          backdropFilter: 'blur(4px)'
        }}>
          <div className="cyber-card" style={{ width: '400px', padding: '24px', alignItems: 'center' }}>
            <h2 style={{ color: 'var(--terminal-info)', margin: '0 0 24px 0', fontSize: '18px', letterSpacing: '2px' }}>SYSTEM_MENU</h2>
            
            <div style={{ display: 'flex', flexDirection: 'column', gap: '16px', width: '100%' }}>
              <button 
                onClick={() => {
                  setSystemMenuOpen(false)
                  setSettingsOpen(true)
                }} 
                className="cyber-button"
                style={{ height: '48px', fontSize: '14px', letterSpacing: '1px' }}
              >
                CONFIGURATION
              </button>
              
              <button 
                onClick={() => {
                  setSystemMenuOpen(false)
                }} 
                className="cyber-button"
                style={{ height: '48px', fontSize: '14px', letterSpacing: '1px' }}
              >
                RESUME_SIMULATION
              </button>

              <div style={{ height: '1px', background: 'var(--terminal-border)', margin: '8px 0' }} />

              {!disconnectConfirm ? (
                <button 
                  onClick={() => setDisconnectConfirm(true)} 
                  className="cyber-button"
                  style={{ height: '48px', fontSize: '14px', letterSpacing: '1px', color: 'var(--terminal-warn)', borderColor: 'var(--terminal-warn)', background: 'transparent' }}
                >
                  DISCONNECT
                </button>
              ) : (
                <div style={{ display: 'flex', gap: '8px' }}>
                  <button 
                    onClick={handleReAuth} 
                    className="cyber-button"
                    style={{ flex: 1, height: '48px', fontSize: '14px', letterSpacing: '1px', background: 'var(--terminal-error)', borderColor: 'var(--terminal-error)', color: '#fff', fontWeight: 'bold' }}
                  >
                    CONFIRM_EXIT
                  </button>
                  <button 
                    onClick={() => setDisconnectConfirm(false)} 
                    className="cyber-button"
                    style={{ flex: 1, height: '48px', fontSize: '14px', letterSpacing: '1px' }}
                  >
                    CANCEL
                  </button>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Terminal Footer Status Bar */}
      <footer style={{ 
        padding: '0 15px', 
        height: '28px',
        borderTop: '1px solid var(--terminal-border)', 
        fontSize: '10px',
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        color: '#64748b',
        background: 'var(--header-bg)'
      }}>
        <div style={{ flex: 1, display: 'flex', gap: '15px' }}>
          <span>STATUS: ONLINE</span>
          <span>LATENCY: 24ms</span>
        </div>
        <div style={{ flex: 2, overflow: 'hidden' }}>
          <NewsTicker />
        </div>
        <div style={{ flex: 1, textAlign: 'right' }}>{new Date().toLocaleTimeString()} // IF_CORE_v4.2</div>
      </footer>
    </div>
  )
}
