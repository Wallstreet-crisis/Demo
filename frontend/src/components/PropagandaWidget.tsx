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

  const handleBoost = async (variantId: string) => {
    setLoading(true)
    try {
      const r = await Api.newsPropagate({
        variant_id: variantId,
        from_actor_id: `user:${playerId}`,
        visibility_level: 'NORMAL',
        spend_cash: propSpendCash ? Number(propSpendCash) : 0,
        limit: propLimit,
      })
      notify('success', `BOOST_SUCCESS: REACHED_${r.delivered}`)
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : String(e)
      notify('error', msg)
    } finally {
      setLoading(false)
    }
  }

  const handleSuppress = async (item: NewsInboxResponseItem) => {
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

    setLoading(true)
    try {
      await Api.newsSuppress({
        actor_id: `user:${playerId}`,
        chain_id: chainId,
        spend_influence: propSpendCash ? Number(propSpendCash) : 500,
      })
      notify('success', `SUPPRESSION_ENGAGED: CHAIN_${chainId.slice(0,8)}`)
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
                      onClick={() => handleBoost(item.variant_id)}
                      disabled={loading}
                      style={{ flex: 1, fontSize: '9px', padding: '2px 0', borderColor: 'var(--terminal-success)', color: 'var(--terminal-success)' }}
                    >BOOST</button>
                    <button 
                      className="cyber-button" 
                      onClick={() => handleSuppress(item)}
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
