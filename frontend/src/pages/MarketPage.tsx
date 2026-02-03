import { useEffect, useState } from 'react'
import { Api, ApiError, type MarketCandlesResponse, type MarketQuoteResponse, type MarketSeriesResponse } from '../api'
import { useAppSession } from '../app/context'

export default function MarketPage() {
  const { symbol } = useAppSession()
  const [err, setErr] = useState<string>('')
  const [quote, setQuote] = useState<MarketQuoteResponse | null>(null)
  const [series, setSeries] = useState<MarketSeriesResponse | null>(null)
  const [candles, setCandles] = useState<MarketCandlesResponse | null>(null)

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

  return (
    <div style={{ display: 'grid', gap: 12 }}>
      <div className="card" style={{ textAlign: 'left' }}>
        <h3 style={{ marginTop: 0 }}>Quote</h3>
        {err ? <div style={{ color: 'crimson' }}>{err}</div> : null}
        <button onClick={refresh}>Refresh</button>
        <pre style={{ whiteSpace: 'pre-wrap' }}>{quote ? JSON.stringify(quote, null, 2) : 'N/A'}</pre>
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
