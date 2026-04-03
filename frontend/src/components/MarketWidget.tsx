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

export default function MarketWidget({ isFocused }: { isFocused?: boolean }) {
  const { symbol, setSymbol, roomId } = useAppSession()
  const [symbols, setSymbols] = useState<string[]>([])
  const [err, setErr] = useState<string>('')
  const [quote, setQuote] = useState<MarketQuoteResponse | null>(null)
  const [flashColor, setFlashColor] = useState<'up' | 'down' | null>(null)
  const [session, setSession] = useState<MarketSessionResponse | null>(null)
  const [candles, setCandles] = useState<MarketCandlesResponse | null>(null)

  const [autoRefresh] = useState<boolean>(true)
  const [refreshSeconds] = useState<number>(3)
  const [candleInterval, setCandleInterval] = useState<number>(60)
  const candleLimit = 200
  const visibleCandlesCount = isFocused ? 70 : 50
  const shiftStep = isFocused ? 20 : 10
  const [candleOffset, setCandleOffset] = useState<number>(0)

  const refresh = useCallback(async (): Promise<void> => {
    setErr('')
    try {
      const [q, c, sess, syms] = await Promise.all([
        Api.marketQuote(symbol),
        Api.marketCandles(symbol, candleInterval, candleLimit),
        Api.marketSession(),
        Api.marketSymbols(),
      ])
      setSymbols(syms)
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
  }, [symbol, candleInterval, candleLimit, roomId])

  useEffect(() => {
    const ws = new WsClient();
    ws.connect('events', (data: unknown) => {
      const ev = data as TradeExecutedEvent;
      if (ev?.event_type === 'trade.executed' && ev?.payload?.symbol === symbol) {
        refresh();
      }
    });
    return () => ws.close();
  }, [symbol, refresh, roomId]);

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
  }, [symbol, candleInterval, roomId])

  useEffect(() => {
    setCandleOffset(0)
  }, [symbol, candleInterval, roomId])

  const refreshMs = useMemo(() => Math.max(1, Number(refreshSeconds)) * 1000, [refreshSeconds])

  const maxCandleOffset = useMemo(() => {
    const total = candles?.candles?.length || 0
    return Math.max(0, total - visibleCandlesCount)
  }, [candles?.candles?.length, visibleCandlesCount])

  const visibleCandles = useMemo(() => {
    const all = candles?.candles || []
    if (all.length === 0) return []
    const offset = Math.min(candleOffset, maxCandleOffset)
    const end = all.length - offset
    const start = Math.max(0, end - visibleCandlesCount)
    return all.slice(start, end)
  }, [candles?.candles, candleOffset, maxCandleOffset, visibleCandlesCount])

  const canStepBack = candleOffset < maxCandleOffset
  const canStepForward = candleOffset > 0

  const stepBackward = () => {
    setCandleOffset((prev) => Math.min(maxCandleOffset, prev + shiftStep))
  }

  const stepForward = () => {
    setCandleOffset((prev) => Math.max(0, prev - shiftStep))
  }

  useEffect(() => {
    if (!autoRefresh) return
    const t = window.setInterval(() => {
      refresh()
    }, refreshMs)
    return () => window.clearInterval(t)
  }, [autoRefresh, refreshMs, refresh])

  const last = quote?.last_price
  const changePct = quote?.change_pct
  const high24h = quote?.high_24h
  const low24h = quote?.low_24h
  
  // 计算 24h 振幅
  const amplitude = (high24h && low24h && low24h > 0) 
    ? ((high24h - low24h) / low24h * 100).toFixed(2) 
    : '--'

  // 模拟情绪指标 ( Sentiment )
  const sentiment = useMemo(() => {
    if (!changePct) return 50;
    return Math.min(95, Math.max(5, 50 + (changePct * 500)));
  }, [changePct]);

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
      title={isFocused ? `MARKET_ANALYSIS: ${symbol}` : symbol} 
      subtitle={isFocused ? "DEEP_QUANTUM_DATA_STREAM" : "REALTIME_FEED"}
      actions={
        <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
          <div style={{ position: 'relative', display: 'flex', alignItems: 'center' }}>
            <span style={{ fontSize: '9px', color: '#64748b', marginRight: '4px', fontFamily: 'monospace' }}>SEC:</span>
            <select 
              className="cyber-input"
              value={symbol}
              onChange={(e) => setSymbol(e.target.value)}
              style={{ 
                fontSize: '11px', 
                padding: '0 4px', 
                height: '22px', 
                minWidth: '80px',
                background: 'rgba(30, 41, 59, 0.5)',
                borderColor: 'rgba(59, 130, 246, 0.3)',
                color: 'var(--terminal-info)',
                fontWeight: 'bold'
              }}
            >
              {symbols.map(s => <option key={s} value={s}>{s}</option>)}
            </select>
          </div>

          {isFocused && (
            <select 
              className="cyber-input" 
              style={{ fontSize: '11px', padding: '0 4px', height: '22px', background: 'rgba(30, 41, 59, 0.5)' }}
              value={candleInterval}
              onChange={e => setCandleInterval(Number(e.target.value))}
            >
              <option value={60}>1M</option>
              <option value={300}>5M</option>
              <option value={900}>15M</option>
            </select>
          )}
          <button 
            className="cyber-button" 
            style={{ fontSize: '10px', padding: '0 8px', height: '22px', minWidth: 'auto' }} 
            onClick={refresh}
          >
            SYNC
          </button>
        </div>
      }
    >
      <div style={{ position: 'absolute', top: 0, right: 0, width: '40px', height: '40px', overflow: 'hidden', pointerEvents: 'none', opacity: 0.1 }}>
        <div style={{ position: 'absolute', top: '-20px', right: '-20px', width: '40px', height: '40px', background: 'var(--terminal-info)', transform: 'rotate(45deg)' }} />
      </div>

      {err && <div style={{ color: 'var(--terminal-error)', fontSize: '12px', marginBottom: '10px', background: 'rgba(239, 68, 68, 0.1)', padding: '5px', borderLeft: '2px solid var(--terminal-error)' }}>[ERR]: {err}</div>}
      
      <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '12px', padding: '0 5px' }}>
          <div style={{ display: 'flex', gap: '20px', alignItems: 'flex-end' }}>
            <div>
              <div style={{ fontSize: '9px', color: '#64748b', marginBottom: '2px', letterSpacing: '1px' }}>LAST_PRICE</div>
              <div style={{ 
                fontSize: isFocused ? '32px' : '24px', 
                fontWeight: '900', 
                color: flashColor === 'up' ? 'var(--terminal-success)' : (flashColor === 'down' ? 'var(--terminal-error)' : '#fff'),
                fontFamily: 'monospace',
                lineHeight: 1,
                textShadow: flashColor ? `0 0 15px ${flashColor === 'up' ? 'var(--terminal-success)' : 'var(--terminal-error)'}` : 'none',
                transition: 'all 0.2s'
              }}>
                ${last?.toFixed(2) ?? '--'}
              </div>
            </div>
            <div>
              <div style={{ fontSize: '9px', color: '#64748b', marginBottom: '2px', letterSpacing: '1px' }}>MARKET_CHG</div>
              <div style={{ fontSize: isFocused ? '18px' : '14px', fontWeight: '700', color: changeColor, marginBottom: '2px' }}>
                {changePct !== undefined && changePct !== null && (changePct >= 0 ? '▲ ' : '▼ ')}
                {changeText}
              </div>
            </div>
            {isFocused && (
              <div style={{ width: '100px', marginBottom: '4px' }}>
                <div style={{ fontSize: '8px', color: '#64748b', marginBottom: '2px', textAlign: 'center' }}>SENTIMENT</div>
                <div style={{ height: '4px', background: 'rgba(255,255,255,0.1)', borderRadius: '2px', overflow: 'hidden', display: 'flex' }}>
                  <div style={{ width: `${sentiment}%`, background: changePct && changePct >= 0 ? 'var(--terminal-success)' : 'var(--terminal-error)', transition: 'width 0.5s cubic-bezier(0.4, 0, 0.2, 1)' }} />
                </div>
              </div>
            )}
          </div>

          <div style={{ display: 'flex', gap: '15px', textAlign: 'right' }}>
            {isFocused && (
              <>
                <div>
                  <div style={{ fontSize: '9px', color: '#64748b', letterSpacing: '1px' }}>AMPLITUDE_24H</div>
                  <div style={{ fontSize: '12px', color: '#fff', fontWeight: '600', fontFamily: 'monospace' }}>{amplitude}%</div>
                </div>
                <div>
                  <div style={{ fontSize: '9px', color: '#64748b', letterSpacing: '1px' }}>HIGH / LOW</div>
                  <div style={{ fontSize: '12px', color: '#fff', fontWeight: '600', fontFamily: 'monospace' }}>
                    <span style={{ color: 'var(--terminal-success)' }}>{quote?.high_24h?.toFixed(2) ?? '--'}</span>
                    <span style={{ margin: '0 4px', opacity: 0.3 }}>/</span>
                    <span style={{ color: 'var(--terminal-error)' }}>{quote?.low_24h?.toFixed(2) ?? '--'}</span>
                  </div>
                </div>
              </>
            )}
            {!isFocused && (
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px', background: 'rgba(59, 130, 246, 0.1)', padding: '4px 8px', borderRadius: '4px', border: '1px solid rgba(59, 130, 246, 0.2)' }}>
                <div className="blink" style={{ width: '6px', height: '6px', borderRadius: '50%', background: 'var(--terminal-success)' }} />
                <span style={{ fontSize: '9px', color: 'var(--terminal-info)', fontWeight: 'bold' }}>LIVE</span>
              </div>
            )}
          </div>
        </div>

        <div style={{ 
          flex: 1,
          background: 'rgba(0,0,0,0.15)', 
          borderRadius: '2px', 
          padding: '5px', 
          border: '1px solid var(--terminal-border)',
          minHeight: 0,
          position: 'relative',
          display: 'flex',
          flexDirection: 'row', // 改为横向布局，左侧 K 线，右侧极简买卖盘
          gap: '5px'
        }}>
          <div style={{ flex: 1, position: 'relative' }}>
            <div style={{
              position: 'absolute',
              top: '6px',
              right: '8px',
              zIndex: 20,
              display: 'flex',
              alignItems: 'center',
              gap: '2px',
              background: 'rgba(15, 23, 42, 0.82)',
              border: '1px solid rgba(59, 130, 246, 0.3)',
              borderRadius: '4px',
              padding: '2px'
            }}>
              <button
                className="cyber-button"
                onClick={stepBackward}
                disabled={!canStepBack}
                title="回看更早K线"
                style={{ fontSize: '10px', padding: '0 6px', height: '18px', lineHeight: 1, opacity: canStepBack ? 1 : 0.4 }}
              >
                ◀
              </button>
              <button
                className="cyber-button"
                onClick={stepForward}
                disabled={!canStepForward}
                title="向前回到更新K线"
                style={{ fontSize: '10px', padding: '0 6px', height: '18px', lineHeight: 1, opacity: canStepForward ? 1 : 0.4 }}
              >
                ▶
              </button>
            </div>
            {candleOffset > 0 && (
              <div style={{
                position: 'absolute',
                top: '8px',
                left: '8px',
                zIndex: 20,
                fontSize: '10px',
                fontFamily: 'monospace',
                color: '#94a3b8',
                background: 'rgba(15, 23, 42, 0.82)',
                border: '1px solid rgba(148, 163, 184, 0.2)',
                borderRadius: '4px',
                padding: '2px 6px'
              }}>
                HIST -{candleOffset}
              </div>
            )}
            <CandlestickChart candles={visibleCandles} />
          </div>
          
          {isFocused && (
            <div style={{ 
              width: '120px', 
              borderLeft: '1px solid rgba(59, 130, 246, 0.2)', 
              paddingLeft: '8px', 
              display: 'flex', 
              flexDirection: 'column', 
              gap: '4px',
              fontSize: '10px',
              fontFamily: 'monospace'
            }}>
              <div style={{ color: '#64748b', fontSize: '8px', marginBottom: '4px' }}>ORDER_FLOW</div>
              <div style={{ color: 'var(--terminal-error)', display: 'flex', justifyContent: 'space-between' }}>
                <span>{((last || 0) * 1.002).toFixed(2)}</span>
                <span style={{ opacity: 0.6 }}>{(Math.random() * 500).toFixed(0)}</span>
              </div>
              <div style={{ color: 'var(--terminal-error)', display: 'flex', justifyContent: 'space-between', opacity: 0.7 }}>
                <span>{((last || 0) * 1.001).toFixed(2)}</span>
                <span style={{ opacity: 0.6 }}>{(Math.random() * 800).toFixed(0)}</span>
              </div>
              <div style={{ 
                height: '1px', 
                background: 'rgba(255,255,255,0.1)', 
                margin: '4px 0',
                position: 'relative' 
              }}>
                <div style={{ position: 'absolute', top: '-6px', left: '0', fontSize: '8px', background: 'var(--panel-bg)', padding: '0 2px' }}>SPREAD: 0.01%</div>
              </div>
              <div style={{ color: 'var(--terminal-success)', display: 'flex', justifyContent: 'space-between' }}>
                <span>{((last || 0) * 0.999).toFixed(2)}</span>
                <span style={{ opacity: 0.6 }}>{(Math.random() * 1200).toFixed(0)}</span>
              </div>
              <div style={{ color: 'var(--terminal-success)', display: 'flex', justifyContent: 'space-between', opacity: 0.7 }}>
                <span>{((last || 0) * 0.998).toFixed(2)}</span>
                <span style={{ opacity: 0.6 }}>{(Math.random() * 600).toFixed(0)}</span>
              </div>
              
              <div style={{ marginTop: 'auto', borderTop: '1px solid rgba(255,255,255,0.05)', paddingTop: '4px' }}>
                <div style={{ color: '#64748b', fontSize: '8px' }}>LIQUIDITY_DEPTH</div>
                <div style={{ display: 'flex', gap: '2px', height: '20px', alignItems: 'flex-end' }}>
                  {[4,7,3,8,5,9,4,6].map((h, i) => (
                    <div key={i} style={{ flex: 1, height: `${h * 10}%`, background: 'var(--terminal-info)', opacity: 0.3 }} />
                  ))}
                </div>
              </div>
            </div>
          )}
        </div>

        {(isFocused || !!session) && (
          <div style={{ 
            marginTop: '8px', 
            fontSize: '9px', 
            padding: '4px 8px', 
            background: 'rgba(51, 65, 85, 0.2)',
            border: '1px solid var(--terminal-border)',
            color: '#94a3b8',
            display: 'flex',
            justifyContent: 'space-between',
            flexShrink: 0
          }}>
            {session && (
              <>
                <span>STATUS: <span style={{ color: session.phase === 'TRADING' ? 'var(--terminal-success)' : 'var(--terminal-error)', fontWeight: 'bold' }}>{session.phase}</span></span>
                <span>GAME_DAY: {session.game_day_index}</span>
              </>
            )}
            <span>SYMBOL: {symbol}</span>
          </div>
        )}
      </div>
    </CyberWidget>
  )
}
