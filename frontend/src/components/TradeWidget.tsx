import { useEffect, useMemo, useState, useCallback } from 'react'
import { Api, ApiError, type AccountValuationResponse, type MarketQuoteResponse } from '../api'
import { useAppSession } from '../app/context'
import { useNotification } from '../app/NotificationContext'
import CyberWidget from './CyberWidget'

export default function TradeWidget() {
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
      {err && <div style={{ color: 'var(--terminal-error)', fontSize: '11px', marginBottom: 10 }}>[ERR]: {err}</div>}
      
      <div style={{ display: 'flex', gap: 2, background: '#111', padding: 2, border: '1px solid #333', marginBottom: 15 }}>
        <button 
          onClick={() => setSide('BUY')}
          className="cyber-button"
          style={{ flex: 1, border: 'none', background: side === 'BUY' ? '#52c41a' : 'transparent', color: side === 'BUY' ? '#000' : '#52c41a', fontSize: '11px' }}
        >BUY</button>
        <button 
          onClick={() => setSide('SELL')}
          className="cyber-button"
          style={{ flex: 1, border: 'none', background: side === 'SELL' ? '#ff4d4f' : 'transparent', color: side === 'SELL' ? '#fff' : '#ff4d4f', fontSize: '11px' }}
        >SELL</button>
      </div>

      <div style={{ display: 'grid', gap: 10 }}>
        <div style={{ display: 'flex', gap: 10 }}>
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: '9px', opacity: 0.6, marginBottom: 4 }}>TYPE</div>
            <select 
              className="cyber-input" 
              value={orderType} 
              onChange={e => setOrderType(e.target.value as 'LIMIT' | 'MARKET')}
              style={{ width: '100%', fontSize: '11px' }}
            >
              <option value="LIMIT">LIMIT</option>
              <option value="MARKET">MARKET</option>
            </select>
          </div>
          {orderType === 'LIMIT' && (
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: '9px', opacity: 0.6, marginBottom: 4 }}>PRICE</div>
              <input 
                className="cyber-input"
                type="number" 
                value={price} 
                onChange={e => setPrice(e.target.value)}
                style={{ width: '100%', fontSize: '11px' }}
              />
            </div>
          )}
        </div>

        <div>
          <div style={{ fontSize: '9px', opacity: 0.6, marginBottom: 4 }}>QUANTITY</div>
          <input 
            className="cyber-input"
            type="number" 
            value={quantity} 
            onChange={e => setQuantity(e.target.value)}
            style={{ width: '100%', fontSize: '11px' }}
          />
        </div>

        <div style={{ display: 'flex', gap: 4 }}>
          {[0.25, 0.5, 0.75, 1].map(p => (
            <button 
              key={p} 
              onClick={() => setPercent(p)}
              className="cyber-button"
              style={{ flex: 1, fontSize: '9px', padding: '2px' }}
            >
              {p * 100}%
            </button>
          ))}
        </div>

        <div style={{ padding: '8px', background: 'rgba(255,255,255,0.05)', fontSize: '10px', border: '1px solid #222' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
            <span style={{ opacity: 0.6 }}>TOTAL_EST:</span>
            <span style={{ fontWeight: 'bold' }}>{estimatedValue.toFixed(2)}</span>
          </div>
          <div style={{ display: 'flex', justifyContent: 'space-between' }}>
            <span style={{ opacity: 0.6 }}>AVAILABLE:</span>
            <span style={{ fontWeight: 'bold', color: (side === 'BUY' ? estimatedValue > availableCash : Number(quantity) > availablePos) ? 'var(--terminal-error)' : 'inherit' }}>
              {side === 'BUY' ? availableCash.toFixed(2) : availablePos.toFixed(2)}
            </span>
          </div>
        </div>

        <button 
          className="cyber-button"
          disabled={!canSubmit || loading}
          onClick={handleSubmit}
          style={{ 
            width: '100%', 
            padding: '10px', 
            background: side === 'BUY' ? '#52c41a' : '#ff4d4f', 
            color: side === 'BUY' ? '#000' : '#fff',
            fontWeight: 'bold',
            opacity: canSubmit ? 1 : 0.3,
            border: 'none',
            marginTop: 5
          }}
        >
          {loading ? 'EXECUTING...' : `CONFIRM_${side}_${symbol}`}
        </button>
      </div>
    </CyberWidget>
  )
}
