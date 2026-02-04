import { useCallback, useEffect, useMemo, useState } from 'react'
import { Api, ApiError, WsClient, type MarketCandleItem, type MarketCandlesResponse, type MarketQuoteResponse, type MarketSeriesResponse, type MarketSessionResponse } from '../api'
import { useAppSession } from '../app/context'

interface TradeExecutedEvent {
  event_type: string;
  payload?: {
    symbol?: string;
  };
}

export default function MarketPage() {
  const { symbol } = useAppSession()
  const [err, setErr] = useState<string>('')
  const [quote, setQuote] = useState<MarketQuoteResponse | null>(null)
  const [flashColor, setFlashColor] = useState<'up' | 'down' | null>(null)
  const [session, setSession] = useState<MarketSessionResponse | null>(null)
  const [series, setSeries] = useState<MarketSeriesResponse | null>(null)
  const [candles, setCandles] = useState<MarketCandlesResponse | null>(null)

  const [autoRefresh, setAutoRefresh] = useState<boolean>(true)
  const [refreshSeconds, setRefreshSeconds] = useState<number>(3)

  const [candleInterval, setCandleInterval] = useState<number>(60)
  const candleLimit = 120

  const refresh = useCallback(async (): Promise<void> => {
    setErr('')
    try {
      const [q, s, c, sess] = await Promise.all([
        Api.marketQuote(symbol),
        Api.marketSeries(symbol, 200),
        Api.marketCandles(symbol, candleInterval, candleLimit),
        Api.marketSession(),
      ])
      setQuote((prevQuote) => {
        if (prevQuote && q.last_price !== null && prevQuote.last_price !== null) {
          if (q.last_price > prevQuote.last_price) {
            setFlashColor('up')
            setTimeout(() => setFlashColor(null), 1000)
          } else if (q.last_price < prevQuote.last_price) {
            setFlashColor('down')
            setTimeout(() => setFlashColor(null), 1000)
          }
        }
        return q
      })
      setSeries(s)
      setCandles(c)
      setSession(sess)
    } catch (e) {
      if (e instanceof ApiError) setErr(`${e.status}: ${e.message}`)
      else setErr(e instanceof Error ? e.message : String(e))
    }
  }, [symbol, candleInterval, candleLimit])

  useEffect(() => {
    const ws = new WsClient();
    ws.connect('events', (data: unknown) => {
      const ev = data as TradeExecutedEvent;
      if (ev?.event_type === 'TRADE_EXECUTED' && ev?.payload?.symbol === symbol) {
        refresh();
      }
    });
    return () => ws.close();
  }, [symbol, refresh]);

  useEffect(() => {
    refresh()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [symbol, candleInterval])

  const refreshMs = useMemo(() => Math.max(1, Number(refreshSeconds)) * 1000, [refreshSeconds])

  useEffect(() => {
    if (!autoRefresh) return
    const t = window.setInterval(() => {
      refresh()
    }, refreshMs)
    return () => window.clearInterval(t)
  }, [autoRefresh, refreshMs, refresh])

  const last = quote?.last_price
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

  // Simple Sparkline (Div based)
  const sparkline = useMemo(() => {
    const prices = series?.prices
    if (!prices || prices.length < 2) return null
    const displayPrices = prices.slice(-50)
    const min = Math.min(...displayPrices)
    const max = Math.max(...displayPrices)
    const range = max - min || 1
    return (
      <div style={{ display: 'flex', alignItems: 'flex-end', height: 40, gap: 1, marginTop: 15, background: '#f9f9f9', padding: '4px', borderRadius: '4px' }}>
        {displayPrices.map((p: number, i: number) => (
          <div
            key={i}
            style={{
              flex: 1,
              background: p >= (displayPrices[i - 1] ?? p) ? '#52c41a' : '#f5222d',
              height: `${((p - min) / range) * 100}%`,
              minWidth: 2,
            }}
          />
        ))}
      </div>
    )
  }, [series])

  return (
    <div style={{ display: 'grid', gap: 12 }}>
      <div className="card" style={{ textAlign: 'left' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
          <h3 style={{ margin: 0 }}>行情概览</h3>
          {session && (
            <div style={{ fontSize: 13, padding: '2px 8px', borderRadius: 4, background: session.phase === 'TRADING' ? '#f6ffed' : '#fff1f0', color: session.phase === 'TRADING' ? '#52c41a' : '#f5222d', border: '1px solid currentColor' }}>
              {session.phase} - 天 {session.game_day_index}
            </div>
          )}
        </div>
        
        {err ? <div style={{ color: 'crimson', marginBottom: 10 }}>{err}</div> : null}

        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'center', marginBottom: 15 }}>
          <button onClick={refresh}>刷新</button>
          <label style={{ display: 'flex', gap: 6, alignItems: 'center', fontSize: 14 }}>
            <input type="checkbox" checked={autoRefresh} onChange={(e) => setAutoRefresh(e.target.checked)} />
            自动刷新
          </label>
          <label style={{ display: 'flex', gap: 6, alignItems: 'center', fontSize: 14 }}>
            间隔(s)
            <input
              type="number"
              value={refreshSeconds}
              onChange={(e) => setRefreshSeconds(Number(e.target.value))}
              min={1}
              style={{ width: 60, padding: '2px 4px' }}
            />
          </label>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: 12 }}>
          <div style={{ padding: 12, background: '#fafafa', borderRadius: 8, border: '1px solid #f0f0f0' }}>
            <div style={{ color: '#888', fontSize: 12 }}>标的</div>
            <div style={{ fontSize: 18, fontWeight: 700 }}>{quote?.symbol ?? symbol}</div>
          </div>
          <div style={{ 
            padding: 12, 
            background: flashColor === 'up' ? '#f6ffed' : (flashColor === 'down' ? '#fff1f0' : '#fafafa'), 
            borderRadius: 8, 
            border: `1px solid ${flashColor === 'up' ? '#b7eb8f' : (flashColor === 'down' ? '#ffccc7' : '#f0f0f0')}`,
            transition: 'all 0.1s ease-in-out',
            boxShadow: flashColor === 'up' ? '0 0 10px rgba(82, 196, 26, 0.3)' : (flashColor === 'down' ? '0 0 10px rgba(245, 34, 45, 0.3)' : 'none')
          }}>
            <div style={{ color: '#888', fontSize: 12 }}>现价</div>
            <div style={{ 
              fontSize: 24, 
              fontWeight: 800,
              color: flashColor === 'up' ? '#52c41a' : (flashColor === 'down' ? '#f5222d' : 'inherit'),
              fontFamily: 'monospace'
            }}>
              {last?.toFixed(2) ?? '--'}
              {flashColor === 'up' && ' ▲'}
              {flashColor === 'down' && ' ▼'}
            </div>
          </div>
          <div style={{ padding: 12, background: '#fafafa', borderRadius: 8, border: '1px solid #f0f0f0' }}>
            <div style={{ color: '#888', fontSize: 12 }}>涨跌幅</div>
            <div style={{ fontSize: 18, fontWeight: 700, color: changeColor }}>{changeText}</div>
          </div>
          <div style={{ padding: 12, background: '#fafafa', borderRadius: 8, border: '1px solid #f0f0f0' }}>
            <div style={{ color: '#888', fontSize: 12 }}>24h 最高 / 最低</div>
            <div style={{ fontSize: 16, fontWeight: 700 }}>
              <span style={{ color: '#52c41a' }}>{quote?.high_24h?.toFixed(2) ?? '--'}</span>
              <span style={{ margin: '0 4px', color: '#ccc' }}>/</span>
              <span style={{ color: '#f5222d' }}>{quote?.low_24h?.toFixed(2) ?? '--'}</span>
            </div>
          </div>
          <div style={{ padding: 12, background: '#fafafa', borderRadius: 8, border: '1px solid #f0f0f0' }}>
            <div style={{ color: '#888', fontSize: 12 }}>24h 成交量</div>
            <div style={{ fontSize: 18, fontWeight: 700 }}>{quote?.volume_24h?.toLocaleString() ?? '--'}</div>
          </div>
        </div>

        {sparkline}

        <details style={{ marginTop: 15 }}>
          <summary style={{ fontSize: 12, color: '#999', cursor: 'pointer' }}>原始数据 (Raw JSON)</summary>
          <pre style={{ whiteSpace: 'pre-wrap', fontSize: 11, background: '#f8f8f8', padding: 8, borderRadius: 4, marginTop: 5 }}>{quote ? JSON.stringify(quote, null, 2) : 'N/A'}</pre>
        </details>
      </div>

      <div className="card" style={{ textAlign: 'left' }}>
        <h3 style={{ marginTop: 0 }}>历史 K 线</h3>
        <div style={{ marginBottom: 12, display: 'flex', gap: 12, alignItems: 'center' }}>
          <label style={{ fontSize: 13 }}>间隔: 
            <select value={candleInterval} onChange={e => setCandleInterval(Number(e.target.value))} style={{ marginLeft: 5, padding: '2px 4px' }}>
              <option value={60}>1m</option>
              <option value={300}>5m</option>
              <option value={900}>15m</option>
            </select>
          </label>
          <button onClick={refresh} style={{ padding: '2px 10px', fontSize: 12 }}>应用</button>
        </div>
        
        {candles?.candles?.length ? (
          <div style={{ overflow: 'auto', maxHeight: 400 }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
              <thead style={{ position: 'sticky', top: 0, background: '#fafafa', zIndex: 1 }}>
                <tr>
                  <th style={{ textAlign: 'left', borderBottom: '2px solid #eee', padding: 10 }}>时间</th>
                  <th style={{ textAlign: 'right', borderBottom: '2px solid #eee', padding: 10 }}>开盘</th>
                  <th style={{ textAlign: 'right', borderBottom: '2px solid #eee', padding: 10 }}>收盘</th>
                  <th style={{ textAlign: 'right', borderBottom: '2px solid #eee', padding: 10 }}>最高</th>
                  <th style={{ textAlign: 'right', borderBottom: '2px solid #eee', padding: 10 }}>最低</th>
                  <th style={{ textAlign: 'right', borderBottom: '2px solid #eee', padding: 10 }}>成交量</th>
                </tr>
              </thead>
              <tbody>
              {candles.candles.slice().reverse().map((c: MarketCandleItem, i: number) => {
                const isUp = c.close >= c.open;
                return (
                  <tr key={i} style={{ 
                    borderBottom: '1px solid #f0f0f0',
                    background: i % 2 === 0 ? 'transparent' : '#fafafa'
                  }}>
                    <td style={{ padding: 10 }}>{new Date(c.bucket_start).toLocaleTimeString()}</td>
                    <td style={{ padding: 10, textAlign: 'right' }}>{c.open.toFixed(2)}</td>
                    <td style={{ 
                      padding: 10, 
                      textAlign: 'right', 
                      color: isUp ? '#52c41a' : '#f5222d', 
                      fontWeight: 700,
                      background: isUp ? 'rgba(82, 196, 26, 0.05)' : 'rgba(245, 34, 45, 0.05)'
                    }}>{c.close.toFixed(2)}</td>
                    <td style={{ padding: 10, textAlign: 'right' }}>{c.high.toFixed(2)}</td>
                    <td style={{ padding: 10, textAlign: 'right' }}>{c.low.toFixed(2)}</td>
                    <td style={{ padding: 10, textAlign: 'right', color: '#666' }}>{c.volume.toLocaleString()}</td>
                  </tr>
                );
              })}
              </tbody>
            </table>
          </div>
        ) : <div style={{ padding: 30, color: '#999', textAlign: 'center', background: '#fafafa', borderRadius: 8 }}>暂无数据</div>}
      </div>
    </div>
  )
}
