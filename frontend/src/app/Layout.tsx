import { Link, Outlet, useLocation } from 'react-router-dom'
import { useAppSession } from './context'

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

  return (
    <div style={{ maxWidth: 1100, margin: '0 auto', padding: 16 }}>
      <header style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <h2 style={{ margin: 0 }}>Information Frontier</h2>
          <nav style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
            <NavItem to="/market" label="Market" />
            <NavItem to="/trade" label="Trade" />
            <NavItem to="/account" label="Account" />
            <NavItem to="/news" label="News" />
            <NavItem to="/chat" label="Chat" />
          </nav>
        </div>

        <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
          <label style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
            <span>Player</span>
            <input value={sess.playerId} onChange={(e) => sess.setPlayerId(e.target.value)} />
          </label>
          <label style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
            <span>Symbol</span>
            <input value={sess.symbol} onChange={(e) => sess.setSymbol(e.target.value)} />
          </label>
        </div>
      </header>

      <main style={{ marginTop: 16 }}>
        <Outlet />
      </main>
    </div>
  )
}
