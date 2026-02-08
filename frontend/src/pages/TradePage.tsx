import { useEffect, useMemo, useState } from 'react'
import { Api, ApiError, type AccountValuationResponse, type MarketQuoteResponse } from '../api'
import { useAppSession } from '../app/context'
import { useNotification } from '../app/NotificationContext'

export default function TradePage() {
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

  const [recentOrders, setRecentOrders] = useState<Array<{ id: string; side: string; type: string; price?: number; qty: number; status: string; time: string }>>([])

  const playerIdOk = useMemo(() => {
    return !!playerId && /^[a-zA-Z0-9_]{3,20}$/.test(playerId)
  }, [playerId])

  const refreshData = useMemo(() => async () => {
    if (!playerIdOk) return
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
  }, [playerIdOk, playerId, symbol, orderType, price])

  useEffect(() => {
    if (!playerIdOk) return
    refreshData()
    const t = setInterval(refreshData, 3000)
    return () => clearInterval(t)
  }, [playerIdOk, refreshData])

  const availableCash = val?.cash ?? 0
  const availablePos = val?.positions ? (val.positions[symbol] ?? 0) : 0
  
  const formattedTotalValue = useMemo(() => {
    if (typeof val?.total_value === 'number') {
      return val.total_value.toLocaleString();
    }
    return '--';
  }, [val?.total_value]);

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
    return true
  }, [side, orderType, price, quantity, estimatedValue, availableCash, availablePos])

  async function handleSubmit(): Promise<void> {
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
        notify('success', `限价单已提交: ${r.order_id}`)
        setRecentOrders(prev => [{
          id: r.order_id,
          side,
          type: 'LIMIT',
          price: Number(price),
          qty: Number(quantity),
          status: 'SUBMITTED',
          time: new Date().toLocaleTimeString()
        }, ...prev].slice(0, 10))
      } else {
        await Api.submitMarketOrder({
          player_id: playerId,
          symbol,
          side,
          quantity: Number(quantity),
        })
        notify('success', '市价单已提交')
        setRecentOrders(prev => [{
          id: `mkt_${Math.random().toString(36).slice(2, 7)}`,
          side,
          type: 'MARKET',
          qty: Number(quantity),
          status: 'SUBMITTED',
          time: new Date().toLocaleTimeString()
        }, ...prev].slice(0, 10))
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
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 350px', gap: 20 }}>
      <div className="card" style={{ textAlign: 'left' }}>
        <h3 style={{ marginTop: 0 }}>交易执行 - {symbol}</h3>
        
        {err ? <div style={{ color: '#f5222d', background: '#fff1f0', padding: '8px 12px', borderRadius: 4, marginBottom: 15, border: '1px solid #ffccc7' }}>{err}</div> : null}

        <div style={{ display: 'flex', gap: 2, background: '#f0f0f0', padding: 4, borderRadius: 8, marginBottom: 20 }}>
          <button 
            onClick={() => setSide('BUY')}
            style={{ flex: 1, padding: '8px', border: 'none', borderRadius: 6, cursor: 'pointer', background: side === 'BUY' ? '#52c41a' : 'transparent', color: side === 'BUY' ? '#fff' : '#666', fontWeight: 600 }}
          >买入 (Long)</button>
          <button 
            onClick={() => setSide('SELL')}
            style={{ flex: 1, padding: '8px', border: 'none', borderRadius: 6, cursor: 'pointer', background: side === 'SELL' ? '#f5222d' : 'transparent', color: side === 'SELL' ? '#fff' : '#666', fontWeight: 600 }}
          >卖出 (Short/Close)</button>
        </div>

        <div style={{ display: 'grid', gap: 15 }}>
          <div style={{ display: 'flex', gap: 15 }}>
            <label style={{ flex: 1 }}>
              <div style={{ marginBottom: 5, color: '#888', fontSize: 13 }}>订单类型</div>
              <select 
                value={orderType} 
                onChange={e => setOrderType(e.target.value as 'LIMIT' | 'MARKET')} 
                style={{ width: '100%', padding: '8px', borderRadius: 4, border: '1px solid #ddd' }}
              >
                <option value="LIMIT">限价单 (Limit)</option>
                <option value="MARKET">市价单 (Market)</option>
              </select>
            </label>
            {orderType === 'LIMIT' && (
              <label style={{ flex: 1 }}>
                <div style={{ marginBottom: 5, color: '#888', fontSize: 13 }}>委托价格</div>
                <input 
                  type="number" 
                  value={price} 
                  onChange={e => setPrice(e.target.value)} 
                  step="0.01"
                  style={{ width: '100%', padding: '8px', borderRadius: 4, border: '1px solid #ddd', boxSizing: 'border-box' }}
                />
              </label>
            )}
          </div>

          <label>
            <div style={{ marginBottom: 5, color: '#888', fontSize: 13 }}>委托数量</div>
            <input 
              type="number" 
              value={quantity} 
              onChange={e => setQuantity(e.target.value)} 
              style={{ width: '100%', padding: '8px', borderRadius: 4, border: '1px solid #ddd', boxSizing: 'border-box' }}
            />
          </label>

          <div style={{ display: 'flex', gap: 8 }}>
            {[0.25, 0.5, 0.75, 1].map(p => (
              <button 
                key={p} 
                onClick={() => setPercent(p)}
                style={{ flex: 1, padding: '4px', fontSize: 12, background: '#fff', border: '1px solid #ddd', borderRadius: 4, cursor: 'pointer' }}
              >
                {p * 100}%
              </button>
            ))}
          </div>

          <div style={{ background: '#fafafa', padding: 15, borderRadius: 8, fontSize: 14 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
              <span style={{ color: '#888' }}>预估总额</span>
              <span style={{ fontWeight: 600 }}>{estimatedValue.toLocaleString()}</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <span style={{ color: '#888' }}>{side === 'BUY' ? '可用现金' : '可用持仓'}</span>
              <span style={{ fontWeight: 600, color: (side === 'BUY' ? estimatedValue > availableCash : Number(quantity) > availablePos) ? '#f5222d' : 'inherit' }}>
                {side === 'BUY' ? availableCash.toLocaleString() : availablePos.toLocaleString()}
              </span>
            </div>
          </div>

          <button 
            disabled={!canSubmit || loading}
            onClick={handleSubmit}
            style={{ 
              width: '100%', 
              padding: '12px', 
              background: side === 'BUY' ? '#52c41a' : '#f5222d', 
              color: '#fff', 
              border: 'none', 
              borderRadius: 8, 
              fontSize: 16, 
              fontWeight: 700, 
              cursor: canSubmit ? 'pointer' : 'not-allowed',
              opacity: canSubmit ? 1 : 0.5,
              marginTop: 10
            }}
          >
            {loading ? '提交中...' : `${side === 'BUY' ? '立即买入' : '立即卖出'} ${symbol}`}
          </button>
        </div>
      </div>

      <div style={{ display: 'grid', gap: 20, alignContent: 'start' }}>
        <div className="card" style={{ textAlign: 'left' }}>
          <h4 style={{ marginTop: 0, marginBottom: 10 }}>当前行情</h4>
          <div style={{ display: 'grid', gap: 10, fontSize: 14 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <span style={{ color: '#888' }}>最新价</span>
              <span style={{ fontWeight: 600 }}>{quote?.last_price ?? '--'}</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <span style={{ color: '#888' }}>24h涨跌</span>
              <span style={{ fontWeight: 600, color: (quote?.change_pct ?? 0) >= 0 ? '#52c41a' : '#f5222d' }}>
                {(quote?.change_pct ?? 0 * 100).toFixed(2)}%
              </span>
            </div>
          </div>
        </div>

        <div className="card" style={{ textAlign: 'left' }}>
          <h4 style={{ marginTop: 0, marginBottom: 10 }}>账户状态</h4>
          <div style={{ display: 'grid', gap: 10, fontSize: 14 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <span style={{ color: '#888' }}>总资产</span>
              <span style={{ fontWeight: 600 }}>{formattedTotalValue}</span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <span style={{ color: '#888' }}>当前持仓</span>
              <span style={{ fontWeight: 600 }}>{availablePos}</span>
            </div>
          </div>
        </div>

        <div className="card" style={{ textAlign: 'left' }}>
          <h4 style={{ marginTop: 0, marginBottom: 10 }}>最近委托</h4>
          {recentOrders.length ? (
            <div style={{ display: 'grid', gap: 8, fontSize: 12 }}>
              {recentOrders.map(o => (
                <div key={o.id} style={{ padding: '8px', background: '#f9f9f9', borderRadius: 4, borderLeft: `3px solid ${o.side === 'BUY' ? '#52c41a' : '#f5222d'}` }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontWeight: 600 }}>
                    <span>{o.side} {o.type}</span>
                    <span style={{ color: '#888' }}>{o.time}</span>
                  </div>
                  <div style={{ marginTop: 4 }}>
                    {o.qty} @ {o.price ?? 'MKT'}
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div style={{ color: '#999', fontSize: 13, textAlign: 'center', padding: '10px 0' }}>暂无记录</div>
          )}
        </div>
      </div>
    </div>
  )
}
