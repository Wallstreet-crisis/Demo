import { useEffect, useState, useCallback, useMemo } from 'react'
import { Api, WsClient, type MarketQuoteResponse } from '../api'
import { useAppSession } from '../app/context'
import CyberWidget from './CyberWidget'

export default function MarketWatchWidget({ isFocused }: { isFocused?: boolean }) {
  void isFocused
  const { symbol, setSymbol, roomId } = useAppSession()
  const [symbols, setSymbols] = useState<string[]>([])
  const [quotes, setQuotes] = useState<Record<string, MarketQuoteResponse>>({})
  const [loading, setLoading] = useState(true)

  const ws = useMemo(() => new WsClient(), [])

  const refreshQuotes = useCallback(async (syms: string[]) => {
    try {
      const results = await Promise.all(syms.map(s => Api.marketQuote(s)))
      const newQuotes: Record<string, MarketQuoteResponse> = {}
      results.forEach(q => {
        newQuotes[q.symbol] = q
      })
      setQuotes(newQuotes)
    } catch (e) {
      console.error('Failed to fetch quotes', e)
    }
  }, [roomId])

  useEffect(() => {
    const init = async () => {
      try {
        const syms = await Api.marketSymbols()
        setSymbols(syms)
        await refreshQuotes(syms)
      } catch (e) {
        console.error('Failed to fetch symbols', e)
      } finally {
        setLoading(false)
      }
    }
    init()
  }, [refreshQuotes, roomId])

  useEffect(() => {
    ws.connect('events', (data: unknown) => {
      const ev = data as { event_type?: string }
      if (ev?.event_type === 'trade.executed') {
        // 当有任何成交发生时，刷新报价
        if (symbols.length > 0) {
          refreshQuotes(symbols)
        }
      }
    })
    return () => ws.close()
  }, [ws, symbols, refreshQuotes, roomId])

  useEffect(() => {
    if (symbols.length === 0) return
    const t = setInterval(() => {
      refreshQuotes(symbols)
    }, 10000) // 轮询频率降低，主要依靠 WS
    return () => clearInterval(t)
  }, [refreshQuotes, symbols, roomId])

  return (
    <CyberWidget 
      title="MARKET_WATCH" 
      subtitle="REALTIME_EQUITY_FEED"
    >
      <div style={{ display: 'flex', flexDirection: 'column', gap: '2px' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px' }}>
          <thead>
            <tr style={{ borderBottom: '1px solid var(--terminal-border)', color: '#64748b', fontSize: '10px' }}>
              <th style={{ textAlign: 'left', padding: '8px 4px' }}>SYMBOL</th>
              <th style={{ textAlign: 'right', padding: '8px 4px' }}>PRICE</th>
              <th style={{ textAlign: 'right', padding: '8px 4px' }}>CHG%</th>
            </tr>
          </thead>
          <tbody>
            {(isFocused ? symbols : symbols.slice(0, 6)).map(s => {
              const q = quotes[s]
              const isSelected = symbol === s
              const changePct = q?.change_pct ?? 0
              const color = changePct >= 0 ? 'var(--terminal-success)' : 'var(--terminal-error)'
              
              return (
                <tr 
                  key={s} 
                  onClick={() => setSymbol(s)}
                  style={{ 
                    cursor: 'pointer',
                    background: isSelected ? 'rgba(59, 130, 246, 0.1)' : 'transparent',
                    borderLeft: isSelected ? '2px solid var(--terminal-info)' : '2px solid transparent',
                    transition: 'background 0.1s'
                  }}
                  onMouseOver={e => !isSelected && (e.currentTarget.style.background = 'rgba(255,255,255,0.03)')}
                  onMouseOut={e => !isSelected && (e.currentTarget.style.background = 'transparent')}
                >
                  <td style={{ padding: '10px 4px', fontWeight: '600' }}>{s}</td>
                  <td style={{ padding: '10px 4px', textAlign: 'right', fontFamily: 'monospace' }}>
                    {q?.last_price?.toFixed(2) ?? '--'}
                  </td>
                  <td style={{ padding: '10px 4px', textAlign: 'right', color, fontWeight: '600' }}>
                    {changePct >= 0 ? '+' : ''}{(changePct * 100).toFixed(2)}%
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
        {loading && symbols.length === 0 && (
          <div style={{ textAlign: 'center', padding: '20px', opacity: 0.5, fontSize: '11px' }}>
            SCANNING_MARKET...
          </div>
        )}
      </div>
    </CyberWidget>
  )
}
