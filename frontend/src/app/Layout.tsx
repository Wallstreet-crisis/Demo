import { Link, Outlet, useLocation } from 'react-router-dom'
import { useAppSession } from './context'
import { useEffect, useState } from 'react'
import { Api } from '../api'

function NavItem(props: { to: string; label: string }) {
  const loc = useLocation()
  const active = loc.pathname === props.to
  return (
    <Link
      to={props.to}
      style={{
        padding: '6px 10px',
        borderRadius: 8,
        textDecoration: 'none',
        color: active ? '#fff' : '#333',
        background: active ? '#646cff' : 'transparent',
      }}
    >
      {props.label}
    </Link>
  )
}

export default function Layout() {
  const sess = useAppSession()
  const [cash, setCash] = useState<number | null>(null)
  const [totalValue, setTotalValue] = useState<number | null>(null)

  const [valuationOk, setValuationOk] = useState<boolean>(true)

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
    <div style={{ maxWidth: 1100, margin: '0 auto', padding: 16 }}>
      {!sess.playerId ? (
        <div
          style={{
            padding: 12,
            background: '#fffbe6',
            border: '1px solid #ffe58f',
            borderRadius: 8,
            marginBottom: 12,
            textAlign: 'left',
          }}
        >
          <strong>未初始化玩家。</strong> 请先前往 <Link to="/onboarding">/onboarding</Link> 创建或选择玩家。
        </div>
      ) : null}

      <header style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <h2 style={{ margin: 0 }}>Information Frontier</h2>
          <nav style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
            <NavItem to="/market" label="Market" />
            <NavItem to="/trade" label="Trade" />
            <NavItem to="/account" label="Account" />
            <NavItem to="/news" label="News" />
            <NavItem to="/chat" label="Chat" />
            <NavItem to="/contracts" label="Contracts" />
            <NavItem to="/hosting" label="Hosting" />
          </nav>
        </div>

        <div style={{ display: 'flex', gap: 15, alignItems: 'center', flexWrap: 'wrap' }}>
          {sess.playerId && (
            <div style={{ display: 'flex', gap: 12, padding: '4px 12px', background: '#f0f2f5', borderRadius: 20, fontSize: 14 }}>
              <span>💰 现金: <strong style={{ color: '#52c41a' }}>{typeof cash === 'number' ? cash.toLocaleString() : '--'}</strong></span>
              <span>📊 总资产: <strong style={{ color: '#1890ff' }}>{typeof totalValue === 'number' ? totalValue.toLocaleString() : '--'}</strong></span>
              {!valuationOk && <span style={{ color: '#f5222d', fontSize: 12 }}>估值连接异常</span>}
            </div>
          )}
          <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
            <span>Player</span>
            <code>{sess.playerId || '(none)'}</code>
            <Link
              to="/onboarding"
              style={{
                padding: '4px 8px',
                borderRadius: 6,
                fontSize: 12,
                textDecoration: 'none',
                color: '#666',
                border: '1px solid #ddd',
                background: '#fff',
              }}
            >
              切换
            </Link>
          </div>
          <label style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
            <span>Symbol</span>
            <input 
              value={sess.symbol} 
              onChange={(e) => sess.setSymbol(e.target.value)}
              style={{ width: 100, padding: '2px 6px', borderRadius: 4, border: '1px solid #ddd' }}
            />
          </label>
        </div>
      </header>

      <main style={{ marginTop: 16 }}>
        <Outlet />
      </main>
    </div>
  )
}
