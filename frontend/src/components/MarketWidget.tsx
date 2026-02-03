import { useCallback, useEffect, useMemo, useState } from 'react'
import { Api, ApiError, WsClient, type MarketCandlesResponse, type MarketQuoteResponse, type MarketSeriesResponse, type MarketSessionResponse } from '../api'
import { useAppSession } from '../app/context'
import CyberWidget from './CyberWidget'

interface TradeExecutedEvent {
  event_type: string;
  payload?: {
    symbol?: string;
  };
}

export default function MarketWidget() {
  const { symbol } = useAppSession()
  const [err, setErr] = useState<string>('')
  const [quote, setQuote] = useState<MarketQuoteResponse | null>(null)
  const [flashColor, setFlashColor] = useState<'up' | 'down' | null>(null)
  const [session, setSession] = useState<MarketSessionResponse | null>(null)
  const [series, setSeries] = useState<MarketSeriesResponse | null>(null)
  const [candles, setCandles] = useState<MarketCandlesResponse | null>(null)

  const [autoRefresh] = useState<boolean>(true)
  const [refreshSeconds] = useState<number>(3)
  const [candleInterval, setCandleInterval] = useState<number>(60)
  const candleLimit = 50

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
        ? '#52c41a'
        : '#ff4d4f'

  const sparkline = useMemo(() => {
    const prices = series?.prices
    if (!prices || prices.length < 2) return null
    const displayPrices = prices.slice(-30)
    const min = Math.min(...displayPrices)
    const max = Math.max(...displayPrices)
    const range = max - min || 1
    return (
      <div style={{ display: 'flex', alignItems: 'flex-end', height: 30, gap: 1, marginTop: 10, background: 'rgba(255,255,255,0.05)', padding: '2px' }}>
        {displayPrices.map((p: number, i: number) => (
          <div
            key={i}
            style={{
              flex: 1,
              background: p >= (displayPrices[i - 1] ?? p) ? '#52c41a' : '#ff4d4f',
              height: `${((p - min) / range) * 100}%`,
              minWidth: 2,
            }}
          />
        ))}
      </div>
    )
  }, [series])

  return (
    <CyberWidget 
      title={`MARKET_DATA: ${symbol}`} 
      subtitle="REALTIME_QUOTE_ENGINE"
      actions={
        <div style={{ display: 'flex', gap: 5 }}>
          <button className="cyber-button" style={{ fontSize: '9px', padding: '2px 6px' }} onClick={refresh}>REFRESH</button>
          <select 
            className="cyber-input" 
            style={{ fontSize: '9px', padding: '1px 2px' }}
            value={candleInterval}
            onChange={e => setCandleInterval(Number(e.target.value))}
          >
            <option value={60}>1M</option>
            <option value={300}>5M</option>
            <option value={900}>15M</option>
          </select>
        </div>
      }
    >
      {err && <div style={{ color: 'var(--terminal-error)', fontSize: '11px', marginBottom: 10 }}>[ERR]: {err}</div>}
      
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, marginBottom: 10 }}>
        <div className="cyber-card" style={{ padding: '8px', border: '1px solid #333' }}>
          <div style={{ fontSize: '9px', opacity: 0.6 }}>LAST_PRICE</div>
          <div style={{ 
            fontSize: '20px', 
            fontWeight: 'bold', 
            color: flashColor === 'up' ? '#52c41a' : (flashColor === 'down' ? '#ff4d4f' : '#fff'),
            textShadow: flashColor ? `0 0 10px ${flashColor === 'up' ? '#52c41a' : '#ff4d4f'}` : 'none'
          }}>
            ${last?.toFixed(2) ?? '--'}
          </div>
        </div>
        <div className="cyber-card" style={{ padding: '8px', border: '1px solid #333' }}>
          <div style={{ fontSize: '9px', opacity: 0.6 }}>24H_CHANGE</div>
          <div style={{ fontSize: '18px', fontWeight: 'bold', color: changeColor }}>
            {changeText}
          </div>
        </div>
      </div>

      {sparkline}

      <div style={{ marginTop: 15 }}>
        <div style={{ fontSize: '10px', marginBottom: 5, opacity: 0.7 }}>RECENT_CANDLES</div>
        <div style={{ maxHeight: '150px', overflow: 'auto', border: '1px solid #222' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '10px' }}>
            <thead style={{ position: 'sticky', top: 0, background: '#000', zIndex: 1, borderBottom: '1px solid #333' }}>
              <tr>
                <th style={{ textAlign: 'left', padding: '4px' }}>TIME</th>
                <th style={{ textAlign: 'right', padding: '4px' }}>PRICE</th>
                <th style={{ textAlign: 'right', padding: '4px' }}>VOL</th>
              </tr>
            </thead>
            <tbody>
              {candles?.candles?.slice(-10).reverse().map((c, i) => (
                <tr key={i} style={{ borderBottom: '1px solid #111' }}>
                  <td style={{ padding: '4px' }}>{new Date(c.bucket_start).toLocaleTimeString()}</td>
                  <td style={{ padding: '4px', textAlign: 'right', color: c.close >= c.open ? '#52c41a' : '#ff4d4f' }}>
                    {c.close.toFixed(2)}
                  </td>
                  <td style={{ padding: '4px', textAlign: 'right', opacity: 0.6 }}>{c.volume}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {session && (
        <div style={{ 
          marginTop: 10, 
          fontSize: '9px', 
          padding: '4px', 
          background: session.phase === 'TRADING' ? 'rgba(82, 196, 26, 0.1)' : 'rgba(255, 77, 79, 0.1)',
          border: `1px solid ${session.phase === 'TRADING' ? '#52c41a' : '#ff4d4f'}`
        }}>
          SESSION: {session.phase} // DAY_{session.game_day_index}
        </div>
      )}
    </CyberWidget>
  )
}
