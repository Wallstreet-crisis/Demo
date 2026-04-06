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
import { Newspaper, ShoppingCart, Filter, ArrowUpDown, Info } from 'lucide-react'

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

  async function refreshStoreCatalog(): Promise<void> {
    try {
      const r = await Api.newsStoreCatalog()
      const items = Array.isArray(r.items) ? r.items : []
      setStoreItems(items)

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
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : (e instanceof Error ? e.message : String(e))
      notify('error', `获取新闻商店目录失败: ${msg}`)
      setStoreItems([])
    }
  }

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
              background: '#1a1a1a',
              padding: '10px 16px',
              borderRadius: '8px',
              border: '1px solid #333'
            }}>
              <div style={{ display: 'flex', gap: '12px', alignItems: 'center' }}>
                <Filter size={14} color="#666" />
                <div style={{ display: 'flex', gap: '6px' }}>
                  <FilterChip active={filterKind === 'ALL'} onClick={() => setFilterKind('ALL')} label="全部" />
                  {kinds.map(k => (
                    <FilterChip key={k} active={filterKind === k} onClick={() => setFilterKind(k)} label={k} />
                  ))}
                </div>
              </div>
              <div style={{ display: 'flex', gap: '12px', alignItems: 'center' }}>
                <button 
                  onClick={() => setSortOrder(prev => prev === 'newest' ? 'oldest' : 'newest')}
                  style={{ background: 'none', border: 'none', color: '#888', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '4px', fontSize: '12px' }}
                >
                  <ArrowUpDown size={14} />
                  {sortOrder === 'newest' ? '最新优先' : '最早优先'}
                </button>
                <button 
                  onClick={refreshInbox} 
                  disabled={loading} 
                  className="cyber-button mini"
                  style={{ background: 'var(--terminal-info)22', border: '1px solid var(--terminal-info)44' }}
                >
                  {loading ? 'SYNCING...' : 'REFRESH'}
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
                  border: '2px dashed #333',
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
            gap: '20px',
            overflowY: 'auto',
            paddingRight: '4px'
          }}>
            {selectedInboxItem ? (
              <div style={{ 
                background: '#1a1a1a',
                border: '1px solid var(--terminal-info)44',
                borderRadius: '12px',
                padding: '20px',
                display: 'flex',
                flexDirection: 'column',
                gap: '16px'
              }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <Info size={16} color="var(--terminal-info)" />
                    <span style={{ fontWeight: 'bold', fontSize: '14px', letterSpacing: '1px' }}>情报分析报告</span>
                  </div>
                  <button onClick={() => setSelectedInboxItem(null)} style={{ background: 'none', border: 'none', color: '#555', cursor: 'pointer' }}>✕</button>
                </div>

                <div style={{ fontSize: '14px', lineHeight: '1.6', color: '#fff', background: '#000', padding: '12px', borderRadius: '8px', borderLeft: '4px solid var(--terminal-info)' }}>
                  {selectedInboxItem.text}
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                  <MetaBox label="变体版本" value={selectedInboxItem.variant_id.slice(0, 8)} />
                  <MetaBox label="来源实体" value={selectedInboxItem.from_actor_id} />
                  <MetaBox label="影响标的" value={selectedInboxItem.symbols?.join(', ') || '全局影响'} />
                  <MetaBox label="投递策略" value={selectedInboxItem.delivery_reason} />
                </div>

                {!!selectedInboxItem.truth_payload && (
                  <div style={{ background: '#0a0a0a', padding: '12px', borderRadius: '8px', border: '1px solid #333' }}>
                    <div style={{ fontSize: '10px', color: '#555', marginBottom: '8px', textTransform: 'uppercase' }}>内核载荷解析 (Truth Payload)</div>
                    <pre style={{ margin: 0, fontSize: '11px', color: 'var(--terminal-success)', whiteSpace: 'pre-wrap', fontFamily: 'monospace' }}>
                      {String(JSON.stringify(selectedInboxItem.truth_payload, null, 2) ?? '')}
                    </pre>
                  </div>
                )}
              </div>
            ) : (
              <div style={{ 
                background: '#1a1a1a22',
                border: '1px dashed #333',
                borderRadius: '12px',
                padding: '40px 20px',
                textAlign: 'center',
                color: '#555'
              }}>
                选择一张情报卡牌启动分析序列
              </div>
            )}

            {/* Propagate Panel */}
            <div style={{ 
              background: '#1a1a1a',
              border: '1px solid var(--terminal-success)44',
              borderRadius: '12px',
              padding: '20px',
              display: 'flex',
              flexDirection: 'column',
              gap: '16px'
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <ArrowUpDown size={16} color="var(--terminal-success)" />
                <span style={{ fontWeight: 'bold', fontSize: '14px', letterSpacing: '1px' }}>传播与扩音器模式</span>
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                  <label style={{ fontSize: '11px', color: '#555' }}>目标变体识别码</label>
                  <input 
                    value={targetVariantId} 
                    onChange={e => setTargetVariantId(e.target.value)} 
                    placeholder="选定卡牌自动映射..."
                    style={{ background: '#000', border: '1px solid #333', color: '#fff', padding: '8px', borderRadius: '4px', fontSize: '12px' }}
                  />
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                    <label style={{ fontSize: '11px', color: '#555' }}>目标覆盖数</label>
                    <input type="number" value={propLimit} onChange={(e) => setPropLimit(Number(e.target.value))} style={{ background: '#000', border: '1px solid #333', color: '#fff', padding: '8px', borderRadius: '4px' }} />
                  </div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                    <label style={{ fontSize: '11px', color: '#555' }}>预算分配 ($)</label>
                    <input value={propSpendCash} onChange={(e) => setPropSpendCash(e.target.value)} style={{ background: '#000', border: '1px solid #333', color: '#fff', padding: '8px', borderRadius: '4px' }} />
                  </div>
                </div>
                
                {propQuote && (
                  <div style={{ background: 'rgba(0,0,0,0.3)', padding: '10px', borderRadius: '6px', border: '1px solid var(--terminal-success)22', fontSize: '11px' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
                      <span style={{ color: '#555' }}>可触达节点</span>
                      <span style={{ color: 'var(--terminal-success)' }}>{propQuote.affordable_limit}</span>
                    </div>
                    <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                      <span style={{ color: '#555' }}>预计总支出</span>
                      <span style={{ color: 'var(--terminal-warn)' }}>${propQuote.estimated_total_cost.toFixed(2)}</span>
                    </div>
                  </div>
                )}

                <button 
                  onClick={propagateLast} 
                  className="cyber-button" 
                  style={{ background: 'var(--terminal-success)', color: '#000', fontWeight: 'bold' }}
                >
                  启动传播序列
                </button>
              </div>
            </div>

            {/* Quick Actions */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
              <button 
                onClick={() => selectedInboxItem ? handleAction('mutate', selectedInboxItem) : notify('error', '请先选择一张情报卡牌')}
                style={{ background: 'var(--terminal-warn)22', border: '1px solid var(--terminal-warn)44', color: 'var(--terminal-warn)', padding: '10px', borderRadius: '8px', cursor: 'pointer', fontSize: '13px' }}
              >
                🖋️ 修改/篡改
              </button>
              <button 
                onClick={() => selectedInboxItem ? handleAction('contract', selectedInboxItem) : notify('error', '请先选择一张情报卡牌')}
                style={{ background: 'var(--terminal-info)22', border: '1px solid var(--terminal-info)44', color: 'var(--terminal-info)', padding: '10px', borderRadius: '8px', cursor: 'pointer', fontSize: '13px' }}
              >
                🤝 引用/签约
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
              <button 
                onClick={refreshStoreCatalog}
                disabled={loading}
                style={{ background: 'none', border: '1px solid #333', color: '#666', padding: '4px 12px', borderRadius: '4px', fontSize: '11px', cursor: 'pointer' }}
              >
                {loading ? '同步中...' : '刷新货架'}
              </button>
            </div>

            <div style={{ 
              display: 'grid', 
              gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', 
              gap: '20px' 
            }}>
              {storeItems.map((it, idx) => {
                const rColor = getRarityColor(it.rarity)
                const isSelected = purchaseKind === it.kind && idx === storeItems.findIndex(s => s.kind === it.kind) // 简单处理重复类型
                
                return (
                  <div 
                    key={`${it.kind}-${idx}`} 
                    className={`market-blueprint-card ${isSelected ? 'selected' : ''}`}
                    style={{ 
                      background: '#141414', 
                      border: isSelected ? `2px solid ${rColor}` : '1px solid #333',
                      borderRadius: '12px',
                      padding: '20px',
                      display: 'flex',
                      flexDirection: 'column',
                      gap: '12px',
                      position: 'relative',
                      cursor: 'pointer',
                      transition: 'all 0.2s',
                      overflow: 'hidden'
                    }}
                    onClick={() => {
                      setPurchaseKind(it.kind)
                      setPurchasePrice(it.price_cash)
                      if (it.presets?.[0]) setPurchasePresetId(it.presets[0].preset_id)
                    }}
                  >
                    {/* Rarity Stripe */}
                    <div style={{ position: 'absolute', top: 0, left: 0, width: '100%', height: '3px', background: rColor }} />
                    
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <div style={{ display: 'flex', flexDirection: 'column' }}>
                        <span style={{ color: rColor, fontSize: '10px', fontWeight: 'bold', textTransform: 'uppercase' }}>{getRarityLabel(it.rarity)}</span>
                        <span style={{ color: '#fff', fontWeight: 'bold', fontSize: '16px' }}>{it.kind}</span>
                      </div>
                      <div style={{ textAlign: 'right' }}>
                        <div style={{ color: '#faad14', fontSize: '16px', fontWeight: 'bold' }}>
                          ${it.price_cash.toLocaleString()}
                        </div>
                      </div>
                    </div>

                    <p style={{ fontSize: '12px', color: '#888', margin: 0, lineHeight: '1.5', height: '36px', overflow: 'hidden' }}>
                      {it.description || it.preview_text}
                    </p>

                    <div style={{ marginTop: 'auto', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <div style={{ display: 'flex', gap: '8px', fontSize: '10px', color: '#555' }}>
                        <span>{it.presets?.length || 0} 模板</span>
                        <span>•</span>
                        <span>{it.default_ttl_hours || 6}h 效期</span>
                      </div>
                      {it.tags && it.tags.length > 0 && (
                        <div style={{ background: '#222', padding: '2px 6px', borderRadius: '4px', fontSize: '9px', color: '#666' }}>
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
            background: '#1a1a1a',
            border: '1px solid #333',
            borderRadius: '16px',
            padding: '24px',
            position: 'sticky',
            top: 0
          }}>
            <h3 style={{ margin: 0, fontSize: '16px', color: '#faad14', display: 'flex', alignItems: 'center', gap: '8px' }}>
              <ShoppingCart size={18} />
              蓝图配置中心 (Configurator)
            </h3>

            {previewItem ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
                {/* Visual Preview */}
                <div style={{ display: 'flex', justifyContent: 'center', padding: '10px 0' }}>
                  <IntelligenceCard 
                    item={previewItem} 
                    stage="PREVIEW" 
                    showActions={false}
                    className="preview-card-animation"
                  />
                </div>

                <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', background: '#111', border: '1px solid #2a2a2a', borderRadius: '12px', padding: '14px' }}>
                  <div style={{ fontSize: '12px', color: '#faad14', fontWeight: 'bold', letterSpacing: '1px' }}>
                    蓝图特性
                  </div>
                  <div style={{ fontSize: '13px', color: '#aaa', lineHeight: '1.6' }}>
                    {activeStoreItem?.description || activeStoreItem?.preview_text}
                  </div>
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px' }}>
                    <div style={{ background: '#0a0a0a', border: '1px solid #222', borderRadius: '8px', padding: '10px' }}>
                      <div style={{ fontSize: '10px', color: '#666', marginBottom: '4px' }}>生命周期</div>
                      <div style={{ color: '#fff', fontSize: '13px' }}>{activeStoreItem?.default_ttl_hours || 6} 小时</div>
                    </div>
                    <div style={{ background: '#0a0a0a', border: '1px solid #222', borderRadius: '8px', padding: '10px' }}>
                      <div style={{ fontSize: '10px', color: '#666', marginBottom: '4px' }}>模板数量</div>
                      <div style={{ color: '#fff', fontSize: '13px' }}>{activeStoreItem?.presets?.length || 0} 个</div>
                    </div>
                  </div>
                  {!!activeStoreItem?.tags?.length && (
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
                      {activeStoreItem.tags.map(tag => (
                        <span key={tag} style={{ fontSize: '11px', color: '#888', background: '#1f1f1f', border: '1px solid #333', borderRadius: '999px', padding: '4px 10px' }}>
                          {tag}
                        </span>
                      ))}
                    </div>
                  )}
                </div>

                {/* Controls */}
                <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                    <label style={{ fontSize: '11px', color: '#555', textTransform: 'uppercase' }}>选择底本模板 (Preset)</label>
                    <select
                      value={purchasePresetId}
                      onChange={(e) => setPurchasePresetId(e.target.value)}
                      style={{ background: '#000', border: '1px solid #444', color: '#fff', padding: '10px', borderRadius: '6px', fontSize: '13px' }}
                    >
                      {activeStoreItem?.presets?.map(p => (
                        <option key={p.preset_id} value={p.preset_id}>{p.preset_id}</option>
                      ))}
                    </select>
                  </div>

                  {activeStoreItem?.symbol_options && activeStoreItem.symbol_options.length > 0 && (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                      <label style={{ fontSize: '11px', color: '#555', textTransform: 'uppercase' }}>绑定目标标的 (Symbol)</label>
                      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
                        {activeStoreItem.symbol_options.map(s => (
                          <button
                            key={s}
                            onClick={() => setPurchaseSymbol(s)}
                            style={{ 
                              background: purchaseSymbol === s ? '#faad14' : '#000',
                              color: purchaseSymbol === s ? '#000' : '#888',
                              border: purchaseSymbol === s ? '1px solid #faad14' : '1px solid #333',
                              padding: '4px 12px',
                              borderRadius: '4px',
                              fontSize: '12px',
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

                  <div style={{ marginTop: '10px', borderTop: '1px solid #333', paddingTop: '20px' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
                      <span style={{ color: '#888', fontSize: '14px' }}>买断费用</span>
                      <span style={{ color: '#faad14', fontSize: '20px', fontWeight: 'bold' }}>${purchasePrice.toLocaleString()}</span>
                    </div>
                    <button 
                      onClick={purchase}
                      style={{ 
                        width: '100%',
                        background: '#faad14', 
                        color: '#000', 
                        border: 'none', 
                        padding: '14px', 
                        borderRadius: '8px', 
                        fontWeight: 'bold', 
                        cursor: 'pointer',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        gap: '10px',
                        fontSize: '15px'
                      }}
                    >
                      <ShoppingCart size={20} />
                      买断并注入系统
                    </button>
                  </div>
                </div>
              </div>
            ) : (
              <div style={{ height: '400px', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#444', textAlign: 'center' }}>
                请从左侧选择一个<br />情报原型开始配置
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
        background: active ? '#1a1a1a' : 'transparent',
        border: active ? '1px solid #333' : '1px solid transparent',
        borderBottom: active ? '1px solid transparent' : '1px solid transparent',
        padding: '10px 20px',
        borderRadius: '8px 8px 0 0',
        color: active ? '#fff' : '#666',
        cursor: 'pointer',
        display: 'flex',
        alignItems: 'center',
        gap: '8px',
        fontSize: '14px',
        fontWeight: active ? 'bold' : 'normal',
        transition: 'all 0.2s'
      }}
    >
      <Icon size={18} color={active ? 'var(--terminal-info)' : '#666'} />
      {label}
    </button>
  )
}

function FilterChip({ active, onClick, label }: { active: boolean, onClick: () => void, label: string }) {
  return (
    <button 
      onClick={onClick}
      style={{
        background: active ? 'var(--terminal-info)' : 'rgba(255,255,255,0.05)',
        border: 'none',
        padding: '4px 12px',
        borderRadius: '4px',
        color: active ? '#000' : '#888',
        fontSize: '11px',
        cursor: 'pointer',
        fontWeight: active ? 'bold' : 'normal'
      }}
    >
      {label}
    </button>
  )
}

function MetaBox({ label, value }: { label: string, value: string }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '2px' }}>
      <span style={{ fontSize: '10px', color: '#555', textTransform: 'uppercase' }}>{label}</span>
      <span style={{ fontSize: '12px', color: '#aaa', overflow: 'hidden', textOverflow: 'ellipsis' }}>{value}</span>
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

