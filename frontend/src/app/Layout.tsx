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
        fontSize: '11px',
        padding: '4px 10px',
        textDecoration: 'none',
        background: active ? 'var(--terminal-border)' : 'transparent',
        color: active ? '#000' : 'var(--terminal-text)',
        boxShadow: active ? '0 0 10px var(--terminal-border)' : 'none'
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
        padding: '10px 20px', 
        borderBottom: '1px solid var(--terminal-border)',
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        background: 'rgba(0, 255, 65, 0.05)',
        fontSize: '12px'
      }}>
        <div style={{ display: 'flex', gap: 20, alignItems: 'center' }}>
          <div style={{ fontWeight: 'bold', fontSize: '16px', letterSpacing: '2px' }}>
            IF_TERMINAL_v2.0
          </div>
          <div style={{ display: 'flex', gap: 15 }}>
            <NavItem to="/dashboard" label="DASHBOARD" />
            <NavItem to="/market" label="MARKET" />
            <NavItem to="/trade" label="TRADE" />
            <NavItem to="/news" label="NEWS" />
            <NavItem to="/chat" label="CHAT" />
            <NavItem to="/account" label="ACCOUNT" />
            <NavItem to="/contracts" label="CONTRACTS" />
            <NavItem to="/hosting" label="HOSTING" />
          </div>
        </div>

        <div style={{ display: 'flex', gap: 20, alignItems: 'center' }}>
          {sess.playerId && (
            <>
              <div style={{ display: 'flex', gap: 10 }}>
                <span>ID: <code style={{ color: '#fff' }}>{sess.playerId}</code></span>
                {caste && <span style={{ color: caste.color }}>[{caste.id}]</span>}
              </div>
              <div style={{ display: 'flex', gap: 15, padding: '2px 10px', border: '1px solid var(--terminal-border)', borderRadius: '4px' }}>
                <span>CASH: <strong style={{ color: '#fff' }}>${typeof cash === 'number' ? cash.toLocaleString() : '--'}</strong></span>
                <span>EQUITY: <strong style={{ color: '#fff' }}>${typeof totalValue === 'number' ? totalValue.toLocaleString() : '--'}</strong></span>
                {!valuationOk && <span style={{ color: 'var(--terminal-error)' }}>[SYNC_ERR]</span>}
              </div>
            </>
          )}
          
          <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
            <span>SYM:</span>
            <input 
              className="cyber-input"
              value={sess.symbol} 
              onChange={(e) => sess.setSymbol(e.target.value.toUpperCase())}
              style={{ width: 80, fontSize: '12px', padding: '2px 4px' }}
            />
          </div>

          <Link to="/onboarding" className="cyber-button" style={{ fontSize: '10px', padding: '2px 8px' }}>
            RE_AUTH
          </Link>
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
        padding: '4px 20px', 
        borderTop: '1px solid var(--terminal-border)', 
        fontSize: '10px',
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        color: 'rgba(0, 255, 65, 0.5)',
        background: 'rgba(0, 0, 0, 0.5)'
      }}>
        <div style={{ flex: 1 }}>NETWORK_STATUS: ENCRYPTED // CONNECTION: STABLE</div>
        <div style={{ flex: 2, overflow: 'hidden' }}>
          <NewsTicker />
        </div>
        <div style={{ flex: 1, textAlign: 'right' }}>{new Date().toISOString()} // IF_CORE_ACTIVE</div>
      </footer>
    </div>
  )
}
