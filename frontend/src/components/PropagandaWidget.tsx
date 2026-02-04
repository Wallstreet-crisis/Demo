import { useState, useEffect, useCallback } from 'react'
import { Api, ApiError, type NewsStoreCatalogItem } from '../api'
import { useAppSession } from '../app/context'
import { useNotification } from '../app/NotificationContext'
import CyberWidget from './CyberWidget'

export default function PropagandaWidget() {
  const { playerId, symbol } = useAppSession()
  const { notify } = useNotification()
  
  const [loading, setLoading] = useState(false)
  const [ownedCards, setOwnedCards] = useState<string[]>([])

  const [storeItems, setStoreItems] = useState<NewsStoreCatalogItem[]>([])
  const [loadingStore, setLoadingStore] = useState(false)
  
  // Purchase
  const [purchaseKind, setPurchaseKind] = useState('RUMOR')
  const [purchasePrice, setPurchasePrice] = useState(100)
  const [purchaseText, setPurchaseText] = useState('')
  const [purchasePresetId, setPurchasePresetId] = useState('')

  // Propagation
  const [targetVariantId, setTargetVariantId] = useState('')
  const [propLimit, setPropLimit] = useState(50)
  const [propSpendCash, setPropSpendCash] = useState('')

  const refreshOwned = useCallback(async () => {
    if (!playerId) return
    try {
      const r = await Api.newsOwnershipList(`user:${playerId}`)
      setOwnedCards(r.cards || [])
    } catch (e) {
      console.error('Failed to fetch cards', e)
    }
  }, [playerId])

  useEffect(() => {
    refreshOwned()
  }, [refreshOwned])

  const refreshStoreCatalog = useCallback(async () => {
    setLoadingStore(true)
    try {
      const r = await Api.newsStoreCatalog()
      const items = Array.isArray(r.items) ? r.items : []
      setStoreItems(items)

      if (items.length > 0) {
        const selected = items.find((x) => x.kind === purchaseKind) ?? items[0]
        if (selected) {
          setPurchaseKind(selected.kind)
          setPurchasePrice(Number(selected.price_cash))
          const p0 = selected.presets?.[0]?.preset_id ?? ''
          setPurchasePresetId(p0)
          setPurchaseText(String(selected.presets?.[0]?.text ?? selected.preview_text ?? ''))
        }
      }
    } catch (e) {
      console.error('Failed to fetch store catalog', e)
      setStoreItems([])
    } finally {
      setLoadingStore(false)
    }
  }, [purchaseKind])

  useEffect(() => {
    refreshStoreCatalog()
  }, [refreshStoreCatalog])

  useEffect(() => {
    const selected = storeItems.find((x) => x.kind === purchaseKind) ?? null
    if (!selected) return
    setPurchasePrice(Number(selected.price_cash))
    const nextPreset = selected.presets?.find((p) => p.preset_id === purchasePresetId) ?? selected.presets?.[0] ?? null
    if (nextPreset) {
      setPurchasePresetId(nextPreset.preset_id)
      setPurchaseText(String(nextPreset.text ?? ''))
    } else {
      setPurchasePresetId('')
      setPurchaseText(String(selected.preview_text ?? ''))
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [purchaseKind, storeItems])

  useEffect(() => {
    const selected = storeItems.find((x) => x.kind === purchaseKind) ?? null
    if (!selected) return
    const chosen = selected.presets?.find((p) => p.preset_id === purchasePresetId) ?? null
    if (chosen) setPurchaseText(String(chosen.text ?? ''))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [purchasePresetId])

  const handlePurchase = async () => {
    setLoading(true)
    try {
      const selected = storeItems.find((x) => x.kind === purchaseKind) ?? null
      const reqSymbols = selected?.requires_symbols ? [symbol] : []
      const presetId = purchasePresetId || (selected?.presets?.[0]?.preset_id ?? null)
      const r = await Api.newsStorePurchase({
        buyer_user_id: `user:${playerId}`,
        kind: purchaseKind,
        price_cash: purchasePrice,
        preset_id: presetId,
        symbols: reqSymbols,
        tags: [],
      })
      notify('success', `INTEL_ACQUIRED: ${r.kind}`)
      if (r.variant_id) setTargetVariantId(r.variant_id)
      refreshOwned()
      setPurchaseText('')
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : String(e)
      notify('error', msg)
    } finally {
      setLoading(false)
    }
  }

  const handlePropagate = async () => {
    if (!targetVariantId) return
    setLoading(true)
    try {
      const r = await Api.newsPropagate({
        variant_id: targetVariantId,
        from_actor_id: `user:${playerId}`,
        visibility_level: 'NORMAL',
        spend_influence: 0.0,
        spend_cash: propSpendCash ? Number(propSpendCash) : 0,
        limit: propLimit,
      })
      notify('success', `PROPAGATION_SUCCESS: DELIVERED_${r.delivered}`)
      setTargetVariantId('')
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : String(e)
      notify('error', msg)
    } finally {
      setLoading(false)
    }
  }

  return (
    <CyberWidget 
      title="PROPAGANDA_CENTER" 
      subtitle="MARKET_SENTIMENT_ENGINE"
      actions={<button className="cyber-button" style={{ fontSize: '11px', padding: '2px 8px' }} onClick={refreshOwned}>SYNC</button>}
    >
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '15px' }}>
        {/* News Store */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
          <div style={{ fontSize: '10px', color: '#64748b', fontWeight: '600' }}>// INTEL_PROCUREMENT</div>
          <select 
            className="cyber-input" 
            value={purchaseKind} 
            onChange={e => setPurchaseKind(e.target.value)}
            disabled={loadingStore}
            style={{ fontSize: '12px', height: '32px' }}
          >
            {storeItems.map((it) => (
              <option key={it.kind} value={it.kind}>
                {it.kind}
              </option>
            ))}
            {storeItems.length === 0 && <option value={purchaseKind}>{purchaseKind}</option>}
          </select>
          <select
            className="cyber-input"
            value={purchasePresetId}
            onChange={e => setPurchasePresetId(e.target.value)}
            disabled={loadingStore}
            style={{ fontSize: '12px', height: '32px' }}
          >
            {(storeItems.find((x) => x.kind === purchaseKind)?.presets ?? []).map((p) => (
              <option key={p.preset_id} value={p.preset_id}>
                {p.preset_id}
              </option>
            ))}
            {!storeItems.find((x) => x.kind === purchaseKind)?.presets?.length && <option value="">(no presets)</option>}
          </select>
          <textarea 
            className="cyber-input"
            value={purchaseText}
            readOnly
            style={{ fontSize: '11px', minHeight: '60px', resize: 'none', background: 'var(--terminal-bg)' }}
          />
          <button 
            className="cyber-button" 
            onClick={handlePurchase}
            disabled={loading}
            style={{ fontSize: '11px', padding: '8px', background: 'rgba(245, 158, 11, 0.1)', borderColor: 'var(--terminal-warn)', color: 'var(--terminal-warn)', fontWeight: '600' }}
          >
            PURCHASE_INTEL
          </button>
        </div>

        {/* Propagation */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
          <div style={{ fontSize: '10px', color: '#64748b', fontWeight: '600' }}>// DISSEMINATION_PROTOCOL</div>
          <input 
            className="cyber-input"
            placeholder="VARIANT_ID"
            value={targetVariantId}
            onChange={e => setTargetVariantId(e.target.value)}
            style={{ fontSize: '11px', height: '32px' }}
          />
          <div style={{ display: 'flex', gap: '8px' }}>
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: '9px', color: '#64748b', marginBottom: '2px' }}>CASH</div>
              <input 
                className="cyber-input"
                type="number"
                placeholder="0"
                value={propSpendCash}
                onChange={e => setPropSpendCash(e.target.value)}
                style={{ fontSize: '11px', width: '100%', height: '32px', boxSizing: 'border-box' }}
              />
            </div>
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: '9px', color: '#64748b', marginBottom: '2px' }}>LIMIT</div>
              <input 
                className="cyber-input"
                type="number"
                placeholder="50"
                value={propLimit}
                onChange={e => setPropLimit(Number(e.target.value))}
                style={{ fontSize: '11px', width: '100%', height: '32px', boxSizing: 'border-box' }}
              />
            </div>
          </div>
          <button 
            className="cyber-button" 
            onClick={handlePropagate}
            disabled={loading || !targetVariantId}
            style={{ fontSize: '11px', padding: '8px', background: 'rgba(16, 185, 129, 0.1)', borderColor: 'var(--terminal-success)', color: 'var(--terminal-success)', fontWeight: '600' }}
          >
            EXECUTE_SPREAD
          </button>
        </div>
      </div>

      <div style={{ marginTop: '15px' }}>
        <div style={{ fontSize: '10px', color: '#64748b', marginBottom: '6px', fontWeight: '600' }}>OWNED_INTEL_CARDS</div>
        <div style={{ 
          display: 'flex', 
          gap: '6px', 
          overflowX: 'auto', 
          paddingBottom: '8px',
          whiteSpace: 'nowrap'
        }}>
          {ownedCards.map(id => (
            <div 
              key={id}
              onClick={() => {
                notify('info', `CARD_SELECTED: ${id.slice(0,8)}...`)
              }}
              style={{ 
                fontSize: '10px', 
                padding: '6px 10px', 
                border: '1px solid var(--terminal-border)', 
                background: 'rgba(255,255,255,0.02)',
                borderRadius: '2px',
                cursor: 'pointer',
                color: '#94a3b8',
                transition: 'all 0.1s'
              }}
              onMouseOver={e => (e.currentTarget.style.borderColor = '#3b82f6')}
              onMouseOut={e => (e.currentTarget.style.borderColor = 'var(--terminal-border)')}
            >
              {id.slice(0, 12)}...
            </div>
          ))}
          {ownedCards.length === 0 && <div style={{ fontSize: '11px', opacity: 0.3, padding: '10px 0' }}>NO_CARDS_IN_INVENTORY</div>}
        </div>
      </div>
    </CyberWidget>
  )
}
