import { useEffect, useMemo, useState, useCallback } from 'react'
import { Api, ApiError, type AccountValuationResponse, type MarketQuoteResponse } from '../api'
import { useAppSession } from '../app/context'
import { useNotification } from '../app/NotificationContext'
import CyberWidget from './CyberWidget'

export default function TradeWidget({ isFocused }: { isFocused?: boolean }) {
  void isFocused
  const { playerId, symbol } = useAppSession()
  const { notify } = useNotification()
  const [err, setErr] = useState<string>('')
  const [loading, setLoading] = useState(false)

  const [quote, setQuote] = useState<MarketQuoteResponse | null>(null)
  const [val, setVal] = useState<AccountValuationResponse | null>(null)

  const [side, setSide] = useState<'BUY' | 'SELL'>('BUY')
  const [orderType, setOrderType] = useState<'LIMIT' | 'MARKET'>('LIMIT')
  const [price, setPrice] = useState<string>('')
  const [quantity, setQuantity] = useState<string>('1')
  const [aiSuggestion, setAiSuggestion] = useState<{ action: string; confidence: number; reason: string } | null>(null)
  const [isAnalyzing, setIsAnalyzing] = useState(false)

  const refreshData = useCallback(async () => {
    try {
      const [q, v] = await Promise.all([
        Api.marketQuote(symbol),
        Api.accountValuation(`user:${playerId}`)
      ])
      setQuote(q)
      setVal(v)
      if (orderType === 'LIMIT' && !price && q.last_price) {
        setPrice(String(q.last_price))
      }
    } catch (e) {
      console.error('Failed to fetch trade data', e)
    }
  }, [playerId, symbol, orderType, price])

  useEffect(() => {
    refreshData()
    const t = setInterval(refreshData, 3000)
    return () => clearInterval(t)
  }, [refreshData])

  useEffect(() => {
    if (!symbol) return
    setIsAnalyzing(true)
    const timer = setTimeout(() => {
      const rand = Math.random()
      setAiSuggestion({
        action: rand > 0.5 ? 'STRONGLY_BUY' : 'CAUTIOUS_SELL',
        confidence: Math.floor(70 + Math.random() * 25),
        reason: rand > 0.5 ? 'BULLISH_SENTIMENT_DETECTED' : 'RESISTANCE_LEVEL_APPROACHING'
      })
      setIsAnalyzing(false)
    }, 1500)
    return () => clearTimeout(timer)
  }, [symbol, quote?.last_price])

  const availableCash = val?.cash ?? 0
  const availablePos = val?.positions ? (val.positions[symbol] ?? 0) : 0
  
  const estimatedValue = useMemo(() => {
    const p = orderType === 'MARKET' ? (quote?.last_price ?? 0) : Number(price)
    const q = Number(quantity)
    if (isNaN(p) || isNaN(q)) return 0
    return p * q
  }, [price, quantity, orderType, quote?.last_price])

  const canSubmit = useMemo(() => {
    const q = Number(quantity)
    if (isNaN(q) || q <= 0) return false
    if (orderType === 'LIMIT') {
      const p = Number(price)
      if (isNaN(p) || p <= 0) return false
    }
    if (side === 'BUY' && estimatedValue > availableCash) return false
    if (side === 'SELL' && q > availablePos) return false
    return !!playerId && !!symbol
  }, [side, orderType, price, quantity, estimatedValue, availableCash, availablePos, playerId, symbol])

  async function handleSubmit(): Promise<void> {
    if (!canSubmit) return
    setErr('')
    setLoading(true)
    try {
      if (orderType === 'LIMIT') {
        const r = await Api.submitLimitOrder({
          player_id: playerId,
          symbol,
          side,
          price: Number(price),
          quantity: Number(quantity),
        })
        notify('success', `ORDER_EXECUTED: ${r.order_id}`)
      } else {
        await Api.submitMarketOrder({
          player_id: playerId,
          symbol,
          side,
          quantity: Number(quantity),
        })
        notify('success', 'MARKET_ORDER_SUBMITTED')
      }
      refreshData()
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : (e instanceof Error ? e.message : String(e))
      setErr(msg)
      notify('error', msg)
    } finally {
      setLoading(false)
    }
  }

  const setPercent = (pct: number) => {
    if (side === 'BUY') {
      const p = orderType === 'MARKET' ? (quote?.last_price ?? 0) : Number(price)
      if (p > 0) {
        const maxQty = Math.floor(availableCash / p)
        setQuantity(String(Math.floor(maxQty * pct)))
      }
    } else {
      setQuantity(String(Math.floor(availablePos * pct)))
    }
  }

  return (
    <CyberWidget 
      title={`TRADE_EXECUTION: ${symbol}`} 
      subtitle="QUANTUM_ORDER_ROUTING"
    >
      {err && <div style={{ color: 'var(--terminal-error)', fontSize: '12px', marginBottom: '10px', background: 'rgba(239, 68, 68, 0.1)', padding: '8px', borderLeft: '3px solid var(--terminal-error)' }}>[ERR]: {err}</div>}
      
      <div style={{ display: 'flex', gap: '2px', background: 'var(--terminal-bg)', padding: '2px', borderRadius: '4px', marginBottom: '15px', border: '1px solid var(--terminal-border)' }}>
        <button 
          onClick={() => setSide('BUY')}
          className={`cyber-button ${side === 'BUY' ? 'active' : ''}`}
          style={{ flex: 1, border: 'none', background: side === 'BUY' ? 'var(--terminal-success)' : 'transparent', color: side === 'BUY' ? '#fff' : '#94a3b8' }}
        >BUY</button>
        <button 
          onClick={() => setSide('SELL')}
          className={`cyber-button ${side === 'SELL' ? 'active' : ''}`}
          style={{ flex: 1, border: 'none', background: side === 'SELL' ? 'var(--terminal-error)' : 'transparent', color: side === 'SELL' ? '#fff' : '#94a3b8' }}
        >SELL</button>
      </div>

      <div style={{ display: 'grid', gap: '12px' }}>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px' }}>
          <div>
            <div style={{ fontSize: '10px', color: '#64748b', marginBottom: '4px' }}>ORDER_TYPE</div>
            <select 
              className="cyber-input" 
              value={orderType} 
              onChange={e => setOrderType(e.target.value as 'LIMIT' | 'MARKET')}
              style={{ width: '100%', height: '32px' }}
            >
              <option value="LIMIT">LIMIT</option>
              <option value="MARKET">MARKET</option>
            </select>
          </div>
          {orderType === 'LIMIT' && (
            <div>
              <div style={{ fontSize: '10px', color: '#64748b', marginBottom: '4px' }}>PRICE</div>
              <input 
                className="cyber-input"
                type="number" 
                value={price} 
                onChange={e => setPrice(e.target.value)}
                style={{ width: '100%', height: '32px', boxSizing: 'border-box' }}
              />
            </div>
          )}
        </div>

        <div>
          <div style={{ fontSize: '10px', color: '#64748b', marginBottom: '4px' }}>QUANTITY</div>
          <input 
            className="cyber-input"
            type="number" 
            value={quantity} 
            onChange={e => setQuantity(e.target.value)}
            style={{ width: '100%', height: '32px', boxSizing: 'border-box' }}
          />
        </div>

        <div style={{ display: 'flex', gap: '4px' }}>
          {[0.25, 0.5, 0.75, 1].map(p => (
            <button 
              key={p} 
              onClick={() => setPercent(p)}
              className="cyber-button"
              style={{ flex: 1, fontSize: '11px', padding: '4px 0' }}
            >
              {p * 100}%
            </button>
          ))}
        </div>

        <div style={{ padding: '10px', background: 'rgba(0,0,0,0.2)', fontSize: '11px', border: '1px solid var(--terminal-border)', borderRadius: '4px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '6px' }}>
            <span style={{ color: '#64748b' }}>TOTAL_ESTIMATED</span>
            <span style={{ fontWeight: '700', color: '#fff' }}>${estimatedValue.toFixed(2)}</span>
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between' }}>
            <span style={{ color: '#64748b' }}>{side === 'BUY' ? 'AVAILABLE_CASH' : 'AVAILABLE_POS'}</span>
            <span style={{ fontWeight: '700', color: (side === 'BUY' ? estimatedValue > availableCash : Number(quantity) > availablePos) ? 'var(--terminal-error)' : 'var(--terminal-success)' }}>
              {side === 'BUY' ? `$${availableCash.toLocaleString()}` : `${availablePos.toLocaleString()} unit`}
            </span>
          </div>
        </div>

        {isFocused && (
          <div style={{ 
            marginTop: '5px', 
            padding: '10px', 
            background: 'rgba(59, 130, 246, 0.05)', 
            border: '1px solid rgba(59, 130, 246, 0.2)', 
            borderRadius: '4px' 
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
              <span style={{ fontSize: '9px', color: 'var(--terminal-info)', fontWeight: 'bold' }}>NEURAL_TRADE_ADVISOR</span>
              <div style={{ width: '8px', height: '8px', borderRadius: '50%', background: isAnalyzing ? 'var(--terminal-warn)' : 'var(--terminal-success)', animation: isAnalyzing ? 'blink-anim 0.5s step-end infinite' : 'none' }} />
            </div>
            
            {isAnalyzing ? (
              <div style={{ fontSize: '10px', color: '#64748b', fontFamily: 'monospace' }}>ANALYZING_MARKET_VECTORS...</div>
            ) : aiSuggestion ? (
              <div>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
                  <span style={{ fontSize: '11px', color: aiSuggestion.action.includes('BUY') ? 'var(--terminal-success)' : 'var(--terminal-error)', fontWeight: 'bold' }}>
                    {aiSuggestion.action}
                  </span>
                  <span style={{ fontSize: '10px', color: '#fff', fontFamily: 'monospace' }}>{aiSuggestion.confidence}%_CONF</span>
                </div>
                <div style={{ fontSize: '9px', color: '#94a3b8', fontFamily: 'monospace', fontStyle: 'italic' }}>
                  {aiSuggestion.reason}
                </div>
              </div>
            ) : null}
          </div>
        )}

        <button 
          className="cyber-button"
          disabled={!canSubmit || loading}
          onClick={handleSubmit}
          style={{ 
            width: '100%', 
            height: '40px',
            background: side === 'BUY' ? 'var(--terminal-success)' : 'var(--terminal-error)', 
            color: '#fff',
            fontWeight: '700',
            opacity: canSubmit ? 1 : 0.4,
            border: 'none',
            fontSize: '14px',
            marginTop: '5px'
          }}
        >
          {loading ? 'EXECUTING...' : `PLACE_${side}_ORDER`}
        </button>
      </div>
    </CyberWidget>
  )
}
