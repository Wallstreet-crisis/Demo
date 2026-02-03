import { useEffect, useState, useCallback } from 'react'
import { Api, ApiError, type AccountValuationResponse, type PlayerAccountResponse } from '../api'
import { useAppSession } from '../app/context'
import CyberWidget from './CyberWidget'

export default function AccountWidget() {
  const { playerId } = useAppSession()
  const [err, setErr] = useState<string>('')
  const [snap, setSnap] = useState<PlayerAccountResponse | null>(null)
  const [val, setVal] = useState<AccountValuationResponse | null>(null)

  const refresh = useCallback(async () => {
    if (!playerId) return
    setErr('')
    try {
      const s = await Api.playerAccount(playerId)
      setSnap(s)
      const v = await Api.accountValuation(`user:${playerId}`, 1.0)
      setVal(v)
    } catch (e) {
      if (e instanceof ApiError) setErr(`${e.status}: ${e.message}`)
      else setErr(e instanceof Error ? e.message : String(e))
    }
  }, [playerId])

  useEffect(() => {
    let active = true
    const doRefresh = async () => {
      if (active) await refresh()
    }
    doRefresh()
    const t = setInterval(refresh, 5000)
    return () => {
      active = false
      clearInterval(t)
    }
  }, [refresh])

  const cash = val?.cash ?? snap?.cash ?? 0
  const equityValue = val?.equity_value ?? 0
  const totalValue = val?.total_value ?? 0

  const positions = snap?.positions ?? {}
  const positionItems = Object.entries(positions)
    .map(([symbol, qty]) => {
      const last = (val?.prices ?? {})[symbol]
      const mktValue = (last === null || last === undefined) ? null : Number(last) * Number(qty)
      return { symbol, qty: Number(qty), last: last === undefined ? null : last, mktValue }
    })
    .filter((x) => Math.abs(x.qty) > 1e-9)
    .sort((a, b) => (b.mktValue ?? 0) - (a.mktValue ?? 0))

  return (
    <CyberWidget 
      title="ASSET_MANAGEMENT" 
      subtitle="LEDGER_SNAPSHOT_v4"
      actions={<button className="cyber-button" style={{ fontSize: '9px', padding: '2px 6px' }} onClick={refresh}>RESCAN</button>}
    >
      {err && <div style={{ color: 'var(--terminal-error)', fontSize: '11px', marginBottom: 10 }}>[ERR]: {err}</div>}
      
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, marginBottom: 15 }}>
        <div style={{ padding: '8px', border: '1px solid #222', background: 'rgba(255,255,255,0.02)' }}>
          <div style={{ fontSize: '9px', opacity: 0.5 }}>CASH_LIQUID</div>
          <div style={{ fontSize: '16px', fontWeight: 'bold' }}>${cash.toLocaleString()}</div>
        </div>
        <div style={{ padding: '8px', border: '1px solid #222', background: 'rgba(255,255,255,0.02)' }}>
          <div style={{ fontSize: '9px', opacity: 0.5 }}>EQUITY_VALUATION</div>
          <div style={{ fontSize: '16px', fontWeight: 'bold' }}>${equityValue.toLocaleString()}</div>
        </div>
      </div>

      <div style={{ fontSize: '10px', marginBottom: 5, opacity: 0.7 }}>PORTFOLIO_POSITIONS</div>
      <div style={{ border: '1px solid #222', maxHeight: '200px', overflow: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '10px' }}>
          <thead style={{ position: 'sticky', top: 0, background: '#000', borderBottom: '1px solid #333' }}>
            <tr>
              <th style={{ textAlign: 'left', padding: '4px' }}>SYM</th>
              <th style={{ textAlign: 'right', padding: '4px' }}>QTY</th>
              <th style={{ textAlign: 'right', padding: '4px' }}>MKT_VAL</th>
            </tr>
          </thead>
          <tbody>
            {positionItems.map((p) => (
              <tr key={p.symbol} style={{ borderBottom: '1px solid #111' }}>
                <td style={{ padding: '4px' }}>{p.symbol}</td>
                <td style={{ padding: '4px', textAlign: 'right' }}>{p.qty.toFixed(2)}</td>
                <td style={{ padding: '4px', textAlign: 'right' }}>
                  {p.mktValue === null ? 'N/A' : `$${p.mktValue.toFixed(2)}`}
                </td>
              </tr>
            ))}
            {positionItems.length === 0 && (
              <tr>
                <td colSpan={3} style={{ padding: '20px', textAlign: 'center', opacity: 0.3 }}>EMPTY_INVENTORY</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <div style={{ 
        marginTop: '15px', 
        padding: '10px', 
        border: '1px solid var(--terminal-border)', 
        background: 'rgba(0, 255, 65, 0.05)',
        textAlign: 'right'
      }}>
        <div style={{ fontSize: '9px', opacity: 0.6 }}>TOTAL_NET_WORTH</div>
        <div style={{ fontSize: '24px', fontWeight: 'bold', textShadow: '0 0 10px var(--terminal-border)' }}>
          ${totalValue.toLocaleString()}
        </div>
      </div>
    </CyberWidget>
  )
}
