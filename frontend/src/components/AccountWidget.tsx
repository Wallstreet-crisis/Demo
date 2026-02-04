import { useEffect, useState, useCallback, useMemo } from 'react'
import { Api, ApiError, WsClient, type AccountValuationResponse, type PlayerAccountResponse } from '../api'
import { useAppSession } from '../app/context'
import { CASTES } from '../app/constants'
import CyberWidget from './CyberWidget'

export default function AccountWidget({ isFocused }: { isFocused?: boolean }) {
  void isFocused
  const { playerId } = useAppSession()
  const [err, setErr] = useState<string>('')
  const [snap, setSnap] = useState<PlayerAccountResponse | null>(null)
  const [val, setVal] = useState<AccountValuationResponse | null>(null)

  const ws = useMemo(() => new WsClient(), [])

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
    return () => {
      active = false
    }
  }, [refresh])

  useEffect(() => {
    if (!playerId) return
    ws.connect('events', (data: unknown) => {
      const ev = data as { event_type?: string; payload?: { buy_account_id?: string; sell_account_id?: string } }
      if (ev?.event_type === 'TRADE_EXECUTED') {
        const myAcc = `user:${playerId}`
        if (ev.payload?.buy_account_id === myAcc || ev.payload?.sell_account_id === myAcc) {
          // 如果成交涉及当前玩家，立即刷新资产
          refresh()
        }
      }
    })
    return () => ws.close()
  }, [ws, playerId, refresh])

  useEffect(() => {
    const t = setInterval(refresh, 15000) // 轮询频率降低，主要依靠实时推送
    return () => clearInterval(t)
  }, [refresh])

  const cash = val?.cash ?? snap?.cash ?? 0
  const equityValue = val?.equity_value ?? 0
  const totalValue = val?.total_value ?? 0

  const playerCaste = useMemo(() => {
    if (!snap?.caste_id) return null;
    return CASTES.find(c => c.id === snap.caste_id);
  }, [snap]);

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
      subtitle="REALTIME_PORTFOLIO_TRACKER"
      actions={<button className="cyber-button" style={{ fontSize: '11px', padding: '2px 8px' }} onClick={refresh}>REFRESH</button>}
    >
      {err && <div style={{ color: 'var(--terminal-error)', fontSize: '12px', marginBottom: '10px', background: 'rgba(239, 68, 68, 0.1)', padding: '8px', borderLeft: '3px solid var(--terminal-error)' }}>[ERR]: {err}</div>}
      
      {playerCaste && (
        <div style={{ 
          marginBottom: '15px', 
          padding: '8px 12px', 
          background: `${playerCaste.color}15`, 
          borderLeft: `3px solid ${playerCaste.color}`,
          borderRadius: '2px'
        }}>
          <div style={{ fontSize: '9px', color: playerCaste.color, fontWeight: 'bold', letterSpacing: '1px' }}>SOCIAL_CLASS_PROFILE</div>
          <div style={{ fontSize: '14px', fontWeight: 'bold', color: '#fff', marginTop: '2px' }}>{playerCaste.label}</div>
          <div style={{ fontSize: '9px', color: '#94a3b8', marginTop: '4px', fontStyle: 'italic' }}>{playerCaste.desc}</div>
        </div>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px', marginBottom: '15px' }}>
        <div style={{ padding: '10px', border: '1px solid var(--terminal-border)', background: 'rgba(255,255,255,0.02)', borderRadius: '4px' }}>
          <div style={{ fontSize: '10px', color: '#64748b', marginBottom: '4px' }}>CASH_LIQUID</div>
          <div style={{ fontSize: '18px', fontWeight: '700', color: '#fff' }}>${cash.toLocaleString()}</div>
        </div>
        <div style={{ padding: '10px', border: '1px solid var(--terminal-border)', background: 'rgba(255,255,255,0.02)', borderRadius: '4px' }}>
          <div style={{ fontSize: '10px', color: '#64748b', marginBottom: '4px' }}>EQUITY_VALUE</div>
          <div style={{ fontSize: '18px', fontWeight: '700', color: '#fff' }}>${equityValue.toLocaleString()}</div>
        </div>
      </div>

      <div style={{ fontSize: '11px', fontWeight: '600', marginBottom: '8px', color: '#94a3b8' }}>PORTFOLIO_POSITIONS</div>
      <div style={{ border: '1px solid var(--terminal-border)', borderRadius: '4px', overflow: 'hidden' }}>
        <div style={{ maxHeight: '180px', overflow: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px' }}>
            <thead style={{ position: 'sticky', top: 0, background: 'var(--header-bg)', color: '#64748b', borderBottom: '1px solid var(--terminal-border)' }}>
              <tr>
                <th style={{ textAlign: 'left', padding: '8px' }}>SYM</th>
                <th style={{ textAlign: 'right', padding: '8px' }}>QTY</th>
                <th style={{ textAlign: 'right', padding: '8px' }}>VALUE</th>
              </tr>
            </thead>
            <tbody>
              {(isFocused ? positionItems : positionItems.slice(0, 3)).map((p) => (
                <tr key={p.symbol} style={{ borderBottom: '1px solid rgba(51, 65, 85, 0.3)', transition: 'background 0.1s' }}>
                  <td style={{ padding: '8px', fontWeight: '600' }}>{p.symbol}</td>
                  <td style={{ padding: '8px', textAlign: 'right', fontFamily: 'monospace' }}>{p.qty.toFixed(2)}</td>
                  <td style={{ padding: '8px', textAlign: 'right', fontFamily: 'monospace', color: '#fff' }}>
                    {p.mktValue === null ? 'N/A' : `$${p.mktValue.toFixed(2)}`}
                  </td>
                </tr>
              ))}
              {positionItems.length === 0 && (
                <tr>
                  <td colSpan={3} style={{ padding: '24px', textAlign: 'center', opacity: 0.4, fontSize: '11px' }}>NO_ACTIVE_POSITIONS</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      <div style={{ 
        marginTop: 'auto',
        paddingTop: '15px'
      }}>
        <div style={{ 
          padding: '12px', 
          borderRadius: '4px',
          background: 'linear-gradient(to right, rgba(59, 130, 246, 0.1), transparent)',
          border: '1px solid rgba(59, 130, 246, 0.3)',
          textAlign: 'right'
        }}>
          <div style={{ fontSize: '10px', color: '#3b82f6', fontWeight: '700', marginBottom: '4px' }}>TOTAL_NET_WORTH</div>
          <div style={{ fontSize: '24px', fontWeight: '800', color: '#fff', fontFamily: 'monospace' }}>
            ${totalValue.toLocaleString()}
          </div>
        </div>
      </div>
    </CyberWidget>
  )
}
