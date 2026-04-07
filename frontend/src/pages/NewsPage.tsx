import { useEffect, useMemo, useRef, useState, useCallback } from 'react'
import {
  Api,
  ApiError,
  type NewsInboxResponse,
  type NewsInboxResponseItem,
  type NewsStoreCatalogItem,
} from '../api'
import { useAppSession } from '../app/context'
import { WsClient } from '../api'
import { useNotification } from '../app/NotificationContext'
import ContractFormFromNews from '../components/ContractFormFromNews'
import IntelligenceCard from '../components/IntelligenceCard'
import { Newspaper, ShoppingCart, ArrowUpDown, Info, Clock } from 'lucide-react'

function getEventType(payload: unknown): string | null {
  if (!payload || typeof payload !== 'object') return null
  const v = (payload as Record<string, unknown>).event_type
  return typeof v === 'string' ? v : null
}

export default function NewsPage() {
  const { playerId, roomId } = useAppSession()
  const { notify } = useNotification()
  const [loading, setLoading] = useState(true)

  const [inbox, setInbox] = useState<NewsInboxResponse | null>(null)
  const [ownedCards, setOwnedCards] = useState<string[]>([])

  const [storeItems, setStoreItems] = useState<NewsStoreCatalogItem[]>([])
  const [storeExpiresAt, setStoreExpiresAt] = useState<string>('')
  const [timeLeft, setTimeLeft] = useState<string>('')
  
  const [targetVariantId, setTargetVariantId] = useState<string>('')
  const [propLimit, setPropLimit] = useState<number>(100)
  const [propSpendCash, setPropSpendCash] = useState<string>('500')
  const [propQuote, setPropQuote] = useState<{
    mutation_depth: number
    per_delivery_cost: number
    requested_limit: number
    affordable_limit: number
    estimated_total_cost: number
  } | null>(null)

  const [purchaseKind, setPurchaseKind] = useState<string>('RUMOR')
  const [purchasePrice, setPurchasePrice] = useState<number>(100)
  const [purchasePresetId, setPurchasePresetId] = useState<string>('')
  const [purchaseSymbol, setPurchaseSymbol] = useState<string>('')

  const [selectedInboxItem, setSelectedInboxItem] = useState<NewsInboxResponseItem | null>(null)

  // 篡改新闻状态
  const [showMutatePanel, setShowMutatePanel] = useState(false)
  const [mutateVariantId, setMutateVariantId] = useState('')
  const [mutateText, setMutateText] = useState('')
  const [mutateSpendCash, setMutateSpendCash] = useState('')

  // 引用签约状态
  const [showContractPanel, setShowContractPanel] = useState(false)
  const [contractNewsItem, setContractNewsItem] = useState<NewsInboxResponseItem | null>(null)

  // 抑制状态
  const [showSuppressPanel, setShowSuppressPanel] = useState(false)
  const [suppressChainId, setSuppressChainId] = useState('')
  const [suppressInfluence, setSuppressInfluence] = useState(500.0)
  const [suppressing, setSuppressing] = useState(false)

  // 界面 Tab 状态
  const [activeTab, setActiveTab] = useState<'collection' | 'store'>('collection')
  const [filterKind, setFilterKind] = useState<string>('ALL')
  const [sortOrder, setSortOrder] = useState<'newest' | 'oldest'>('newest')

  const ws = useMemo(() => new WsClient({ baseUrl: import.meta.env.VITE_API_BASE_URL }), [])
  const refreshTimerRef = useRef<number | null>(null)

  const fetchPropagateQuote = useCallback(async (variantId: string, cash: number, limit: number) => {
    if (!playerId || !variantId || cash <= 0 || limit <= 0) return
    try {
      const r = await Api.newsPropagateQuote({
        variant_id: variantId,
        from_actor_id: `user:${playerId}`,
        spend_cash: cash,
        limit,
      })
      setPropQuote(r)
    } catch (e) {
      console.error('Failed to fetch propagate quote', e)
    }
  }, [playerId])

  useEffect(() => {
    if (targetVariantId && Number(propSpendCash) > 0 && propLimit > 0) {
      const timer = setTimeout(() => {
        fetchPropagateQuote(targetVariantId, Number(propSpendCash), propLimit)
      }, 500)
      return () => clearTimeout(timer)
    }
  }, [targetVariantId, propSpendCash, propLimit, fetchPropagateQuote])

  function scheduleRefreshInbox(): void {
    if (refreshTimerRef.current !== null) return
    refreshTimerRef.current = window.setTimeout(() => {
      refreshTimerRef.current = null
      refreshInbox()
    }, 500)
  }

  async function refreshInbox(): Promise<void> {
    setLoading(true)
    try {
      const r = await Api.newsInbox(`user:${playerId}`, 50)
      setInbox(r)
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : (e instanceof Error ? e.message : String(e))
      notify('error', `刷新收件箱失败: ${msg}`)
    } finally {
      setLoading(false)
    }
  }

  async function refreshOwnedCards(): Promise<void> {
    try {
      const r = await Api.newsOwnershipList(`user:${playerId}`)
      setOwnedCards(Array.isArray(r.cards) ? r.cards : [])
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : (e instanceof Error ? e.message : String(e))
      notify('error', `获取已购卡片失败: ${msg}`)
      setOwnedCards([])
    }
  }

  async function purchase(): Promise<void> {
    try {
      const selected = storeItems.find((x) => x.kind === purchaseKind) ?? null
      const options = selected?.symbol_options ?? []
      const reqSymbols = options.length > 0 ? [purchaseSymbol || options[0]] : []
      const presetId = purchasePresetId || (selected?.presets?.[0]?.preset_id ?? null)
      const r = await Api.newsStorePurchase({
        buyer_user_id: `user:${playerId}`,
        kind: purchaseKind,
        price_cash: Number(purchasePrice),
        preset_id: presetId,
        symbols: reqSymbols,
        tags: [],
      })
      if (r.variant_id) setTargetVariantId(r.variant_id)
      notify('success', `购买成功: ${r.kind}`)
      await refreshInbox()
      refreshOwnedCards()
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : (e instanceof Error ? e.message : String(e))
      notify('error', msg)
    }
  }

  async function refreshStoreCatalog(force = false): Promise<void> {
    if (!playerId) return
    setLoading(true)
    try {
      const r = await Api.newsStoreCatalog(`user:${playerId}`, force)
      const items = Array.isArray(r.items) ? r.items : []
      setStoreItems(items)
      setStoreExpiresAt(r.expires_at || '')

      if (items.length > 0) {
        const selected = items.find((x) => x.kind === purchaseKind) ?? items[0]
        if (selected) {
          setPurchaseKind(selected.kind)
          const p0 = selected.presets?.[0]?.preset_id ?? ''
          setPurchasePresetId(p0)
          const s0 = selected.symbol_options?.[0] ?? ''
          setPurchaseSymbol(s0)
        }
      }
      if (force) notify('success', '黑市货架已更新')
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : (e instanceof Error ? e.message : String(e))
      notify('error', `获取新闻商店目录失败: ${msg}`)
      setStoreItems([])
    } finally {
      setLoading(false)
    }
  }

  // 倒计时逻辑
  useEffect(() => {
    if (!storeExpiresAt) return
    
    const updateTimer = () => {
      const now = new Date().getTime()
      const expiry = new Date(storeExpiresAt).getTime()
      const diff = expiry - now
      
      if (diff <= 0) {
        setTimeLeft('已过期')
        // 自动刷新
        refreshStoreCatalog()
        return
      }
      
      const mins = Math.floor(diff / (1000 * 60))
      const secs = Math.floor((diff % (1000 * 60)) / 1000)
      setTimeLeft(`${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`)
    }
    
    updateTimer()
    const timer = setInterval(updateTimer, 1000)
    return () => clearInterval(timer)
  }, [storeExpiresAt, playerId])

  useEffect(() => {
    refreshInbox()
    refreshOwnedCards()
    refreshStoreCatalog()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [playerId])

  useEffect(() => {
    const selected = storeItems.find((x) => x.kind === purchaseKind) ?? null
    if (!selected) return
    const nextPreset = selected.presets?.find((p) => p.preset_id === purchasePresetId) ?? selected.presets?.[0] ?? null
    if (nextPreset) {
      setPurchasePresetId(nextPreset.preset_id)
    } else {
      setPurchasePresetId('')
    }

    const opts = selected.symbol_options ?? []
    if (opts.length > 0) {
      if (!purchaseSymbol || !opts.includes(purchaseSymbol)) setPurchaseSymbol(opts[0])
    } else {
      if (purchaseSymbol) setPurchaseSymbol('')
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [purchaseKind, storeItems])

  useEffect(() => {
    ws.connect('events', (payload) => {
      const t = getEventType(payload)
      if (typeof t === 'string' && t.startsWith('news.')) {
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
  }, [roomId])

  const handleAction = (action: 'propagate' | 'mutate' | 'contract' | 'suppress', item: NewsInboxResponseItem) => {
    setSelectedInboxItem(item)
    if (action === 'propagate') {
      setTargetVariantId(item.variant_id)
      notify('info', '已选择该变体，请在下方传播面板操作')
    } else if (action === 'mutate') {
      setMutateVariantId(item.variant_id)
      setMutateText(item.text)
      setShowMutatePanel(true)
    } else if (action === 'contract') {
      setContractNewsItem(item)
      setShowContractPanel(true)
    } else if (action === 'suppress') {
      const payload = item.truth_payload as any
      const chainId = payload?.chain_id || ''
      setSuppressChainId(chainId)
      setShowSuppressPanel(true)
    }
  }

  async function propagateLast(): Promise<void> {
    const vid = targetVariantId
    if (!vid) {
      notify('error', '请先选择一个情报变体')
      return
    }
    const spendCash = propSpendCash.trim() === '' ? undefined : Number(propSpendCash)
    if (spendCash !== undefined && (!Number.isFinite(spendCash) || spendCash <= 0)) {
      notify('error', '投入资金必须为正数')
      return
    }
    try {
      const r = await Api.newsPropagate({
        variant_id: vid,
        from_actor_id: `user:${playerId}`,
        visibility_level: 'NORMAL',
        spend_influence: 0.0,
        spend_cash: spendCash,
        limit: Number(propLimit),
      })
      notify('success', `传播成功: 已送达 ${r.delivered} 人`)
      await refreshInbox()
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : (e instanceof Error ? e.message : String(e))
      notify('error', msg)
    }
  }

  const kinds = useMemo(() => {
    const k = new Set<string>()
    inbox?.items?.forEach(it => k.add(it.kind.toUpperCase()))
    return Array.from(k)
  }, [inbox])

  const filteredInbox = useMemo(() => {
    if (!inbox?.items) return []
    let items = [...inbox.items]
    
    // Sort
    items.sort((a, b) => {
      const da = new Date(a.delivered_at).getTime()
      const db = new Date(b.delivered_at).getTime()
      return sortOrder === 'newest' ? db - da : da - db
    })

    // Filter
    if (filterKind !== 'ALL') {
      items = items.filter(it => it.kind.toUpperCase() === filterKind)
    }
    
    return items
  }, [inbox, filterKind, sortOrder])

  const categorizedInbox = useMemo(() => {
    const active: NewsInboxResponseItem[] = []
    const expired: NewsInboxResponseItem[] = []
    
    filteredInbox.forEach(it => {
      const createdAt = new Date(it.delivered_at)
      const ageHours = (new Date().getTime() - createdAt.getTime()) / (1000 * 60 * 60)
      const ttl = it.kind === 'WORLD_EVENT' ? 24 : 6
      if (ageHours >= ttl) {
        expired.push(it)
      } else {
        active.push(it)
      }
    })
    
    return { active, expired }
  }, [filteredInbox])

  const activeStoreItem = useMemo(() => {
    return storeItems.find(it => it.kind === purchaseKind) || null
  }, [storeItems, purchaseKind])

  const getRarityColor = (rarity?: string) => {
    switch ((rarity || 'COMMON').toUpperCase()) {
      case 'UNCOMMON': return '#52c41a'
      case 'RARE': return '#1890ff'
      case 'EPIC': return '#722ed1'
      case 'LEGENDARY': return '#faad14'
      default: return '#8c8c8c'
    }
  }

  const getRarityLabel = (rarity?: string) => {
    switch ((rarity || 'COMMON').toUpperCase()) {
      case 'UNCOMMON': return '罕见'
      case 'RARE': return '珍稀'
      case 'EPIC': return '史诗'
      case 'LEGENDARY': return '传说'
      default: return '基础'
    }
  }

  const previewItem = useMemo((): NewsInboxResponseItem | null => {
    if (!activeStoreItem) return null
    const preset = activeStoreItem.presets?.find(p => p.preset_id === purchasePresetId) || activeStoreItem.presets?.[0]
    return {
      delivery_id: 'preview',
      card_id: 'preview',
      variant_id: purchasePresetId || 'preview',
      kind: purchaseKind,
      from_actor_id: 'MARKET',
      visibility_level: 'NORMAL',
      delivery_reason: 'BLUEPRINT_PREVIEW',
      delivered_at: new Date().toISOString(),
      text: preset?.text.replace('{symbol}', purchaseSymbol || '[$SYMBOL]') || activeStoreItem.preview_text,
      symbols: purchaseSymbol ? [purchaseSymbol] : [],
      tags: activeStoreItem.tags || [],
      truth_payload: {
        image_uri: activeStoreItem.preview_image_uri || null,
        impact: 'UNKNOWN'
      },
      rarity: activeStoreItem.rarity || 'COMMON'
    }
  }, [activeStoreItem, purchaseKind, purchasePresetId, purchaseSymbol])

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '24px', height: '100%', color: '#e0e0e0' }}>
      {/* Header Tabs */}
      <div style={{ display: 'flex', gap: '16px', borderBottom: '1px solid #333', paddingBottom: '12px' }}>
        <TabBtn 
          active={activeTab === 'collection'} 
          onClick={() => setActiveTab('collection')} 
          icon={Newspaper} 
          label="情报仓库 (Collection)" 
        />
        <TabBtn 
          active={activeTab === 'store'} 
          onClick={() => setActiveTab('store')} 
          icon={ShoppingCart} 
          label="黑市情报 (Black Market)" 
        />
      </div>

      {activeTab === 'collection' && (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 380px', gap: '24px', flex: 1, minHeight: 0 }}>
          {/* Left: Card Collection */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '16px', minHeight: 0 }}>
            {/* Filter Bar */}
            <div style={{ 
              display: 'flex', 
              justifyContent: 'space-between', 
              alignItems: 'center',
              background: 'rgba(20, 20, 20, 0.4)',
              padding: '12px 20px',
              borderRadius: '2px',
              borderWidth: '1px',
              borderStyle: 'solid',
              borderColor: 'rgba(255,255,255,0.05)',
              backdropFilter: 'blur(10px)'
            }}>
              <div style={{ display: 'flex', gap: '16px', alignItems: 'center' }}>
                <span style={{ fontSize: '10px', color: '#444', fontWeight: '900', letterSpacing: '2px', textTransform: 'uppercase' }}>Filter_Protocol:</span>
                <div style={{ display: 'flex', gap: '8px' }}>
                  <FilterChip active={filterKind === 'ALL'} onClick={() => setFilterKind('ALL')} label="ALL_FILES" />
                  {kinds.map(k => (
                    <FilterChip key={k} active={filterKind === k} onClick={() => setFilterKind(k)} label={k} />
                  ))}
                </div>
              </div>
              <div style={{ display: 'flex', gap: '20px', alignItems: 'center' }}>
                <button 
                  onClick={() => setSortOrder(prev => prev === 'newest' ? 'oldest' : 'newest')}
                  style={{ 
                    background: 'none', 
                    border: 'none', 
                    color: '#444', 
                    cursor: 'pointer', 
                    display: 'flex', 
                    alignItems: 'center', 
                    gap: '6px', 
                    fontSize: '10px',
                    fontWeight: '900',
                    letterSpacing: '1px',
                    textTransform: 'uppercase',
                    transition: 'color 0.2s'
                  }}
                  onMouseEnter={e => e.currentTarget.style.color = '#fff'}
                  onMouseLeave={e => e.currentTarget.style.color = '#444'}
                >
                  <ArrowUpDown size={12} />
                  {sortOrder === 'newest' ? 'NEWEST_FIRST' : 'OLDEST_FIRST'}
                </button>
                <div style={{ width: '1px', height: '16px', background: 'rgba(255,255,255,0.05)' }} />
                <button 
                  onClick={refreshInbox} 
                  disabled={loading} 
                  className="cyber-button mini"
                  style={{ 
                    background: 'transparent',
                    borderWidth: '1px',
                    borderStyle: 'solid',
                    borderColor: 'var(--terminal-info)33',
                    color: 'var(--terminal-info)',
                    fontSize: '10px',
                    fontWeight: 'bold',
                    letterSpacing: '2px',
                    padding: '6px 16px',
                    borderRadius: '2px'
                  }}
                >
                  {loading ? 'RE-SYNCING...' : 'SYNC_INBOX'}
                </button>
              </div>
            </div>

            {/* Card Grid */}
            <div style={{ 
              display: 'flex',
              flexDirection: 'column',
              gap: '32px',
              overflowY: 'auto',
              padding: '4px',
              flex: 1,
              paddingRight: '10px'
            }}>
              {/* Active Section */}
              <section>
                <h3 style={{ fontSize: '12px', color: '#555', marginBottom: '16px', letterSpacing: '2px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <div style={{ width: '8px', height: '8px', borderRadius: '50%', background: 'var(--terminal-success)' }} />
                  ACTIVE_INTELLIGENCE ({categorizedInbox.active.length})
                </h3>
                <div style={{ 
                  display: 'grid', 
                  gridTemplateColumns: 'repeat(auto-fill, minmax(240px, 1fr))', 
                  gap: '20px'
                }}>
                  {categorizedInbox.active.map(it => (
                    <IntelligenceCard 
                      key={it.delivery_id} 
                      item={it} 
                      isSelected={selectedInboxItem?.delivery_id === it.delivery_id}
                      onClick={() => setSelectedInboxItem(it)}
                      onAction={handleAction}
                      stage={ownedCards.includes(it.card_id) ? 'HELD' : 'CIRCULATING'}
                    />
                  ))}
                </div>
              </section>

              {/* Expired Section */}
              {categorizedInbox.expired.length > 0 && (
                <section>
                  <h3 style={{ fontSize: '12px', color: '#555', marginBottom: '16px', letterSpacing: '2px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <div style={{ width: '8px', height: '8px', borderRadius: '50%', background: '#444' }} />
                    ARCHIVED_HISTORY ({categorizedInbox.expired.length})
                  </h3>
                  <div style={{ 
                    display: 'grid', 
                    gridTemplateColumns: 'repeat(auto-fill, minmax(240px, 1fr))', 
                    gap: '20px',
                    opacity: 0.6
                  }}>
                    {categorizedInbox.expired.map(it => (
                      <IntelligenceCard 
                        key={it.delivery_id} 
                        item={it} 
                        isSelected={selectedInboxItem?.delivery_id === it.delivery_id}
                        onClick={() => setSelectedInboxItem(it)}
                        onAction={handleAction}
                        stage="EXPIRED"
                      />
                    ))}
                  </div>
                </section>
              )}

              {filteredInbox.length === 0 && (
                <div style={{ 
                  height: '300px',
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: '12px',
                  color: '#666',
                  borderWidth: '2px',
                  borderStyle: 'dashed',
                  borderColor: '#333',
                  borderRadius: '12px'
                }}>
                  <Newspaper size={48} opacity={0.2} />
                  <span>暂无匹配情报</span>
                </div>
              )}
            </div>
          </div>

          {/* Right: Action Panel */}
          <div style={{ 
            display: 'flex', 
            flexDirection: 'column', 
            gap: '24px',
            overflowY: 'auto',
            paddingRight: '4px'
          }}>
            {selectedInboxItem ? (
              <div style={{ 
                background: 'rgba(26, 26, 26, 0.4)',
                borderWidth: '1px',
                borderStyle: 'solid',
                borderColor: 'var(--terminal-info)33',
                borderRadius: '4px',
                padding: '24px',
                display: 'flex',
                flexDirection: 'column',
                gap: '20px',
                backdropFilter: 'blur(10px)',
                position: 'relative'
              }}>
                {/* Corner Decoration */}
                <div style={{ position: 'absolute', top: 0, right: 0, width: '40px', height: '40px', background: 'linear-gradient(45deg, transparent 50%, var(--terminal-info) 50%)', opacity: 0.1 }} />
                
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                    <div style={{ width: '4px', height: '16px', background: 'var(--terminal-info)' }} />
                    <span style={{ fontWeight: '900', fontSize: '14px', letterSpacing: '2px', textTransform: 'uppercase', color: 'var(--terminal-info)' }}>
                      Intelligence Analysis
                    </span>
                  </div>
                  <button onClick={() => setSelectedInboxItem(null)} style={{ 
                    background: 'none', 
                    border: 'none', 
                    color: '#444', 
                    cursor: 'pointer',
                    fontSize: '18px'
                  }}>✕</button>
                </div>

                <div style={{ 
                  fontSize: '15px', 
                  lineHeight: '1.7', 
                  color: '#fff', 
                  background: 'rgba(0,0,0,0.6)', 
                  padding: '20px', 
                  borderRadius: '2px', 
                  borderLeft: '2px solid var(--terminal-info)',
                  fontFamily: 'system-ui',
                  boxShadow: 'inset 0 0 20px rgba(0,0,0,0.4)'
                }}>
                  {selectedInboxItem.text}
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
                  <MetaBox label="Variant Signature" value={selectedInboxItem.variant_id.slice(0, 12)} />
                  <MetaBox label="Origin Entity" value={selectedInboxItem.from_actor_id} />
                  <MetaBox label="Impact Targets" value={selectedInboxItem.symbols?.join(', ') || 'GLOBAL_SCOPE'} />
                  <MetaBox label="Delivery Protocol" value={selectedInboxItem.delivery_reason} />
                </div>

                {!!selectedInboxItem.truth_payload && (
                  <div style={{ 
                    background: 'rgba(0,0,0,0.4)', 
                    padding: '16px', 
                    borderRadius: '2px', 
                    borderWidth: '1px', 
                    borderStyle: 'solid', 
                    borderColor: 'rgba(255,255,255,0.05)' 
                  }}>
                    <div style={{ fontSize: '10px', color: '#444', marginBottom: '10px', textTransform: 'uppercase', letterSpacing: '1px', fontWeight: 'bold' }}>
                      Core Data Stream (Hex/Json)
                    </div>
                    <pre style={{ 
                      margin: 0, 
                      fontSize: '12px', 
                      color: 'var(--terminal-success)', 
                      whiteSpace: 'pre-wrap', 
                      fontFamily: 'monospace',
                      opacity: 0.8,
                      lineHeight: '1.4'
                    }}>
                      {String(JSON.stringify(selectedInboxItem.truth_payload, null, 2) ?? '')}
                    </pre>
                  </div>
                )}
              </div>
            ) : (
              <div style={{ 
                background: 'rgba(26, 26, 26, 0.2)',
                borderWidth: '1px',
                borderStyle: 'dashed',
                borderColor: '#222',
                borderRadius: '4px',
                padding: '60px 20px',
                textAlign: 'center',
                color: '#333',
                fontSize: '12px',
                letterSpacing: '2px',
                textTransform: 'uppercase'
              }}>
                [ Waiting for Intelligence Selection ]
              </div>
            )}

            {/* Propagate Panel */}
            <div style={{ 
              background: 'rgba(26, 26, 26, 0.4)',
              borderWidth: '1px',
              borderStyle: 'solid',
              borderColor: 'var(--terminal-success)22',
              borderRadius: '4px',
              padding: '24px',
              display: 'flex',
              flexDirection: 'column',
              gap: '20px',
              backdropFilter: 'blur(10px)'
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                <div style={{ width: '4px', height: '16px', background: 'var(--terminal-success)' }} />
                <span style={{ fontWeight: '900', fontSize: '14px', letterSpacing: '2px', textTransform: 'uppercase', color: 'var(--terminal-success)' }}>
                  Amplifier System
                </span>
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                  <label style={{ fontSize: '10px', color: '#444', textTransform: 'uppercase', letterSpacing: '1px' }}>Target Identification</label>
                  <input 
                    value={targetVariantId} 
                    onChange={e => setTargetVariantId(e.target.value)} 
                    placeholder="Auto-mapped from selection..."
                    style={{ 
                      background: 'rgba(0,0,0,0.4)', 
                      borderWidth: '1px',
                      borderStyle: 'solid',
                      borderColor: '#222',
                      color: 'var(--terminal-success)', 
                      padding: '12px', 
                      borderRadius: '2px', 
                      fontSize: '12px',
                      fontFamily: 'monospace'
                    }}
                  />
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                    <label style={{ fontSize: '10px', color: '#444', textTransform: 'uppercase', letterSpacing: '1px' }}>Node Coverage</label>
                    <input type="number" value={propLimit} onChange={(e) => setPropLimit(Number(e.target.value))} style={{ 
                      background: 'rgba(0,0,0,0.4)', 
                      borderWidth: '1px',
                      borderStyle: 'solid',
                      borderColor: '#222',
                      color: '#fff', 
                      padding: '12px', 
                      borderRadius: '2px',
                      fontFamily: 'monospace'
                    }} />
                  </div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                    <label style={{ fontSize: '10px', color: '#444', textTransform: 'uppercase', letterSpacing: '1px' }}>Energy Budget ($)</label>
                    <input value={propSpendCash} onChange={(e) => setPropSpendCash(e.target.value)} style={{ 
                      background: 'rgba(0,0,0,0.4)', 
                      borderWidth: '1px',
                      borderStyle: 'solid',
                      borderColor: '#222',
                      color: '#fff', 
                      padding: '12px', 
                      borderRadius: '2px',
                      fontFamily: 'monospace'
                    }} />
                  </div>
                </div>
                
                {propQuote && (
                  <div style={{ background: 'rgba(0,0,0,0.6)', padding: '16px', borderRadius: '2px', border: '1px solid var(--terminal-success)11', fontSize: '12px' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px' }}>
                      <span style={{ color: '#444', textTransform: 'uppercase', fontSize: '10px' }}>Reachable Nodes</span>
                      <span style={{ color: 'var(--terminal-success)', fontWeight: 'bold' }}>{propQuote.affordable_limit}</span>
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                      <span style={{ color: '#444', textTransform: 'uppercase', fontSize: '10px' }}>Total Resource Consumption</span>
                      <span style={{ color: 'var(--terminal-warn)', fontWeight: 'bold' }}>${propQuote.estimated_total_cost.toFixed(2)}</span>
                    </div>
                  </div>
                )}

                <button 
                  onClick={propagateLast} 
                  className="cyber-button" 
                  style={{ 
                    background: 'var(--terminal-success)', 
                    color: '#000', 
                    fontWeight: '900',
                    height: '50px',
                    borderRadius: '2px',
                    letterSpacing: '2px',
                    textTransform: 'uppercase',
                    fontSize: '14px',
                    boxShadow: '0 0 20px var(--terminal-success)33'
                  }}
                >
                  Initiate Broadcast
                </button>
              </div>
            </div>

            {/* Quick Actions */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
              <button 
                onClick={() => selectedInboxItem ? handleAction('mutate', selectedInboxItem) : notify('error', '请先选择一张情报卡牌')}
                style={{ 
                  background: 'rgba(250, 173, 20, 0.05)', 
                  border: '1px solid rgba(250, 173, 20, 0.2)', 
                  color: 'var(--terminal-warn)', 
                  padding: '14px', 
                  borderRadius: '2px', 
                  cursor: 'pointer', 
                  fontSize: '12px',
                  fontWeight: 'bold',
                  letterSpacing: '1px',
                  textTransform: 'uppercase',
                  transition: 'all 0.3s'
                }}
              >
                Modify Variant
              </button>
              <button 
                onClick={() => selectedInboxItem ? handleAction('contract', selectedInboxItem) : notify('error', '请先选择一张情报卡牌')}
                style={{ 
                  background: 'rgba(24, 144, 255, 0.05)', 
                  border: '1px solid rgba(24, 144, 255, 0.2)', 
                  color: 'var(--terminal-info)', 
                  padding: '14px', 
                  borderRadius: '2px', 
                  cursor: 'pointer', 
                  fontSize: '12px',
                  fontWeight: 'bold',
                  letterSpacing: '1px',
                  textTransform: 'uppercase',
                  transition: 'all 0.3s'
                }}
              >
                Execute Contract
              </button>
            </div>
          </div>
        </div>
      )}

      {activeTab === 'store' && (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 400px', gap: '32px', flex: 1, minHeight: 0 }}>
          {/* Left: Blueprint Selection */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '24px', overflowY: 'auto', paddingRight: '10px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end' }}>
              <div>
                <h2 style={{ color: '#faad14', letterSpacing: '2px', marginBottom: '8px' }}>地下情报黑市 (Black Market)</h2>
                <p style={{ color: '#666', fontSize: '13px', margin: 0 }}>基于你的财富地位，黑市商人为你准备了以下专属蓝图。</p>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
                {timeLeft && (
                  <div style={{ textAlign: 'right' }}>
                    <div style={{ fontSize: '10px', color: '#444', textTransform: 'uppercase' }}>货架自动刷新倒计时</div>
                    <div style={{ fontSize: '16px', color: '#faad14', fontFamily: 'monospace', fontWeight: 'bold' }}>{timeLeft}</div>
                  </div>
                )}
                <button 
                  onClick={() => refreshStoreCatalog(true)}
                  disabled={loading}
                  className="cyber-button mini"
                  style={{ 
                    background: 'rgba(250, 173, 20, 0.1)', 
                    borderColor: '#faad1444',
                    color: '#faad14',
                    padding: '8px 16px'
                  }}
                >
                  {loading ? '刷新中...' : '手动刷新货架'}
                </button>
              </div>
            </div>

            <div style={{ 
              display: 'grid', 
              gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', 
              gap: '20px' 
            }}>
              {storeItems.map((it, idx) => {
                const rColor = getRarityColor(it.rarity)
                const isSelected = purchaseKind === it.kind && idx === storeItems.findIndex(s => s.kind === it.kind)
                
                return (
                  <div 
                    key={`${it.kind}-${idx}`} 
                    className={`market-blueprint-card ${isSelected ? 'selected' : ''}`}
                    style={{ 
                      background: 'rgba(20, 20, 20, 0.6)', 
                      borderWidth: '1px',
                      borderStyle: 'solid',
                      borderColor: isSelected ? '#faad14' : 'rgba(255,255,255,0.05)',
                      borderRadius: '2px',
                      padding: '24px',
                      display: 'flex',
                      flexDirection: 'column',
                      gap: '16px',
                      position: 'relative',
                      cursor: 'pointer',
                      transition: 'all 0.4s cubic-bezier(0.165, 0.84, 0.44, 1)',
                      overflow: 'hidden',
                      backdropFilter: 'blur(10px)'
                    }}
                    onClick={() => {
                      setPurchaseKind(it.kind)
                      setPurchasePrice(it.price_cash)
                      if (it.presets?.[0]) setPurchasePresetId(it.presets[0].preset_id)
                    }}
                  >
                    {/* Background Noise/Pattern */}
                    <div style={{ position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, opacity: 0.03, pointerEvents: 'none', background: 'url("data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAADIAAAAyBAMAAADsEZWCAAAAGFBMVEUAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAt6pY6AAAAB3RSTlMAoIDAgICA0RECDAAAAEtJREFUOMtjYEAFeR0IXE9IDAKiUAgIgoAIFALCEAisEIYQAoGICBQCghAIhIDoEYYpBAIBURBCIBRCEIAKghAIhIDoEQIDUAgIBEYIABWzI0Y39r8oAAAAAElFTkSuQmCC")' }} />

                    {/* Rarity Accent */}
                    <div style={{ position: 'absolute', top: 0, left: 0, width: '4px', height: '100%', background: rColor, opacity: isSelected ? 1 : 0.3 }} />
                    
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', zIndex: 2 }}>
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                        <span style={{ color: rColor, fontSize: '9px', fontWeight: '900', textTransform: 'uppercase', letterSpacing: '2px' }}>{getRarityLabel(it.rarity)} Protocol</span>
                        <span style={{ color: '#fff', fontWeight: '900', fontSize: '18px', letterSpacing: '1px' }}>{it.kind}</span>
                      </div>
                      <div style={{ textAlign: 'right' }}>
                        <div style={{ color: '#faad14', fontSize: '20px', fontWeight: '900', fontFamily: 'monospace' }}>
                          ${it.price_cash.toLocaleString()}
                        </div>
                      </div>
                    </div>

                    <p style={{ fontSize: '13px', color: '#666', margin: 0, lineHeight: '1.6', height: '42px', overflow: 'hidden', zIndex: 2 }}>
                      {it.description || it.preview_text}
                    </p>

                    <div style={{ marginTop: 'auto', display: 'flex', justifyContent: 'space-between', alignItems: 'center', zIndex: 2, borderTop: '1px solid rgba(255,255,255,0.05)', paddingTop: '12px' }}>
                      <div style={{ display: 'flex', gap: '12px', fontSize: '10px', color: '#444', fontWeight: 'bold' }}>
                        <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}><Newspaper size={10} /> {it.presets?.length || 0} TEMPLATES</span>
                        <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}><Clock size={10} /> {it.default_ttl_hours || 6}H TTL</span>
                      </div>
                      {it.tags && it.tags.length > 0 && (
                        <div style={{ 
                          background: 'rgba(250, 173, 20, 0.1)', 
                          padding: '2px 8px', 
                          borderRadius: '2px', 
                          fontSize: '9px', 
                          color: '#faad14',
                          border: '1px solid rgba(250, 173, 20, 0.2)',
                          textTransform: 'uppercase',
                          fontWeight: 'bold'
                        }}>
                          {it.tags[0]}
                        </div>
                      )}
                    </div>
                  </div>
                )
              })}
            </div>
          </div>

          {/* Right: Configurator & Preview */}
          <div style={{ 
            display: 'flex', 
            flexDirection: 'column', 
            gap: '24px',
            background: 'rgba(26, 26, 26, 0.6)',
            borderWidth: '1px',
            borderStyle: 'solid',
            borderColor: 'rgba(250, 173, 20, 0.2)',
            borderRadius: '4px',
            padding: '32px',
            position: 'sticky',
            top: 0,
            backdropFilter: 'blur(20px)'
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '8px' }}>
              <div style={{ width: '4px', height: '20px', background: '#faad14' }} />
              <h3 style={{ margin: 0, fontSize: '16px', color: '#faad14', fontWeight: '900', letterSpacing: '2px', textTransform: 'uppercase' }}>
                Fabrication Unit
              </h3>
            </div>

            {previewItem ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
                {/* Visual Preview */}
                <div style={{ 
                  display: 'flex', 
                  justifyContent: 'center', 
                  padding: '20px',
                  background: 'rgba(0,0,0,0.4)',
                  borderRadius: '2px',
                  border: '1px dashed rgba(250, 173, 20, 0.1)'
                }}>
                  <IntelligenceCard 
                    item={previewItem} 
                    stage="PREVIEW" 
                    showActions={false}
                    className="preview-card-animation"
                  />
                </div>

                <div style={{ 
                  display: 'flex', 
                  flexDirection: 'column', 
                  gap: '12px', 
                  background: 'rgba(0,0,0,0.6)', 
                  padding: '20px', 
                  borderRadius: '2px',
                  borderLeft: '2px solid #faad14'
                }}>
                  <div style={{ fontSize: '10px', color: '#444', fontWeight: '900', letterSpacing: '2px', textTransform: 'uppercase' }}>
                    Blueprint Specifications
                  </div>
                  <div style={{ fontSize: '13px', color: '#aaa', lineHeight: '1.7', fontFamily: 'system-ui' }}>
                    {activeStoreItem?.description || activeStoreItem?.preview_text}
                  </div>
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px', marginTop: '8px' }}>
                    <div style={{ background: 'rgba(255,255,255,0.02)', padding: '12px', borderRadius: '2px', border: '1px solid rgba(255,255,255,0.05)' }}>
                      <div style={{ fontSize: '9px', color: '#444', marginBottom: '4px', textTransform: 'uppercase' }}>Duration</div>
                      <div style={{ color: '#fff', fontSize: '13px', fontWeight: 'bold', fontFamily: 'monospace' }}>{activeStoreItem?.default_ttl_hours || 6} HOURS</div>
                    </div>
                    <div style={{ background: 'rgba(255,255,255,0.02)', padding: '12px', borderRadius: '2px', border: '1px solid rgba(255,255,255,0.05)' }}>
                      <div style={{ fontSize: '9px', color: '#444', marginBottom: '4px', textTransform: 'uppercase' }}>Available Sets</div>
                      <div style={{ color: '#fff', fontSize: '13px', fontWeight: 'bold', fontFamily: 'monospace' }}>{activeStoreItem?.presets?.length || 0} VARIANTS</div>
                    </div>
                  </div>
                </div>

                {/* Controls */}
                <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                    <label style={{ fontSize: '10px', color: '#444', textTransform: 'uppercase', letterSpacing: '1px', fontWeight: 'bold' }}>Select Prototype Base</label>
                    <select
                      value={purchasePresetId}
                      onChange={(e) => setPurchasePresetId(e.target.value)}
                      style={{ 
                        background: 'rgba(0,0,0,0.8)', 
                        border: '1px solid #333', 
                        color: '#fff', 
                        padding: '12px', 
                        borderRadius: '2px', 
                        fontSize: '13px',
                        outline: 'none',
                        cursor: 'pointer'
                      }}
                    >
                      {activeStoreItem?.presets?.map(p => (
                        <option key={p.preset_id} value={p.preset_id}>{p.preset_id}</option>
                      ))}
                    </select>
                  </div>

                  {activeStoreItem?.symbol_options && activeStoreItem.symbol_options.length > 0 && (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                      <label style={{ fontSize: '10px', color: '#444', textTransform: 'uppercase', letterSpacing: '1px', fontWeight: 'bold' }}>Target Asset Binding</label>
                      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
                        {activeStoreItem.symbol_options.map(s => (
                          <button
                            key={s}
                            onClick={() => setPurchaseSymbol(s)}
                            style={{ 
                              background: purchaseSymbol === s ? '#faad14' : 'rgba(0,0,0,0.4)',
                              color: purchaseSymbol === s ? '#000' : '#666',
                              border: purchaseSymbol === s ? '1px solid #faad14' : '1px solid #222',
                              padding: '6px 14px',
                              borderRadius: '2px',
                              fontSize: '11px',
                              fontWeight: 'bold',
                              fontFamily: 'monospace',
                              cursor: 'pointer',
                              transition: 'all 0.2s'
                            }}
                          >
                            ${s}
                          </button>
                        ))}
                      </div>
                    </div>
                  )}

                  <div style={{ marginTop: '12px', borderTop: '1px solid rgba(255,255,255,0.05)', paddingTop: '24px' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
                      <span style={{ color: '#444', fontSize: '12px', textTransform: 'uppercase', letterSpacing: '1px' }}>Acquisition Cost</span>
                      <span style={{ color: '#faad14', fontSize: '24px', fontWeight: '900', fontFamily: 'monospace' }}>${purchasePrice.toLocaleString()}</span>
                    </div>
                    <button 
                      onClick={purchase}
                      style={{ 
                        width: '100%',
                        background: '#faad14', 
                        color: '#000', 
                        border: 'none', 
                        padding: '18px', 
                        borderRadius: '2px', 
                        fontWeight: '900', 
                        cursor: 'pointer',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        gap: '12px',
                        fontSize: '14px',
                        textTransform: 'uppercase',
                        letterSpacing: '2px',
                        boxShadow: '0 0 30px rgba(250, 173, 20, 0.2)',
                        transition: 'all 0.3s'
                      }}
                      onMouseEnter={(e) => {
                        e.currentTarget.style.background = '#ffc53d'
                        e.currentTarget.style.boxShadow = '0 0 40px rgba(250, 173, 20, 0.4)'
                      }}
                      onMouseLeave={(e) => {
                        e.currentTarget.style.background = '#faad14'
                        e.currentTarget.style.boxShadow = '0 0 30px rgba(250, 173, 20, 0.2)'
                      }}
                    >
                      <ShoppingCart size={18} />
                      Inject Intelligence
                    </button>
                  </div>
                </div>
              </div>
            ) : (
              <div style={{ height: '400px', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#222', textAlign: 'center', textTransform: 'uppercase', letterSpacing: '2px', fontSize: '12px' }}>
                Select a prototype to<br />begin fabrication
              </div>
            )}
          </div>
        </div>
      )}

      {/* Overlays / Modals */}
      {showMutatePanel && (
        <Overlay title="🖋️ 篡改情报变体" onClose={() => setShowMutatePanel(false)} color="#faad14">
          <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            <textarea 
              value={mutateText} 
              onChange={e => setMutateText(e.target.value)}
              rows={6}
              style={{ width: '100%', padding: '12px', background: '#000', color: '#fff', border: '1px solid #333', borderRadius: '8px', fontSize: '14px', lineHeight: '1.6' }}
            />
            <div style={{ display: 'flex', gap: '12px', alignItems: 'center' }}>
              <span style={{ fontSize: '12px', color: '#666' }}>投入修改预算:</span>
              <input value={mutateSpendCash} onChange={e => setMutateSpendCash(e.target.value)} placeholder="0" style={{ flex: 1, background: '#000', border: '1px solid #333', color: '#fff', padding: '8px', borderRadius: '4px' }} />
            </div>
            <div style={{ display: 'flex', gap: '12px' }}>
              <button onClick={() => setShowMutatePanel(false)} className="cyber-button" style={{ flex: 1, background: '#333' }}>取消</button>
              <button 
                onClick={async () => {
                  try {
                    const r = await Api.newsMutateVariant({
                      parent_variant_id: mutateVariantId,
                      editor_id: `user:${playerId}`,
                      new_text: mutateText,
                      spend_cash: mutateSpendCash ? Number(mutateSpendCash) : undefined,
                    })
                    notify('success', `篡改序列执行成功`)
                    setTargetVariantId(r.new_variant_id)
                    setShowMutatePanel(false)
                    refreshInbox()
                  } catch (e) { notify('error', '篡改序列执行失败') }
                }}
                className="cyber-button" 
                style={{ flex: 1, background: '#faad14', color: '#000', fontWeight: 'bold' }}
              >
                注入修改变体
              </button>
            </div>
          </div>
        </Overlay>
      )}

      {showSuppressPanel && (
        <Overlay title="🚫 抑制抹除序列" onClose={() => setShowSuppressPanel(false)} color="#ff4d4f">
          <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            <div style={{ background: '#ff4d4f11', border: '1px solid #ff4d4f33', padding: '12px', borderRadius: '8px', fontSize: '12px', color: '#ff4d4f' }}>
              警告：抑制序列将消耗大量资源尝试抹除该情报链的所有后续传播。
            </div>
            <MetaBox label="情报链 ID" value={suppressChainId} />
            <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
              <label style={{ fontSize: '11px', color: '#555' }}>投入影响力 (Influence)</label>
              <input type="number" value={suppressInfluence} onChange={e => setSuppressInfluence(Number(e.target.value))} style={{ background: '#000', border: '1px solid #333', color: '#fff', padding: '8px', borderRadius: '4px' }} />
            </div>
            <div style={{ display: 'flex', gap: '12px' }}>
              <button onClick={() => setShowSuppressPanel(false)} className="cyber-button" style={{ flex: 1, background: '#333' }}>放弃</button>
              <button 
                disabled={suppressing}
                onClick={async () => {
                  if (!suppressChainId) return notify('error', '未检测到情报链ID')
                  setSuppressing(true)
                  try {
                    await Api.newsSuppress({
                      actor_id: `user:${playerId}`,
                      chain_id: suppressChainId,
                      spend_influence: suppressInfluence
                    })
                    notify('success', '抹除序列已上线')
                    setShowSuppressPanel(false)
                  } catch (e) { notify('error', '抹除序列初始化失败') } 
                  finally { setSuppressing(false) }
                }}
                className="cyber-button" 
                style={{ flex: 1, background: '#ff4d4f', color: '#fff' }}
              >
                {suppressing ? 'EXECUTING...' : '执行抹除'}
              </button>
            </div>
          </div>
        </Overlay>
      )}

      {showContractPanel && contractNewsItem && (
        <Overlay title="🤝 引用签约协议" onClose={() => setShowContractPanel(false)} color="var(--terminal-info)">
          <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            <ContractFormFromNews 
              newsItem={contractNewsItem}
              onError={(msg) => msg ? notify('error', msg) : setShowContractPanel(false)}
            />
            <button onClick={() => setShowContractPanel(false)} className="cyber-button" style={{ background: '#333' }}>放弃签约</button>
          </div>
        </Overlay>
      )}

      <style>{`
        @keyframes slideDown {
          from { opacity: 0; transform: translateY(-10px); }
          to { opacity: 1; transform: translateY(0); }
        }
        .market-blueprint-card:hover {
          border-color: #faad1488 !important;
          transform: translateY(-4px);
        }
        .market-blueprint-card.selected {
          box-shadow: 0 0 30px #faad1422;
        }
      `}</style>
    </div>
  )
}

function TabBtn({ active, onClick, icon: Icon, label }: { active: boolean, onClick: () => void, icon: any, label: string }) {
  return (
    <button 
      onClick={onClick}
      style={{
        background: active ? 'rgba(24, 144, 255, 0.1)' : 'transparent',
        borderWidth: '1px',
        borderStyle: 'solid',
        borderColor: active ? 'var(--terminal-info)' : 'rgba(255,255,255,0.05)',
        padding: '12px 24px',
        borderRadius: '2px', // 尖锐边缘
        color: active ? '#fff' : '#666',
        fontSize: '13px',
        fontWeight: 'bold',
        textTransform: 'uppercase',
        letterSpacing: '2px',
        cursor: 'pointer',
        display: 'flex',
        alignItems: 'center',
        gap: '10px',
        transition: 'all 0.3s cubic-bezier(0.4, 0, 0.2, 1)',
        position: 'relative',
        overflow: 'hidden'
      }}
    >
      {active && (
        <div style={{
          position: 'absolute',
          top: 0,
          left: 0,
          width: '2px',
          height: '100%',
          background: 'var(--terminal-info)',
          boxShadow: '0 0 10px var(--terminal-info)'
        }} />
      )}
      <Icon size={16} color={active ? 'var(--terminal-info)' : '#666'} />
      {label}
    </button>
  )
}

function FilterChip({ active, onClick, label }: { active: boolean, onClick: () => void, label: string }) {
  return (
    <button 
      onClick={onClick}
      style={{
        background: active ? 'rgba(24, 144, 255, 0.15)' : 'rgba(255,255,255,0.02)',
        borderWidth: '1px',
        borderStyle: 'solid',
        borderColor: active ? 'var(--terminal-info)' : 'rgba(255,255,255,0.05)',
        padding: '4px 14px',
        borderRadius: '2px',
        color: active ? '#fff' : '#444',
        fontSize: '10px',
        cursor: 'pointer',
        fontWeight: '900',
        letterSpacing: '1px',
        textTransform: 'uppercase',
        transition: 'all 0.2s'
      }}
    >
      {label}
    </button>
  )
}

function MetaBox({ label, value }: { label: string, value: string }) {
  return (
    <div style={{ 
      display: 'flex', 
      flexDirection: 'column', 
      gap: '4px',
      background: 'rgba(255,255,255,0.02)',
      padding: '10px',
      borderRadius: '2px',
      border: '1px solid rgba(255,255,255,0.05)'
    }}>
      <span style={{ fontSize: '9px', color: '#444', textTransform: 'uppercase', letterSpacing: '1px', fontWeight: 'bold' }}>{label}</span>
      <span style={{ fontSize: '12px', color: '#aaa', overflow: 'hidden', textOverflow: 'ellipsis', fontFamily: 'monospace' }}>{value}</span>
    </div>
  )
}

function Overlay({ title, children, onClose, color }: { title: string, children: React.ReactNode, onClose: () => void, color: string }) {
  return (
    <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.85)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000, backdropFilter: 'blur(4px)' }}>
      <div style={{ 
        width: '500px', 
        background: '#141414', 
        border: `1px solid ${color}44`, 
        borderRadius: '16px',
        padding: '24px',
        boxShadow: `0 20px 40px rgba(0,0,0,0.5), 0 0 20px ${color}11`
      }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
          <h3 style={{ margin: 0, color, letterSpacing: '1px' }}>{title}</h3>
          <button onClick={onClose} style={{ background: 'none', border: 'none', color: '#555', cursor: 'pointer', fontSize: '20px' }}>✕</button>
        </div>
        {children}
      </div>
    </div>
  )
}

