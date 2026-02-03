import { Link, Outlet, useLocation } from 'react-router-dom'
import { useAppSession } from './context'
import { useEffect, useMemo, useState } from 'react'
import { Api } from '../api'

const CASTES = [
  { id: 'ELITE', label: '精英阶层 (Elite)', color: '#ff4d4f', weight: 0.1, desc: '掌控巨量原始资本，拥有信息溯源权' },
  { id: 'MIDDLE', label: '中产阶层 (Middle)', color: '#1890ff', weight: 0.3, desc: '拥有稳健的起步资金' },
  { id: 'WORKING', label: '工薪阶层 (Working)', color: '#52c41a', weight: 0.6, desc: '白手起家，依赖社交网络获取信息' },
]

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
  const [cash, setCash] = useState<number | null>(null)
  const [totalValue, setTotalValue] = useState<number | null>(null)
  const [valuationOk, setValuationOk] = useState<boolean>(true)

  const caste = useMemo(() => {
    return CASTES.find(c => c.id === sess.casteId)
  }, [sess.casteId])

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

  return (
    <div style={{ 
      minHeight: '100vh', 
      background: 'var(--terminal-bg)', 
      color: 'var(--terminal-text)',
      display: 'flex',
      flexDirection: 'column'
    }}>
      <div className="scanlines" />
      
      {/* HUD Header */}
      <header style={{ 
        padding: '0 20px', 
        height: '48px',
        borderBottom: '1px solid var(--terminal-border)',
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        background: 'var(--header-bg)',
        fontSize: '13px',
        zIndex: 100
      }}>
        <div style={{ display: 'flex', gap: '30px', alignItems: 'center' }}>
          <div style={{ fontWeight: '800', fontSize: '14px', color: '#fff' }}>
            TERMINAL_<span style={{ color: '#3b82f6' }}>IF</span>
          </div>
          <nav style={{ display: 'flex', gap: '4px' }}>
            <NavItem to="/dashboard" label="DASHBOARD" />
            <NavItem to="/news" label="INTELLIGENCE" />
            <NavItem to="/contracts" label="CONTRACTS" />
            <NavItem to="/account" label="PORTFOLIO" />
          </nav>
        </div>

        <div style={{ display: 'flex', gap: '20px', alignItems: 'center' }}>
          {sess.playerId && (
            <>
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
          
          <button onClick={() => window.location.href='/onboarding'} className="cyber-button" style={{ fontSize: '11px', height: '28px', padding: '0 12px' }}>
            RE_AUTH
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

      <main style={{ flex: 1, padding: '20px', overflow: 'auto' }}>
        <Outlet />
      </main>

      {/* Terminal Footer Status Bar */}
      <footer style={{ 
        padding: '0 20px', 
        height: '32px',
        borderTop: '1px solid var(--terminal-border)', 
        fontSize: '11px',
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
