import { useCallback, useEffect, useMemo, useState } from 'react'
import { Api, ApiError, WsClient, type MarketCandlesResponse, type MarketQuoteResponse, type MarketSessionResponse } from '../api'
import { useAppSession } from '../app/context'
import CyberWidget from './CyberWidget'
import CandlestickChart from './CandlestickChart'

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
  const [candles, setCandles] = useState<MarketCandlesResponse | null>(null)

  const [autoRefresh] = useState<boolean>(true)
  const [refreshSeconds] = useState<number>(3)
  const [candleInterval, setCandleInterval] = useState<number>(60)
  const candleLimit = 50

  const refresh = useCallback(async (): Promise<void> => {
    setErr('')
    try {
      const [q, c, sess] = await Promise.all([
        Api.marketQuote(symbol),
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
    let active = true
    const doRefresh = async () => {
      if (active) await refresh()
    }
    doRefresh()
    return () => {
      active = false
    }
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
      ? '#64748b'
      : changePct >= 0
        ? 'var(--terminal-success)'
        : 'var(--terminal-error)'

  return (
    <CyberWidget 
      title={`SYMBOL_DETAILS: ${symbol}`} 
      subtitle="PRECISION_MARKET_MONITOR"
      actions={
        <div style={{ display: 'flex', gap: '8px' }}>
          <select 
            className="cyber-input" 
            style={{ fontSize: '11px', padding: '2px 4px', height: '24px' }}
            value={candleInterval}
            onChange={e => setCandleInterval(Number(e.target.value))}
          >
            <option value={60}>1M</option>
            <option value={300}>5M</option>
            <option value={900}>15M</option>
          </select>
          <button className="cyber-button" style={{ fontSize: '11px', padding: '0 8px', height: '24px' }} onClick={refresh}>SYNC</button>
        </div>
      }
    >
      {err && <div style={{ color: 'var(--terminal-error)', fontSize: '12px', marginBottom: '10px' }}>[ERR]: {err}</div>}
      
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '15px', padding: '0 5px' }}>
        <div style={{ display: 'flex', gap: '30px' }}>
          <div>
            <div style={{ fontSize: '10px', color: '#64748b', marginBottom: '2px' }}>LAST_PRICE</div>
            <div style={{ 
              fontSize: '28px', 
              fontWeight: '800', 
              color: flashColor === 'up' ? 'var(--terminal-success)' : (flashColor === 'down' ? 'var(--terminal-error)' : '#fff'),
              fontFamily: 'monospace'
            }}>
              ${last?.toFixed(2) ?? '--'}
            </div>
          </div>
          <div>
            <div style={{ fontSize: '10px', color: '#64748b', marginBottom: '2px' }}>24H_CHANGE</div>
            <div style={{ fontSize: '18px', fontWeight: '700', color: changeColor, marginTop: '8px' }}>
              {changePct !== undefined && changePct !== null && (changePct >= 0 ? '▲ ' : '▼ ')}
              {changeText}
            </div>
          </div>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'x 20px', textAlign: 'right' }}>
          <div>
            <div style={{ fontSize: '9px', color: '#64748b' }}>HIGH_24H</div>
            <div style={{ fontSize: '12px', color: '#fff', fontWeight: '600' }}>{quote?.high_24h?.toFixed(2) ?? '--'}</div>
          </div>
          <div>
            <div style={{ fontSize: '9px', color: '#64748b' }}>LOW_24H</div>
            <div style={{ fontSize: '12px', color: '#fff', fontWeight: '600' }}>{quote?.low_24h?.toFixed(2) ?? '--'}</div>
          </div>
          <div style={{ marginTop: '4px' }}>
            <div style={{ fontSize: '9px', color: '#64748b' }}>OPEN_24H</div>
            <div style={{ fontSize: '12px', color: '#cbd5e1' }}>{quote?.prev_price?.toFixed(2) ?? '--'}</div>
          </div>
          <div style={{ marginTop: '4px' }}>
            <div style={{ fontSize: '9px', color: '#64748b' }}>VOLUME_24H</div>
            <div style={{ fontSize: '12px', color: '#cbd5e1' }}>{quote?.volume_24h?.toLocaleString() ?? '--'}</div>
          </div>
        </div>
      </div>

      <div style={{ background: 'rgba(0,0,0,0.15)', borderRadius: '2px', padding: '10px', border: '1px solid var(--terminal-border)' }}>
        <CandlestickChart candles={candles?.candles || []} height={280} />
      </div>

      {session && (
        <div style={{ 
          marginTop: '12px', 
          fontSize: '10px', 
          padding: '4px 10px', 
          background: 'rgba(51, 65, 85, 0.2)',
          border: '1px solid var(--terminal-border)',
          color: '#94a3b8',
          display: 'flex',
          justifyContent: 'space-between'
        }}>
          <span>STATUS: <span style={{ color: session.phase === 'TRADING' ? 'var(--terminal-success)' : 'var(--terminal-error)', fontWeight: 'bold' }}>{session.phase}</span></span>
          <span>GAME_DAY: {session.game_day_index}</span>
          <span>SYMBOL: {symbol}</span>
        </div>
      )}
    </CyberWidget>
  )
}
