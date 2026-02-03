import { useEffect, useState } from 'react'
import {
  Api,
  ApiError,
  type NewsCreateCardResponse,
  type NewsEmitVariantResponse,
  type NewsInboxResponse,
  type NewsStorePurchaseResponse,
} from '../api'
import { useAppSession } from '../app/context'

export default function NewsPage() {
  const { playerId, symbol } = useAppSession()
  const [err, setErr] = useState<string>('')
  const [ok, setOk] = useState<string>('')

  const [inbox, setInbox] = useState<NewsInboxResponse | null>(null)

  const [cardKind, setCardKind] = useState<string>('RUMOR')
  const [cardText, setCardText] = useState<string>('')
  const [lastCard, setLastCard] = useState<NewsCreateCardResponse | null>(null)
  const [lastVariant, setLastVariant] = useState<NewsEmitVariantResponse | null>(null)

  const [purchaseKind, setPurchaseKind] = useState<string>('RUMOR')
  const [purchasePrice, setPurchasePrice] = useState<number>(100)
  const [purchaseText, setPurchaseText] = useState<string>('')
  const [purchaseRes, setPurchaseRes] = useState<NewsStorePurchaseResponse | null>(null)

  async function refreshInbox(): Promise<void> {
    setErr('')
    try {
      const r = await Api.newsInbox(playerId, 50)
      setInbox(r)
    } catch (e) {
      if (e instanceof ApiError) setErr(`${e.status}: ${e.message}`)
      else setErr(e instanceof Error ? e.message : String(e))
    }
  }

  async function createCardAndVariant(): Promise<void> {
    setErr('')
    setOk('')
    try {
      const card = await Api.newsCreateCard({
        actor_id: `user:${playerId}`,
        kind: cardKind,
        symbols: [symbol],
        tags: [],
        truth_payload: null,
      })
      setLastCard(card)

      const v = await Api.newsEmitVariant({
        card_id: card.card_id,
        author_id: `user:${playerId}`,
        text: cardText,
        parent_variant_id: null,
        influence_cost: 0.0,
        risk_roll: null,
      })
      setLastVariant(v)
      setOk(`created card=${card.card_id}, variant=${v.variant_id}`)
      await refreshInbox()
    } catch (e) {
      if (e instanceof ApiError) setErr(`${e.status}: ${e.message}`)
      else setErr(e instanceof Error ? e.message : String(e))
    }
  }

  async function purchase(): Promise<void> {
    setErr('')
    setOk('')
    try {
      const r = await Api.newsStorePurchase({
        buyer_user_id: `user:${playerId}`,
        kind: purchaseKind,
        price_cash: Number(purchasePrice),
        symbols: [symbol],
        tags: [],
        initial_text: purchaseText,
      })
      setPurchaseRes(r)
      setOk(`purchased: kind=${r.kind}, card=${r.card_id}, variant=${r.variant_id}, chain=${r.chain_id}`)
      await refreshInbox()
    } catch (e) {
      if (e instanceof ApiError) setErr(`${e.status}: ${e.message}`)
      else setErr(e instanceof Error ? e.message : String(e))
    }
  }

  useEffect(() => {
    refreshInbox()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [playerId])

  return (
    <div style={{ display: 'grid', gap: 12 }}>
      <div className="card" style={{ textAlign: 'left' }}>
        <h3 style={{ marginTop: 0 }}>Inbox</h3>
        {err ? <div style={{ color: 'crimson' }}>{err}</div> : null}
        {ok ? <div style={{ color: 'green' }}>{ok}</div> : null}
        <button onClick={refreshInbox}>Refresh</button>
        <pre style={{ whiteSpace: 'pre-wrap' }}>{inbox ? JSON.stringify(inbox, null, 2) : 'N/A'}</pre>
      </div>

      <div className="card" style={{ textAlign: 'left' }}>
        <h3 style={{ marginTop: 0 }}>Create Card + Emit Variant</h3>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
          <label>
            Kind{' '}
            <input value={cardKind} onChange={(e) => setCardKind(e.target.value)} />
          </label>
          <input
            style={{ minWidth: 320 }}
            placeholder="text"
            value={cardText}
            onChange={(e) => setCardText(e.target.value)}
          />
          <button onClick={createCardAndVariant}>Submit</button>
        </div>
        <pre style={{ whiteSpace: 'pre-wrap' }}>{JSON.stringify({ lastCard, lastVariant }, null, 2)}</pre>
      </div>

      <div className="card" style={{ textAlign: 'left' }}>
        <h3 style={{ marginTop: 0 }}>Store Purchase</h3>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
          <label>
            Kind{' '}
            <input value={purchaseKind} onChange={(e) => setPurchaseKind(e.target.value)} />
          </label>
          <label>
            Price{' '}
            <input type="number" value={purchasePrice} onChange={(e) => setPurchasePrice(Number(e.target.value))} />
          </label>
          <input
            style={{ minWidth: 320 }}
            placeholder="initial_text"
            value={purchaseText}
            onChange={(e) => setPurchaseText(e.target.value)}
          />
          <button onClick={purchase}>Buy</button>
        </div>
        <pre style={{ whiteSpace: 'pre-wrap' }}>{purchaseRes ? JSON.stringify(purchaseRes, null, 2) : 'N/A'}</pre>
      </div>
    </div>
  )
}
