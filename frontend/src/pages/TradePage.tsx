import { useState } from 'react'
import { Api, ApiError } from '../api'
import { useAppSession } from '../app/context'

export default function TradePage() {
  const { playerId, symbol } = useAppSession()
  const [err, setErr] = useState<string>('')
  const [ok, setOk] = useState<string>('')

  const [limitSide, setLimitSide] = useState<string>('BUY')
  const [limitPrice, setLimitPrice] = useState<number>(10)
  const [limitQty, setLimitQty] = useState<number>(1)

  const [mktSide, setMktSide] = useState<string>('BUY')
  const [mktQty, setMktQty] = useState<number>(1)

  async function submitLimit(): Promise<void> {
    setErr('')
    setOk('')
    try {
      const r = await Api.submitLimitOrder({
        player_id: playerId,
        symbol,
        side: limitSide,
        price: Number(limitPrice),
        quantity: Number(limitQty),
      })
      setOk(`limit order submitted: ${r.order_id}`)
    } catch (e) {
      if (e instanceof ApiError) setErr(`${e.status}: ${e.message}`)
      else setErr(e instanceof Error ? e.message : String(e))
    }
  }

  async function submitMarket(): Promise<void> {
    setErr('')
    setOk('')
    try {
      await Api.submitMarketOrder({
        player_id: playerId,
        symbol,
        side: mktSide,
        quantity: Number(mktQty),
      })
      setOk('market order submitted')
    } catch (e) {
      if (e instanceof ApiError) setErr(`${e.status}: ${e.message}`)
      else setErr(e instanceof Error ? e.message : String(e))
    }
  }

  return (
    <div style={{ display: 'grid', gap: 12 }}>
      <div className="card" style={{ textAlign: 'left' }}>
        <h3 style={{ marginTop: 0 }}>Submit Orders</h3>
        {err ? <div style={{ color: 'crimson' }}>{err}</div> : null}
        {ok ? <div style={{ color: 'green' }}>{ok}</div> : null}

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
          <div>
            <h4>Limit</h4>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
              <select value={limitSide} onChange={(e) => setLimitSide(e.target.value)}>
                <option value="BUY">BUY</option>
                <option value="SELL">SELL</option>
              </select>
              <input
                type="number"
                value={limitPrice}
                onChange={(e) => setLimitPrice(Number(e.target.value))}
                step={0.01}
              />
              <input type="number" value={limitQty} onChange={(e) => setLimitQty(Number(e.target.value))} step={1} />
              <button onClick={submitLimit}>Submit</button>
            </div>
          </div>

          <div>
            <h4>Market</h4>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
              <select value={mktSide} onChange={(e) => setMktSide(e.target.value)}>
                <option value="BUY">BUY</option>
                <option value="SELL">SELL</option>
              </select>
              <input type="number" value={mktQty} onChange={(e) => setMktQty(Number(e.target.value))} step={1} />
              <button onClick={submitMarket}>Submit</button>
            </div>
          </div>
        </div>
      </div>

      <div className="card" style={{ textAlign: 'left' }}>
        <h3 style={{ marginTop: 0 }}>Tips</h3>
        <div>
          Current context:
          <pre style={{ whiteSpace: 'pre-wrap' }}>{JSON.stringify({ playerId, symbol }, null, 2)}</pre>
        </div>
      </div>
    </div>
  )
}
