import { useEffect, useMemo, useRef, useState } from 'react'
import {
  Api,
  ApiError,
  type NewsCreateCardResponse,
  type NewsEmitVariantResponse,
  type NewsInboxResponse,
  type NewsStorePurchaseResponse,
} from '../api'
import { useAppSession } from '../app/context'
import { WsClient } from '../api'

function getEventType(payload: unknown): string | null {
  if (!payload || typeof payload !== 'object') return null
  const v = (payload as Record<string, unknown>).event_type
  return typeof v === 'string' ? v : null
}

export default function NewsPage() {
  const { playerId, symbol } = useAppSession()
  const [err, setErr] = useState<string>('')
  const [ok, setOk] = useState<string>('')

  const [inbox, setInbox] = useState<NewsInboxResponse | null>(null)

  const [cardKind, setCardKind] = useState<string>('RUMOR')
  const [cardText, setCardText] = useState<string>('')
  const [lastCard, setLastCard] = useState<NewsCreateCardResponse | null>(null)
  const [lastVariant, setLastVariant] = useState<NewsEmitVariantResponse | null>(null)

  const [propLimit, setPropLimit] = useState<number>(50)
  const [propSpendCash, setPropSpendCash] = useState<string>('')

  const [purchaseKind, setPurchaseKind] = useState<string>('RUMOR')
  const [purchasePrice, setPurchasePrice] = useState<number>(100)
  const [purchaseText, setPurchaseText] = useState<string>('')
  const [purchaseRes, setPurchaseRes] = useState<NewsStorePurchaseResponse | null>(null)

  const ws = useMemo(() => new WsClient({ baseUrl: import.meta.env.VITE_API_BASE_URL }), [])
  const refreshTimerRef = useRef<number | null>(null)

  function scheduleRefreshInbox(): void {
    if (refreshTimerRef.current !== null) return
    refreshTimerRef.current = window.setTimeout(() => {
      refreshTimerRef.current = null
      refreshInbox()
    }, 500)
  }

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

  useEffect(() => {
    ws.connect('events', (payload) => {
      const t = getEventType(payload)
      if (typeof t === 'string' && t.startsWith('NEWS_')) {
        scheduleRefreshInbox()
      }
    })
    return () => {
      ws.close()
      if (refreshTimerRef.current !== null) {
        window.clearTimeout(refreshTimerRef.current)
        refreshTimerRef.current = null
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  async function propagateLast(): Promise<void> {
    setErr('')
    setOk('')
    if (!lastVariant?.variant_id) {
      setErr('no variant_id yet (create card + emit first)')
      return
    }
    const spendCash = propSpendCash.trim() === '' ? undefined : Number(propSpendCash)
    if (spendCash !== undefined && (!Number.isFinite(spendCash) || spendCash <= 0)) {
      setErr('spend_cash must be a positive number')
      return
    }
    try {
      const r = await Api.newsPropagate({
        variant_id: lastVariant.variant_id,
        from_actor_id: `user:${playerId}`,
        visibility_level: 'NORMAL',
        spend_influence: 0.0,
        spend_cash: spendCash,
        limit: Number(propLimit),
      })
      setOk(`propagated: delivered=${r.delivered}`)
      await refreshInbox()
    } catch (e) {
      if (e instanceof ApiError) setErr(`${e.status}: ${e.message}`)
      else setErr(e instanceof Error ? e.message : String(e))
    }
  }

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

        <div style={{ marginTop: 10 }}>
          <h4 style={{ margin: '10px 0 6px' }}>Propagate (last variant)</h4>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
            <label>
              limit <input type="number" value={propLimit} onChange={(e) => setPropLimit(Number(e.target.value))} />
            </label>
            <label>
              spend_cash(optional){' '}
              <input
                value={propSpendCash}
                onChange={(e) => setPropSpendCash(e.target.value)}
                placeholder=""
                style={{ width: 120 }}
              />
            </label>
            <button onClick={propagateLast}>Propagate</button>
          </div>
        </div>
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
