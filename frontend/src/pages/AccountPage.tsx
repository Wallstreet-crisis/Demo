import { useEffect, useState } from 'react'
import { Api, ApiError, type AccountValuationResponse, type PlayerAccountResponse } from '../api'
import { useAppSession } from '../app/context'

export default function AccountPage() {
  const { playerId } = useAppSession()
  const [err, setErr] = useState<string>('')
  const [loading, setLoading] = useState(true)
  const [snap, setSnap] = useState<PlayerAccountResponse | null>(null)
  const [val, setVal] = useState<AccountValuationResponse | null>(null)

  async function refresh(): Promise<void> {
    setErr('')
    setLoading(true)
    try {
      const s = await Api.playerAccount(playerId)
      setSnap(s)
      const v = await Api.accountValuation(`user:${playerId}`, 1.0)
      setVal(v)
    } catch (e) {
      if (e instanceof ApiError) setErr(`${e.status}: ${e.message}`)
      else setErr(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    refresh()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [playerId])

  const cash = val?.cash ?? snap?.cash ?? null
  const equityValue = val?.equity_value ?? null
  const totalValue = val?.total_value ?? null

  const positions = snap?.positions ?? {}
  const positionItems = Object.entries(positions)
    .map(([symbol, qty]) => {
      const last = (val?.prices ?? {})[symbol]
      const mktValue = last === null || last === undefined ? null : Number(last) * Number(qty)
      return { symbol, qty: Number(qty), last: last === undefined ? null : last, mktValue }
    })
    .filter((x) => Math.abs(x.qty) > 1e-9)
    .sort((a, b) => b.qty - a.qty)

  const positionCount = positionItems.length

  return (
    <div style={{ display: 'grid', gap: 12 }}>
      <div className="card" style={{ textAlign: 'left' }}>
        <h3 style={{ marginTop: 0 }}>账户资产</h3>
        {err ? <div style={{ color: 'crimson' }}>{err}</div> : null}
        <button onClick={refresh} disabled={loading}>{loading ? '刷新中...' : 'Refresh'}</button>

        {loading && !snap ? (
          <div style={{ padding: '20px 0', color: '#999' }}>加载中...</div>
        ) : (
          <>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, minmax(0, 1fr))', gap: 10, marginTop: 10 }}>
              <div style={{ padding: 10, border: '1px solid #eee', borderRadius: 10 }}>
                <div style={{ color: '#666' }}>玩家</div>
                <div style={{ fontSize: 18, fontWeight: 600 }}>{playerId}</div>
              </div>
              <div style={{ padding: 10, border: '1px solid #eee', borderRadius: 10 }}>
                <div style={{ color: '#666' }}>现金</div>
                <div style={{ fontSize: 18, fontWeight: 700 }}>{cash?.toLocaleString() ?? '--'}</div>
              </div>
              <div style={{ padding: 10, border: '1px solid #eee', borderRadius: 10 }}>
                <div style={{ color: '#666' }}>股票市值</div>
                <div style={{ fontSize: 18, fontWeight: 700 }}>{equityValue?.toLocaleString() ?? '--'}</div>
              </div>
              <div style={{ padding: 10, border: '1px solid #eee', borderRadius: 10 }}>
                <div style={{ color: '#666' }}>总资产</div>
                <div style={{ fontSize: 18, fontWeight: 700 }}>{totalValue?.toLocaleString() ?? '--'}</div>
              </div>
            </div>

            <div style={{ marginTop: 10, color: '#666' }}>持仓数：{positionCount}</div>
          </>
        )}
      </div>

      <div className="card" style={{ textAlign: 'left' }}>
        <h3 style={{ marginTop: 0 }}>持仓明细</h3>

        {loading && !snap ? (
          <div style={{ padding: 20, color: '#999' }}>加载中...</div>
        ) : positionItems.length ? (
          <div style={{ overflow: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead>
                <tr>
                  <th style={{ textAlign: 'left', borderBottom: '1px solid #ddd', padding: 6 }}>Symbol</th>
                  <th style={{ textAlign: 'right', borderBottom: '1px solid #ddd', padding: 6 }}>Qty</th>
                  <th style={{ textAlign: 'right', borderBottom: '1px solid #ddd', padding: 6 }}>Last</th>
                  <th style={{ textAlign: 'right', borderBottom: '1px solid #ddd', padding: 6 }}>Value</th>
                </tr>
              </thead>
              <tbody>
                {positionItems.map((p) => (
                  <tr key={p.symbol}>
                    <td style={{ padding: 6, borderBottom: '1px solid #eee' }}>{p.symbol}</td>
                    <td style={{ padding: 6, textAlign: 'right', borderBottom: '1px solid #eee' }}>{p.qty}</td>
                    <td style={{ padding: 6, textAlign: 'right', borderBottom: '1px solid #eee' }}>{p.last ?? 'N/A'}</td>
                    <td style={{ padding: 6, textAlign: 'right', borderBottom: '1px solid #eee' }}>
                      {p.mktValue === null ? 'N/A' : p.mktValue}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div style={{ color: '#666' }}>暂无持仓。</div>
        )}

        <details style={{ marginTop: 12 }}>
          <summary>Raw JSON</summary>
          <pre style={{ whiteSpace: 'pre-wrap' }}>{JSON.stringify({ snap, valuation: val }, null, 2)}</pre>
        </details>
      </div>
    </div>
  )
}
