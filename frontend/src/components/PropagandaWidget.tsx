import { useState, useEffect, useCallback, useMemo } from 'react'
import { Api, ApiError, type NewsStoreCatalogItem, type NewsInboxResponseItem } from '../api'
import { useAppSession } from '../app/context'
import { useNotification } from '../app/NotificationContext'
import CyberWidget from './CyberWidget'

export default function PropagandaWidget({ isFocused }: { isFocused?: boolean }) {
  void isFocused
  const { playerId } = useAppSession()
  const { notify } = useNotification()
  
  const [loading, setLoading] = useState(false)
  const [boostModalOpen, setBoostModalOpen] = useState(false)
  const [boostVariantId, setBoostVariantId] = useState<string>('')
  const [boostSpendCash, setBoostSpendCash] = useState<string>('')
  const [boostLimit, setBoostLimit] = useState<number>(100)
  const [boostQuote, setBoostQuote] = useState<{
    mutation_depth: number
    per_delivery_cost: number
    requested_limit: number
    affordable_limit: number
    estimated_total_cost: number
  } | null>(null)
  const [suppressModalOpen, setSuppressModalOpen] = useState(false)
  const [suppressChainId, setSuppressChainId] = useState<string>('')
  const [suppressSpendInfluence, setSuppressSpendInfluence] = useState<string>('500')
  const [inboxItems, setInboxItems] = useState<NewsInboxResponseItem[]>([])
  const [storeItems, setStoreItems] = useState<NewsStoreCatalogItem[]>([])
  const [loadingStore, setLoadingStore] = useState(false)
  const [activeTab, setActiveTab] = useState<'INVENTORY' | 'PROCUREMENT'>('INVENTORY')
  
  // Purchase state
  const [purchaseKind, setPurchaseKind] = useState('RUMOR')
  const [purchasePrice, setPurchasePrice] = useState(100)
  const [purchaseText, setPurchaseText] = useState('')
  const [purchasePresetId, setPurchasePresetId] = useState('')
  const [purchaseSymbol, setPurchaseSymbol] = useState('')

  // Propagation settings
  const [propLimit, setPropLimit] = useState(100)
  const [propSpendCash, setPropSpendCash] = useState('500')

  const refreshInbox = useCallback(async () => {
    if (!playerId) return
    try {
      const r = await Api.newsInbox(`user:${playerId}`, 50)
      setInboxItems(r.items || [])
    } catch (e) {
      console.error('Failed to fetch inbox', e)
    }
  }, [playerId])

  // Sorted items: newest first
  const sortedInboxItems = useMemo(() => {
    return [...inboxItems].sort((a, b) => 
      new Date(b.delivered_at).getTime() - new Date(a.delivered_at).getTime()
    )
  }, [inboxItems])

  useEffect(() => {
    refreshInbox()
    const t = setInterval(refreshInbox, 10000)
    return () => clearInterval(t)
  }, [refreshInbox])

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
          const s0 = selected.symbol_options?.[0] ?? ''
          setPurchaseSymbol(s0)
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
    if (activeTab === 'PROCUREMENT') {
      refreshStoreCatalog()
    }
  }, [activeTab, refreshStoreCatalog])

  const handlePurchase = async () => {
    setLoading(true)
    try {
      const selected = storeItems.find((x) => x.kind === purchaseKind) ?? null
      const options = selected?.symbol_options ?? []
      const reqSymbols = options.length > 0 ? [purchaseSymbol || options[0]] : []
      const presetId = purchasePresetId || (selected?.presets?.[0]?.preset_id ?? null)
      await Api.newsStorePurchase({
        buyer_user_id: `user:${playerId}`,
        kind: purchaseKind,
        price_cash: purchasePrice,
        preset_id: presetId,
        symbols: reqSymbols,
        tags: [],
      })
      notify('success', 'INTEL_ACQUIRED')
      refreshInbox()
      setActiveTab('INVENTORY')
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : String(e)
      notify('error', msg)
    } finally {
      setLoading(false)
    }
  }

  const openBoostModal = (variantId: string) => {
    setBoostVariantId(variantId)
    setBoostSpendCash(propSpendCash)
    setBoostLimit(propLimit)
    setBoostQuote(null)
    setBoostModalOpen(true)

    const budget = Number(propSpendCash)
    const limit = Number(propLimit)
    if (!playerId) return
    if (!Number.isFinite(budget) || budget <= 0) return
    if (!Number.isFinite(limit) || limit <= 0) return

    setLoading(true)
    void (async () => {
      try {
        const r = await Api.newsPropagateQuote({
          variant_id: variantId,
          from_actor_id: `user:${playerId}`,
          spend_cash: budget,
          limit,
        })
        setBoostQuote(r)
      } catch (e) {
        const msg = e instanceof ApiError ? e.message : String(e)
        notify('error', msg)
      } finally {
        setLoading(false)
      }
    })()
  }

  const handleBoostQuote = async () => {
    if (!playerId) return
    const budget = Number(boostSpendCash)
    if (!Number.isFinite(budget) || budget <= 0) {
      notify('error', '请填写正数预算')
      return
    }
    const limit = Number(boostLimit)
    if (!Number.isFinite(limit) || limit <= 0) {
      notify('error', '请填写正数目标覆盖人数')
      return
    }
    setLoading(true)
    try {
      const r = await Api.newsPropagateQuote({
        variant_id: boostVariantId,
        from_actor_id: `user:${playerId}`,
        spend_cash: budget,
        limit,
      })
      setBoostQuote(r)
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : String(e)
      notify('error', msg)
    } finally {
      setLoading(false)
    }
  }

  const handleBoostConfirm = async () => {
    if (!playerId) return
    const budget = Number(boostSpendCash)
    if (!Number.isFinite(budget) || budget <= 0) {
      notify('error', '请填写正数预算')
      return
    }
    const limit = Number(boostLimit)
    if (!Number.isFinite(limit) || limit <= 0) {
      notify('error', '请填写正数目标覆盖人数')
      return
    }
    setLoading(true)
    try {
      const r = await Api.newsPropagate({
        variant_id: boostVariantId,
        from_actor_id: `user:${playerId}`,
        visibility_level: 'NORMAL',
        spend_cash: budget,
        limit,
      })
      notify('success', `BOOST_SUCCESS: REACHED_${r.delivered}`)
      setBoostModalOpen(false)
      setBoostVariantId('')
      setBoostQuote(null)
      refreshInbox()
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : String(e)
      notify('error', msg)
    } finally {
      setLoading(false)
    }
  }

  const openSuppressModal = (item: NewsInboxResponseItem) => {
    // Current API newsSuppress requires chain_id
    // We try to extract it from truth_payload if present
    const truth = (item.truth_payload && typeof item.truth_payload === 'object')
      ? (item.truth_payload as Record<string, unknown>)
      : null
    const chainId = truth && typeof truth.chain_id === 'string' ? truth.chain_id : null
    
    if (!chainId) {
      notify('error', 'SUPPRESSION_FAILED: NO_ACTIVE_CHAIN')
      return
    }

    setSuppressChainId(chainId)
    setSuppressSpendInfluence(propSpendCash ? String(propSpendCash) : '500')
    setSuppressModalOpen(true)
  }

  const handleSuppressConfirm = async () => {
    if (!playerId) return
    const spend = Number(suppressSpendInfluence)
    if (!Number.isFinite(spend) || spend <= 0) {
      notify('error', '请填写正数影响力投入')
      return
    }
    setLoading(true)
    try {
      await Api.newsSuppress({
        actor_id: `user:${playerId}`,
        chain_id: suppressChainId,
        spend_influence: spend,
      })
      notify('success', `SUPPRESSION_ENGAGED: CHAIN_${suppressChainId.slice(0, 8)}`)
      setSuppressModalOpen(false)
      setSuppressChainId('')
      refreshInbox()
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : String(e)
      notify('error', msg)
    } finally {
      setLoading(false)
    }
  }

  return (
    <CyberWidget 
      title="PROPAGANDA_CONTROL" 
      subtitle="MARKET_INFLUENCE_WARFARE"
      actions={
        <div style={{ display: 'flex', gap: '4px' }}>
          <button 
            className={`cyber-button ${activeTab === 'INVENTORY' ? 'active' : ''}`} 
            onClick={() => setActiveTab('INVENTORY')}
            style={{ fontSize: '10px' }}
          >INVENTORY</button>
          <button 
            className={`cyber-button ${activeTab === 'PROCUREMENT' ? 'active' : ''}`} 
            onClick={() => setActiveTab('PROCUREMENT')}
            style={{ fontSize: '10px' }}
          >PROCURE</button>
        </div>
      }
    >
      {boostModalOpen && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(0,0,0,0.65)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 9999,
          }}
          onClick={() => {
            if (loading) return
            setBoostModalOpen(false)
            setBoostVariantId('')
            setBoostQuote(null)
          }}
        >
          <div
            style={{
              width: 420,
              maxWidth: '92vw',
              background: 'rgba(10, 14, 18, 0.95)',
              border: '1px solid var(--terminal-border)',
              padding: 12,
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <div style={{ fontSize: '11px', opacity: 0.8, marginBottom: 8 }}>PAID_BOOST</div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginBottom: 8 }}>
              <div>
                <div style={{ fontSize: '9px', opacity: 0.7, marginBottom: 4 }}>BUDGET_CASH</div>
                <input
                  className="cyber-input"
                  type="number"
                  value={boostSpendCash}
                  onChange={(e) => setBoostSpendCash(e.target.value)}
                  style={{ fontSize: '10px', width: '100%', height: '24px' }}
                />
              </div>
              <div>
                <div style={{ fontSize: '9px', opacity: 0.7, marginBottom: 4 }}>TARGET_REACH</div>
                <input
                  className="cyber-input"
                  type="number"
                  value={boostLimit}
                  onChange={(e) => setBoostLimit(Number(e.target.value))}
                  style={{ fontSize: '10px', width: '100%', height: '24px' }}
                />
              </div>
            </div>

            <div style={{ display: 'flex', gap: 6, marginBottom: 10 }}>
              <button className="cyber-button" onClick={handleBoostQuote} disabled={loading} style={{ fontSize: '10px' }}>
                REFRESH_QUOTE
              </button>
              <button
                className="cyber-button"
                onClick={handleBoostConfirm}
                disabled={loading}
                style={{ fontSize: '10px', borderColor: 'var(--terminal-success)', color: 'var(--terminal-success)' }}
              >
                CONFIRM
              </button>
              <button
                className="cyber-button"
                onClick={() => {
                  if (loading) return
                  setBoostModalOpen(false)
                  setBoostVariantId('')
                  setBoostQuote(null)
                }}
                disabled={loading}
                style={{ fontSize: '10px', opacity: 0.9 }}
              >
                CANCEL
              </button>
            </div>

            <div style={{ fontSize: '10px', opacity: 0.85 }}>
              <div style={{ opacity: 0.7, marginBottom: 4 }}>VARIANT: {boostVariantId ? boostVariantId.slice(0, 8) : ''}</div>
              {boostQuote ? (
                <div style={{ display: 'grid', gap: 6 }}>
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr auto', alignItems: 'end', gap: 8 }}>
                    <div style={{ opacity: 0.7 }}>EST_REACH</div>
                    <div style={{ fontSize: '22px', fontWeight: 700, color: 'var(--terminal-success)', lineHeight: 1 }}>
                      {boostQuote.affordable_limit}
                      <span style={{ fontSize: '12px', fontWeight: 400, opacity: 0.8, marginLeft: 6, color: 'inherit' }}>
                        / {boostQuote.requested_limit}
                      </span>
                    </div>
                  </div>
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, opacity: 0.9 }}>
                    <div>DEPTH: {boostQuote.mutation_depth}</div>
                    <div>UNIT_COST: {boostQuote.per_delivery_cost.toFixed(2)}</div>
                    <div style={{ gridColumn: '1 / -1' }}>EST_TOTAL: {boostQuote.estimated_total_cost.toFixed(2)}</div>
                  </div>
                </div>
              ) : (
                <div style={{ opacity: 0.6 }}>正在获取报价...</div>
              )}
            </div>
          </div>
        </div>
      )}

      {suppressModalOpen && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(0,0,0,0.65)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 9999,
          }}
          onClick={() => {
            if (loading) return
            setSuppressModalOpen(false)
            setSuppressChainId('')
          }}
        >
          <div
            style={{
              width: 420,
              maxWidth: '92vw',
              background: 'rgba(10, 14, 18, 0.95)',
              border: '1px solid var(--terminal-border)',
              padding: 12,
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <div style={{ fontSize: '11px', opacity: 0.8, marginBottom: 8 }}>SUPPRESS_CONFIRM</div>
            <div style={{ fontSize: '10px', opacity: 0.85, marginBottom: 10 }}>
              <div style={{ opacity: 0.7, marginBottom: 4 }}>CHAIN: {suppressChainId ? suppressChainId.slice(0, 8) : ''}</div>
              <div style={{ marginBottom: 6 }}>CASH_COST: 100000</div>
              <div style={{ opacity: 0.7, marginBottom: 4 }}>SPEND_INFLUENCE</div>
              <input
                className="cyber-input"
                type="number"
                value={suppressSpendInfluence}
                onChange={(e) => setSuppressSpendInfluence(e.target.value)}
                style={{ fontSize: '10px', width: '100%', height: '24px' }}
              />
            </div>
            <div style={{ display: 'flex', gap: 6 }}>
              <button
                className="cyber-button"
                onClick={handleSuppressConfirm}
                disabled={loading}
                style={{ fontSize: '10px', borderColor: 'var(--terminal-error)', color: 'var(--terminal-error)' }}
              >
                CONFIRM
              </button>
              <button
                className="cyber-button"
                onClick={() => {
                  if (loading) return
                  setSuppressModalOpen(false)
                  setSuppressChainId('')
                }}
                disabled={loading}
                style={{ fontSize: '10px', opacity: 0.9 }}
              >
                CANCEL
              </button>
            </div>
          </div>
        </div>
      )}

      <div style={{ display: 'flex', flexDirection: 'column', height: '100%', gap: '8px' }}>
        
        {/* Global Settings - Only show when focused */}
        {isFocused && (
          <div style={{ 
            display: 'flex', 
            gap: '10px', 
            padding: '6px 8px', 
            background: 'rgba(0,0,0,0.2)', 
            border: '1px solid var(--terminal-border)',
            borderRadius: '2px'
          }}>
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: '8px', color: '#64748b', marginBottom: '2px' }}>OP_BUDGET</div>
              <input 
                className="cyber-input"
                type="number"
                value={propSpendCash}
                onChange={e => setPropSpendCash(e.target.value)}
                style={{ fontSize: '10px', width: '100%', height: '22px' }}
              />
            </div>
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: '8px', color: '#64748b', marginBottom: '2px' }}>TARGET_REACH</div>
              <input 
                className="cyber-input"
                type="number"
                value={propLimit}
                onChange={e => setPropLimit(Number(e.target.value))}
                style={{ fontSize: '10px', width: '100%', height: '22px' }}
              />
            </div>
          </div>
        )}

        {activeTab === 'INVENTORY' && (
          <div style={{ flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '6px' }} className="custom-scrollbar">
            {sortedInboxItems.length === 0 && (
              <div style={{ opacity: 0.3, textAlign: 'center', padding: '20px', fontSize: '11px' }}>VOID_INVENTORY</div>
            )}
            {(isFocused ? sortedInboxItems : sortedInboxItems.slice(0, 3)).map(item => {
              const truth = (item.truth_payload && typeof item.truth_payload === 'object')
                ? (item.truth_payload as Record<string, unknown>)
                : null
              const itemChainId = truth && typeof truth.chain_id === 'string' ? truth.chain_id : null
              return (
                <div key={item.delivery_id} style={{ 
                  background: 'rgba(30, 41, 49, 0.5)', 
                  border: '1px solid var(--terminal-border)',
                  padding: '8px',
                  borderRadius: '2px'
                }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '9px', marginBottom: '4px', opacity: 0.7 }}>
                    <span>[{item.kind}] {new Date(item.delivered_at).toLocaleTimeString()}</span>
                    <span>ID: {item.variant_id.slice(0,8)}</span>
                  </div>
                  <div style={{ fontSize: '11px', lineHeight: '1.3', marginBottom: '8px', color: '#cbd5e1' }}>
                    {item.text.length > 120 ? item.text.substring(0, 120) + '...' : item.text}
                  </div>
                  <div style={{ display: 'flex', gap: '4px' }}>
                    <button 
                      className="cyber-button" 
                      onClick={() => openBoostModal(item.variant_id)}
                      disabled={loading}
                      style={{ flex: 1, fontSize: '9px', padding: '2px 0', borderColor: 'var(--terminal-success)', color: 'var(--terminal-success)' }}
                    >BOOST</button>
                    <button 
                      className="cyber-button" 
                      onClick={() => openSuppressModal(item)}
                      disabled={loading || !itemChainId}
                      style={{ flex: 1, fontSize: '9px', padding: '2px 0', borderColor: 'var(--terminal-error)', color: 'var(--terminal-error)' }}
                    >SUPPRESS</button>
                  </div>
                </div>
              )
            })}
          </div>
        )}

        {activeTab === 'PROCUREMENT' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '6px' }}>
              <select 
                className="cyber-input" 
                value={purchaseKind} 
                onChange={e => setPurchaseKind(e.target.value)}
                disabled={loadingStore}
                style={{ fontSize: '10px', height: '26px' }}
              >
                {storeItems.map((it) => (
                  <option key={it.kind} value={it.kind}>{it.kind} (${it.price_cash})</option>
                ))}
              </select>
              <select
                className="cyber-input"
                value={purchaseSymbol}
                onChange={e => setPurchaseSymbol(e.target.value)}
                disabled={loadingStore}
                style={{ fontSize: '10px', height: '26px' }}
              >
                {(storeItems.find((x) => x.kind === purchaseKind)?.symbol_options ?? []).map((s) => (
                  <option key={s} value={s}>{s}</option>
                ))}
                {!storeItems.find((x) => x.kind === purchaseKind)?.symbol_options?.length && <option value="">ANY_TARGET</option>}
              </select>
            </div>
            
            <textarea 
              className="cyber-input"
              value={purchaseText}
              readOnly
              style={{ fontSize: '10px', minHeight: '40px', resize: 'none', background: 'rgba(0,0,0,0.3)', opacity: 0.7 }}
            />
            
            <button 
              className="cyber-button" 
              onClick={handlePurchase}
              disabled={loading}
              style={{ 
                fontSize: '11px', 
                padding: '6px', 
                background: 'rgba(245, 158, 11, 0.1)', 
                borderColor: 'var(--terminal-warn)', 
                color: 'var(--terminal-warn)', 
                fontWeight: 'bold' 
              }}
            >
              INITIATE_PROCUREMENT
            </button>
          </div>
        )}
      </div>
    </CyberWidget>
  )
}
