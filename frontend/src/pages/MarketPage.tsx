import { useEffect, useMemo, useState } from 'react'
import { Api, ApiError, type MarketCandlesResponse, type MarketQuoteResponse, type MarketSeriesResponse } from '../api'
import { useAppSession } from '../app/context'

export default function MarketPage() {
  const { symbol } = useAppSession()
  const [err, setErr] = useState<string>('')
  const [quote, setQuote] = useState<MarketQuoteResponse | null>(null)
  const [series, setSeries] = useState<MarketSeriesResponse | null>(null)
  const [candles, setCandles] = useState<MarketCandlesResponse | null>(null)

  const [autoRefresh, setAutoRefresh] = useState<boolean>(true)
  const [refreshSeconds, setRefreshSeconds] = useState<number>(3)

  const [seriesLimit, setSeriesLimit] = useState<number>(200)
  const [candleInterval, setCandleInterval] = useState<number>(60)
  const [candleLimit, setCandleLimit] = useState<number>(120)

  async function refresh(): Promise<void> {
    setErr('')
    try {
      const [q, s, c] = await Promise.all([
        Api.marketQuote(symbol),
        Api.marketSeries(symbol, seriesLimit),
        Api.marketCandles(symbol, candleInterval, candleLimit),
      ])
      setQuote(q)
      setSeries(s)
      setCandles(c)
    } catch (e) {
      if (e instanceof ApiError) setErr(`${e.status}: ${e.message}`)
      else setErr(e instanceof Error ? e.message : String(e))
    }
  }

  useEffect(() => {
    refresh()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [symbol])

  const refreshMs = useMemo(() => Math.max(1, Number(refreshSeconds)) * 1000, [refreshSeconds])

  useEffect(() => {
    if (!autoRefresh) return
    const t = window.setInterval(() => {
      refresh()
    }, refreshMs)
    return () => window.clearInterval(t)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoRefresh, refreshMs, symbol])

  const last = quote?.last_price
  const prev = quote?.prev_price
  const changePct = quote?.change_pct

  const changeText =
    changePct === null || changePct === undefined
      ? 'N/A'
      : `${(changePct * 100).toFixed(2)}%`

  const changeColor =
    changePct === null || changePct === undefined
      ? '#666'
      : changePct >= 0
        ? 'green'
        : 'crimson'

  return (
    <div style={{ display: 'grid', gap: 12 }}>
      <div className="card" style={{ textAlign: 'left' }}>
        <h3 style={{ marginTop: 0 }}>Quote</h3>
        {err ? <div style={{ color: 'crimson' }}>{err}</div> : null}

        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'center', marginBottom: 10 }}>
          <button onClick={refresh}>Refresh</button>
          <label style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
            <input type="checkbox" checked={autoRefresh} onChange={(e) => setAutoRefresh(e.target.checked)} />
            Auto
          </label>
          <label style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
            every(s)
            <input
              type="number"
              value={refreshSeconds}
              onChange={(e) => setRefreshSeconds(Number(e.target.value))}
              min={1}
              style={{ width: 80 }}
            />
          </label>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, minmax(0, 1fr))', gap: 10 }}>
          <div style={{ padding: 10, border: '1px solid #eee', borderRadius: 10 }}>
            <div style={{ color: '#666' }}>Symbol</div>
            <div style={{ fontSize: 18, fontWeight: 600 }}>{quote?.symbol ?? symbol}</div>
          </div>
          <div style={{ padding: 10, border: '1px solid #eee', borderRadius: 10 }}>
            <div style={{ color: '#666' }}>Last</div>
            <div style={{ fontSize: 18, fontWeight: 600 }}>{last ?? 'N/A'}</div>
          </div>
          <div style={{ padding: 10, border: '1px solid #eee', borderRadius: 10 }}>
            <div style={{ color: '#666' }}>Prev</div>
            <div style={{ fontSize: 18, fontWeight: 600 }}>{prev ?? 'N/A'}</div>
          </div>
          <div style={{ padding: 10, border: '1px solid #eee', borderRadius: 10 }}>
            <div style={{ color: '#666' }}>Change</div>
            <div style={{ fontSize: 18, fontWeight: 700, color: changeColor }}>{changeText}</div>
          </div>
        </div>

        <details style={{ marginTop: 10 }}>
          <summary>Raw JSON</summary>
          <pre style={{ whiteSpace: 'pre-wrap' }}>{quote ? JSON.stringify(quote, null, 2) : 'N/A'}</pre>
        </details>
      </div>

      <div className="card" style={{ textAlign: 'left' }}>
        <h3 style={{ marginTop: 0 }}>Series</h3>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
          <label>
            Limit{' '}
            <input type="number" value={seriesLimit} onChange={(e) => setSeriesLimit(Number(e.target.value))} />
          </label>
          <button onClick={refresh}>Reload</button>
        </div>
        <pre style={{ whiteSpace: 'pre-wrap' }}>{series ? JSON.stringify(series, null, 2) : 'N/A'}</pre>
      </div>

      <div className="card" style={{ textAlign: 'left' }}>
        <h3 style={{ marginTop: 0 }}>Candles</h3>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
          <label>
            Interval(s){' '}
            <input
              type="number"
              value={candleInterval}
              onChange={(e) => setCandleInterval(Number(e.target.value))}
            />
          </label>
          <label>
            Limit{' '}
            <input type="number" value={candleLimit} onChange={(e) => setCandleLimit(Number(e.target.value))} />
          </label>
          <button onClick={refresh}>Reload</button>
        </div>

        {candles?.candles?.length ? (
          <div style={{ overflow: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead>
                <tr>
                  <th style={{ textAlign: 'left', borderBottom: '1px solid #ddd', padding: 6 }}>t</th>
                  <th style={{ textAlign: 'right', borderBottom: '1px solid #ddd', padding: 6 }}>O</th>
                  <th style={{ textAlign: 'right', borderBottom: '1px solid #ddd', padding: 6 }}>H</th>
                  <th style={{ textAlign: 'right', borderBottom: '1px solid #ddd', padding: 6 }}>L</th>
                  <th style={{ textAlign: 'right', borderBottom: '1px solid #ddd', padding: 6 }}>C</th>
                  <th style={{ textAlign: 'right', borderBottom: '1px solid #ddd', padding: 6 }}>V</th>
                </tr>
              </thead>
              <tbody>
                {candles.candles.map((c) => (
                  <tr key={c.bucket_start}>
                    <td style={{ padding: 6, borderBottom: '1px solid #eee' }}>{c.bucket_start}</td>
                    <td style={{ padding: 6, textAlign: 'right', borderBottom: '1px solid #eee' }}>{c.open}</td>
                    <td style={{ padding: 6, textAlign: 'right', borderBottom: '1px solid #eee' }}>{c.high}</td>
                    <td style={{ padding: 6, textAlign: 'right', borderBottom: '1px solid #eee' }}>{c.low}</td>
                    <td style={{ padding: 6, textAlign: 'right', borderBottom: '1px solid #eee' }}>{c.close}</td>
                    <td style={{ padding: 6, textAlign: 'right', borderBottom: '1px solid #eee' }}>{c.volume}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <pre style={{ whiteSpace: 'pre-wrap' }}>{candles ? JSON.stringify(candles, null, 2) : 'N/A'}</pre>
        )}
      </div>
    </div>
  )
}
