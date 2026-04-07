
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { Clock, LayoutDashboard, LogOut, Newspaper, ShoppingCart } from 'lucide-react'
import {
  Api,
  ApiError,
  WsClient,
  type NewsInboxResponse,
  type NewsInboxResponseItem,
  type NewsStoreCatalogItem,
} from '../api'
import { useNotification } from '../app/NotificationContext'
import { useAppSession } from '../app/context'
import ContractFormFromNews from '../components/ContractFormFromNews'
import IntelligenceCard from '../components/IntelligenceCard'

function getEventType(payload: unknown): string | null {
  if (!payload || typeof payload !== 'object') return null
  const eventType = (payload as Record<string, unknown>).event_type
  return typeof eventType === 'string' ? eventType : null
}

function getRarityColor(rarity?: string): string {
  switch ((rarity || 'COMMON').toUpperCase()) {
    case 'UNCOMMON':
      return '#52c41a'
    case 'RARE':
      return '#1890ff'
    case 'EPIC':
      return '#722ed1'
    case 'LEGENDARY':
      return '#faad14'
    default:
      return '#8c8c8c'
  }
}

export default function NewsPage() {
  const { playerId, roomId } = useAppSession()
  const { notify } = useNotification()

  const [loading, setLoading] = useState(true)
  const [activeTab, setActiveTab] = useState<'collection' | 'store'>('collection')
  const [inbox, setInbox] = useState<NewsInboxResponse | null>(null)
  const [ownedCards, setOwnedCards] = useState<string[]>([])
  const [selectedInboxItem, setSelectedInboxItem] = useState<NewsInboxResponseItem | null>(null)
  const [storeItems, setStoreItems] = useState<NewsStoreCatalogItem[]>([])
  const [storeExpiresAt, setStoreExpiresAt] = useState('')
  const [timeLeft, setTimeLeft] = useState('')
  const [purchaseKind, setPurchaseKind] = useState('')
  const [purchasePrice, setPurchasePrice] = useState(0)
  const [purchaseInitialText, setPurchaseInitialText] = useState('')
  const [purchaseSymbol, setPurchaseSymbol] = useState('')
  const [filterKind, setFilterKind] = useState('ALL')
  const [sortOrder, setSortOrder] = useState<'newest' | 'oldest'>('newest')
  const [targetVariantId, setTargetVariantId] = useState('')
  const [propLimit, setPropLimit] = useState(100)
  const [propSpendCash, setPropSpendCash] = useState('500')
  const [propQuote, setPropQuote] = useState<{
    mutation_depth: number
    per_delivery_cost: number
    requested_limit: number
    affordable_limit: number
    estimated_total_cost: number
  } | null>(null)
  const [showMutatePanel, setShowMutatePanel] = useState(false)
  const [mutateVariantId, setMutateVariantId] = useState('')
  const [mutateText, setMutateText] = useState('')
  const [mutateSpendCash, setMutateSpendCash] = useState('')
  const [showSuppressPanel, setShowSuppressPanel] = useState(false)
  const [suppressChainId, setSuppressChainId] = useState('')
  const [suppressInfluence, setSuppressInfluence] = useState(500)
  const [suppressing, setSuppressing] = useState(false)
  const [showContractPanel, setShowContractPanel] = useState(false)
  const [contractNewsItem, setContractNewsItem] = useState<NewsInboxResponseItem | null>(null)

  const refreshTimerRef = useRef<number | null>(null)
  const ws = useMemo(() => new WsClient({ baseUrl: import.meta.env.VITE_API_BASE_URL }), [])

  const refreshInbox = useCallback(async () => {
    if (!playerId) return
    setLoading(true)
    try {
      const response = await Api.newsInbox(`user:${playerId}`, 50)
      setInbox(response)
      setSelectedInboxItem((prev) => {
        if (!prev) return response.items[0] ?? null
        return response.items.find((item) => item.delivery_id === prev.delivery_id) ?? response.items[0] ?? null
      })
    } catch (error) {
      const message = error instanceof ApiError ? error.message : error instanceof Error ? error.message : String(error)
      notify('error', `刷新收件箱失败: ${message}`)
    } finally {
      setLoading(false)
    }
  }, [notify, playerId])

  const refreshOwnedCards = useCallback(async () => {
    if (!playerId) return
    try {
      const response = await Api.newsOwnershipList(`user:${playerId}`)
      setOwnedCards(Array.isArray(response.cards) ? response.cards : [])
    } catch (error) {
      const message = error instanceof ApiError ? error.message : error instanceof Error ? error.message : String(error)
      notify('error', `获取持有卡牌失败: ${message}`)
    }
  }, [notify, playerId])

  const refreshStoreCatalog = useCallback(async (force = false) => {
    if (!playerId) return
    setLoading(true)
    try {
      const response = await Api.newsStoreCatalog(`user:${playerId}`, force)
      const items = Array.isArray(response.items) ? response.items : []
      setStoreItems(items)
      setStoreExpiresAt(response.expires_at || '')
      if (items.length > 0) {
        const next = items[0]
        const fixedSymbol = (next as NewsStoreCatalogItem & { symbol?: string }).symbol || next.symbol_options?.[0] || ''
        setPurchaseKind(next.kind)
        setPurchasePrice(next.price_cash)
        setPurchaseInitialText(next.preview_text || '')
        setPurchaseSymbol(fixedSymbol)
      }
      if (force) notify('success', '黑市货架已刷新')
    } catch (error) {
      const message = error instanceof ApiError ? error.message : error instanceof Error ? error.message : String(error)
      notify('error', `获取黑市货架失败: ${message}`)
    } finally {
      setLoading(false)
    }
  }, [notify, playerId])

  const fetchPropagateQuote = useCallback(async (variantId: string, cash: number, limit: number) => {
    if (!playerId || !variantId || cash <= 0 || limit <= 0) return
    try {
      const response = await Api.newsPropagateQuote({
        variant_id: variantId,
        from_actor_id: `user:${playerId}`,
        spend_cash: cash,
        limit,
      })
      setPropQuote(response)
    } catch {
      setPropQuote(null)
    }
  }, [playerId])

  useEffect(() => {
    void refreshInbox()
    void refreshOwnedCards()
    void refreshStoreCatalog()
  }, [refreshInbox, refreshOwnedCards, refreshStoreCatalog])

  useEffect(() => {
    if (!storeExpiresAt) return
    const updateTimer = () => {
      const diff = new Date(storeExpiresAt).getTime() - Date.now()
      if (diff <= 0) {
        setTimeLeft('已过期')
        return
      }
      const minutes = Math.floor(diff / 60000)
      const seconds = Math.floor((diff % 60000) / 1000)
      setTimeLeft(`${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`)
    }
    updateTimer()
    const timer = window.setInterval(updateTimer, 1000)
    return () => window.clearInterval(timer)
  }, [storeExpiresAt])

  useEffect(() => {
    if (!targetVariantId || Number(propSpendCash) <= 0 || propLimit <= 0) return
    const timer = window.setTimeout(() => {
      void fetchPropagateQuote(targetVariantId, Number(propSpendCash), propLimit)
    }, 300)
    return () => window.clearTimeout(timer)
  }, [fetchPropagateQuote, propLimit, propSpendCash, targetVariantId])

  useEffect(() => {
    ws.connect('events', (payload) => {
      const eventType = getEventType(payload)
      if (!eventType || !eventType.startsWith('news.')) return
      if (refreshTimerRef.current !== null) return
      refreshTimerRef.current = window.setTimeout(() => {
        refreshTimerRef.current = null
        void refreshInbox()
      }, 500)
    })
    return () => {
      ws.close()
      if (refreshTimerRef.current !== null) {
        window.clearTimeout(refreshTimerRef.current)
        refreshTimerRef.current = null
      }
    }
  }, [refreshInbox, roomId, ws])

  const kinds = useMemo(() => Array.from(new Set((inbox?.items || []).map((item) => item.kind.toUpperCase()))), [inbox])

  const filteredInbox = useMemo(() => {
    const items = [...(inbox?.items || [])]
    items.sort((a, b) => {
      const left = new Date(a.delivered_at).getTime()
      const right = new Date(b.delivered_at).getTime()
      return sortOrder === 'newest' ? right - left : left - right
    })
    if (filterKind === 'ALL') return items
    return items.filter((item) => item.kind.toUpperCase() === filterKind)
  }, [filterKind, inbox, sortOrder])

  const categorizedInbox = useMemo(() => {
    const active: NewsInboxResponseItem[] = []
    const expired: NewsInboxResponseItem[] = []
    filteredInbox.forEach((item) => {
      const ageHours = (Date.now() - new Date(item.delivered_at).getTime()) / 3600000
      const ttl = item.kind === 'WORLD_EVENT' ? 24 : 6
      if (ageHours >= ttl) expired.push(item)
      else active.push(item)
    })
    return { active, expired }
  }, [filteredInbox])

  const activeStoreItem = useMemo(() => {
    return storeItems.find((item) => item.kind === purchaseKind && item.preview_text === purchaseInitialText) || storeItems[0] || null
  }, [purchaseInitialText, purchaseKind, storeItems])

  const previewItem = useMemo<NewsInboxResponseItem | null>(() => {
    if (!activeStoreItem) return null
    return {
      delivery_id: 'preview',
      card_id: 'preview',
      variant_id: 'preview',
      kind: activeStoreItem.kind,
      from_actor_id: 'MARKET',
      visibility_level: 'NORMAL',
      delivery_reason: 'BLUEPRINT_PREVIEW',
      delivered_at: new Date().toISOString(),
      text: activeStoreItem.preview_text,
      symbols: purchaseSymbol ? [purchaseSymbol] : [],
      tags: activeStoreItem.tags || [],
      truth_payload: { image_uri: activeStoreItem.preview_image_uri || null },
      rarity: activeStoreItem.rarity || 'COMMON',
      faction: activeStoreItem.faction,
    }
  }, [activeStoreItem, purchaseSymbol])

  const handleAction = useCallback((action: 'propagate' | 'mutate' | 'contract' | 'suppress', item: NewsInboxResponseItem) => {
    setSelectedInboxItem(item)
    if (action === 'propagate') {
      setTargetVariantId(item.variant_id)
      notify('info', '已将当前变体载入传播面板')
      return
    }
    if (action === 'mutate') {
      setMutateVariantId(item.variant_id)
      setMutateText(item.text)
      setShowMutatePanel(true)
      return
    }
    if (action === 'contract') {
      setContractNewsItem(item)
      setShowContractPanel(true)
      return
    }
    const payload = item.truth_payload as Record<string, unknown> | null
    setSuppressChainId(String(payload?.chain_id || ''))
    setShowSuppressPanel(true)
  }, [notify])

  const handlePurchase = useCallback(async () => {
    if (!playerId || !purchaseKind) return
    setLoading(true)
    try {
      await Api.newsStorePurchase({
        buyer_user_id: `user:${playerId}`,
        kind: purchaseKind,
        price_cash: purchasePrice,
        initial_text: purchaseInitialText,
        symbols: purchaseSymbol ? [purchaseSymbol] : [],
      })
      notify('success', `已购入 ${purchaseKind}`)
      await refreshInbox()
      await refreshOwnedCards()
      await refreshStoreCatalog()
      setActiveTab('collection')
    } catch (error) {
      const message = error instanceof ApiError ? error.message : error instanceof Error ? error.message : String(error)
      notify('error', `购买失败: ${message}`)
    } finally {
      setLoading(false)
    }
  }, [notify, playerId, purchaseInitialText, purchaseKind, purchasePrice, purchaseSymbol, refreshInbox, refreshOwnedCards, refreshStoreCatalog])

  const propagateLast = useCallback(async () => {
    if (!playerId || !targetVariantId) {
      notify('error', '请先选择一个情报变体')
      return
    }
    const spendCash = propSpendCash.trim() === '' ? undefined : Number(propSpendCash)
    if (spendCash !== undefined && (!Number.isFinite(spendCash) || spendCash <= 0)) {
      notify('error', '投入现金必须为正数')
      return
    }
    try {
      const response = await Api.newsPropagate({
        variant_id: targetVariantId,
        from_actor_id: `user:${playerId}`,
        visibility_level: 'NORMAL',
        spend_influence: 0,
        spend_cash: spendCash,
        limit: propLimit,
      })
      notify('success', `传播成功，送达 ${response.delivered} 人`)
      await refreshInbox()
    } catch (error) {
      const message = error instanceof ApiError ? error.message : error instanceof Error ? error.message : String(error)
      notify('error', message)
    }
  }, [notify, playerId, propLimit, propSpendCash, refreshInbox, targetVariantId])

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '24px', height: '100%', color: '#e0e0e0' }}>
      <header style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
          <div style={{ background: 'var(--terminal-info)', padding: '10px', borderRadius: '4px' }}>
            <Newspaper size={24} color="#000" />
          </div>
          <div>
            <h1 style={{ margin: 0, fontSize: '28px', fontWeight: 900, letterSpacing: '4px', textTransform: 'uppercase' }}>
              Intelligence <span style={{ color: 'var(--terminal-info)' }}>Network</span>
            </h1>
            <div style={{ fontSize: '10px', color: '#666', letterSpacing: '2px', marginTop: '4px' }}>
              ROOM_{roomId?.toUpperCase()} // SIGNAL_MATRIX
            </div>
          </div>
        </div>

        <div style={{ display: 'flex', gap: '12px' }}>
          <button onClick={() => { window.location.hash = '#/' }} style={navButtonStyle('#999', 'rgba(255,255,255,0.05)')}>
            <LayoutDashboard size={14} /> DASHBOARD
          </button>
          <button onClick={() => { window.location.hash = '#/' }} style={navButtonStyle('#ff4d4f', 'rgba(255,77,79,0.1)')}>
            <LogOut size={14} /> EXIT
          </button>
        </div>
      </header>

      <div style={{ display: 'flex', gap: '4px', borderBottom: '1px solid #333', paddingBottom: '2px' }}>
        <TabBtn active={activeTab === 'collection'} onClick={() => setActiveTab('collection')} icon={Newspaper} label="情报仓库" />
        <TabBtn active={activeTab === 'store'} onClick={() => setActiveTab('store')} icon={ShoppingCart} label="黑市情报" />
      </div>

      {activeTab === 'collection' && (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 450px', gap: '24px', minHeight: 0, flex: 1 }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '24px', minWidth: 0, overflowY: 'auto', paddingRight: '8px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', gap: '16px', alignItems: 'center', flexWrap: 'wrap', background: 'rgba(20,20,20,0.5)', border: '1px solid rgba(255,255,255,0.06)', borderRadius: '4px', padding: '12px 16px' }}>
              <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
                <FilterChip active={filterKind === 'ALL'} onClick={() => setFilterKind('ALL')} label="全部" />
                {kinds.map((kind) => (
                  <FilterChip key={kind} active={filterKind === kind} onClick={() => setFilterKind(kind)} label={kind} />
                ))}
              </div>
              <button onClick={() => setSortOrder((prev) => prev === 'newest' ? 'oldest' : 'newest')} style={ghostButtonStyle}>
                {sortOrder === 'newest' ? '按最新排序' : '按最早排序'}
              </button>
            </div>

            <section>
              <h3 style={sectionTitleStyle}>ACTIVE_INTELLIGENCE ({categorizedInbox.active.length})</h3>
              <div style={cardGridStyle}>
                {categorizedInbox.active.map((item) => (
                  <IntelligenceCard
                    key={item.delivery_id}
                    item={item}
                    stage={ownedCards.includes(item.card_id) ? 'HELD' : 'CIRCULATING'}
                    isSelected={selectedInboxItem?.delivery_id === item.delivery_id}
                    onClick={() => setSelectedInboxItem(item)}
                    onAction={handleAction}
                  />
                ))}
              </div>
            </section>

            {categorizedInbox.expired.length > 0 && (
              <section>
                <h3 style={sectionTitleStyle}>ARCHIVED_HISTORY ({categorizedInbox.expired.length})</h3>
                <div style={{ ...cardGridStyle, opacity: 0.65 }}>
                  {categorizedInbox.expired.map((item) => (
                    <IntelligenceCard
                      key={item.delivery_id}
                      item={item}
                      stage="EXPIRED"
                      isSelected={selectedInboxItem?.delivery_id === item.delivery_id}
                      onClick={() => setSelectedInboxItem(item)}
                      onAction={handleAction}
                    />
                  ))}
                </div>
              </section>
            )}

            {filteredInbox.length === 0 && (
              <div style={{ padding: '48px 24px', textAlign: 'center', color: '#555', border: '1px dashed #333', borderRadius: '4px' }}>
                暂无匹配情报
              </div>
            )}
          </div>

          <div style={{ width: '450px', flexShrink: 0, display: 'flex', flexDirection: 'column', gap: '24px' }}>
            <div style={sidePanelStyle}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <strong style={{ color: 'var(--terminal-info)' }}>Intelligence Analysis</strong>
                {selectedInboxItem && <button onClick={() => setSelectedInboxItem(null)} style={iconCloseButtonStyle}>✕</button>}
              </div>

              {selectedInboxItem ? (
                <>
                  <div style={{ background: 'rgba(0,0,0,0.55)', padding: '16px', borderLeft: '2px solid var(--terminal-info)', lineHeight: 1.7 }}>
                    {selectedInboxItem.text}
                  </div>
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                    <MetaBox label="变体" value={selectedInboxItem.variant_id.slice(0, 12)} />
                    <MetaBox label="来源" value={selectedInboxItem.from_actor_id} />
                    <MetaBox label="标的" value={selectedInboxItem.symbols?.join(', ') || 'GLOBAL'} />
                    <MetaBox label="投递" value={selectedInboxItem.delivery_reason} />
                  </div>
                  {selectedInboxItem.truth_payload && (
                    <pre style={{ margin: 0, background: 'rgba(0,0,0,0.45)', padding: '12px', color: '#7dd3fc', fontSize: '12px', lineHeight: 1.5, whiteSpace: 'pre-wrap' }}>
                      {JSON.stringify(selectedInboxItem.truth_payload, null, 2)}
                    </pre>
                  )}
                </>
              ) : (
                <div style={{ color: '#444', textAlign: 'center', padding: '40px 20px' }}>选择一张卡牌查看右侧分析面板</div>
              )}
            </div>

            <div style={sidePanelStyle}>
              <strong style={{ color: 'var(--terminal-success)' }}>Amplifier System</strong>
              <input value={targetVariantId} onChange={(e) => setTargetVariantId(e.target.value)} placeholder="目标变体 ID" style={inputStyle} />
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                <input type="number" value={propLimit} onChange={(e) => setPropLimit(Number(e.target.value))} placeholder="传播人数" style={inputStyle} />
                <input value={propSpendCash} onChange={(e) => setPropSpendCash(e.target.value)} placeholder="投入现金" style={inputStyle} />
              </div>
              {propQuote && <div style={{ color: '#888', fontSize: '12px' }}>预计成本 ${propQuote.estimated_total_cost.toFixed(2)}，最多送达 {propQuote.affordable_limit} 节点</div>}
              <button onClick={() => { void propagateLast() }} className="cyber-button" style={{ background: 'var(--terminal-success)', color: '#000', fontWeight: 900, padding: '14px' }}>
                Initiate Broadcast
              </button>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '12px' }}>
                <button onClick={() => selectedInboxItem ? handleAction('mutate', selectedInboxItem) : notify('error', '请先选择一张情报卡牌')} style={actionButtonStyle('rgba(250,173,20,0.06)', '#faad14')}>
                  篡改
                </button>
                <button onClick={() => selectedInboxItem ? handleAction('contract', selectedInboxItem) : notify('error', '请先选择一张情报卡牌')} style={actionButtonStyle('rgba(24,144,255,0.06)', '#1890ff')}>
                  签约
                </button>
                <button onClick={() => selectedInboxItem ? handleAction('suppress', selectedInboxItem) : notify('error', '请先选择一张情报卡牌')} style={actionButtonStyle('rgba(255,77,79,0.06)', '#ff4d4f')}>
                  抑制
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {activeTab === 'store' && (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 450px', gap: '24px', minHeight: 0, flex: 1 }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '20px', overflowY: 'auto', paddingRight: '8px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', gap: '16px' }}>
              <div>
                <h2 style={{ margin: 0, color: '#faad14', letterSpacing: '2px' }}>地下情报黑市</h2>
                <p style={{ margin: '8px 0 0 0', color: '#666', fontSize: '13px' }}>货架出售固定情报，所见即所得，不再提供模板二次定制。</p>
              </div>
              <div style={{ textAlign: 'right' }}>
                <div style={{ color: '#444', fontSize: '10px' }}>货架刷新倒计时</div>
                <div style={{ color: '#faad14', fontFamily: 'monospace', fontWeight: 900 }}>{timeLeft || '--:--'}</div>
              </div>
            </div>

            <div style={storeGridStyle}>
              {storeItems.map((item, index) => {
                const symbol = (item as NewsStoreCatalogItem & { symbol?: string }).symbol || item.symbol_options?.[0] || ''
                const selected = purchaseKind === item.kind && purchaseInitialText === item.preview_text
                return (
                  <div
                    key={`${item.kind}-${index}`}
                    className={`market-blueprint-card ${selected ? 'selected' : ''}`}
                    onClick={() => {
                      setPurchaseKind(item.kind)
                      setPurchasePrice(item.price_cash)
                      setPurchaseInitialText(item.preview_text || '')
                      setPurchaseSymbol(symbol)
                    }}
                    style={{
                      background: selected ? 'rgba(250,173,20,0.08)' : 'rgba(20,20,20,0.6)',
                      border: `1px solid ${selected ? '#faad14' : 'rgba(255,255,255,0.06)'}`,
                      borderRadius: '4px',
                      padding: '22px',
                      display: 'flex',
                      flexDirection: 'column',
                      gap: '12px',
                      cursor: 'pointer',
                      transition: 'all 0.3s ease',
                      minHeight: '220px',
                    }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'start' }}>
                      <div>
                        <div style={{ color: getRarityColor(item.rarity), fontSize: '10px', fontWeight: 900, letterSpacing: '2px' }}>{item.rarity || 'COMMON'}</div>
                        <div style={{ color: '#fff', fontSize: '18px', fontWeight: 900 }}>{item.kind}</div>
                      </div>
                      <div style={{ color: '#faad14', fontFamily: 'monospace', fontWeight: 900 }}>${item.price_cash.toLocaleString()}</div>
                    </div>
                    <div style={{ color: '#bbb', fontSize: '13px', lineHeight: 1.7 }}>{item.description || item.preview_text}</div>
                    <div style={{ marginTop: 'auto', display: 'flex', justifyContent: 'space-between', alignItems: 'center', paddingTop: '12px', borderTop: '1px solid rgba(255,255,255,0.05)' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '6px', color: '#666', fontSize: '10px' }}>
                        <Clock size={12} /> {item.default_ttl_hours || 6}H TTL
                      </div>
                      <div style={{ color: '#faad14', fontFamily: 'monospace', fontSize: '11px', fontWeight: 900 }}>{symbol ? `$${symbol}` : 'GLOBAL'}</div>
                    </div>
                  </div>
                )
              })}
            </div>
          </div>

          <div style={{ ...sidePanelStyle, width: '450px', flexShrink: 0 }}>
            <strong style={{ color: '#faad14' }}>Purchase Confirmation</strong>
            {previewItem ? (
              <>
                <div style={{ display: 'flex', justifyContent: 'center', padding: '4px 0 12px 0' }}>
                  <IntelligenceCard item={previewItem} stage="PREVIEW" showActions={false} />
                </div>
                <div style={{ background: 'rgba(0,0,0,0.55)', padding: '16px', borderLeft: '2px solid #faad14', lineHeight: 1.7 }}>
                  <div style={{ color: '#fff', fontWeight: 900, marginBottom: '8px' }}>{activeStoreItem?.kind}</div>
                  <div style={{ color: '#aaa' }}>{purchaseInitialText}</div>
                  {purchaseSymbol && <div style={{ marginTop: '10px', color: '#faad14', fontFamily: 'monospace' }}>BOUND_SYMBOL: ${purchaseSymbol}</div>}
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                  <MetaBox label="阵营" value={activeStoreItem?.faction || 'NEUTRAL'} />
                  <MetaBox label="时效" value={`${activeStoreItem?.default_ttl_hours || 6}H`} />
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span style={{ color: '#666' }}>交易价格</span>
                  <span style={{ color: '#faad14', fontSize: '28px', fontWeight: 900, fontFamily: 'monospace' }}>${purchasePrice.toLocaleString()}</span>
                </div>
                <button onClick={() => { void handlePurchase() }} disabled={loading} className="cyber-button" style={{ background: '#faad14', color: '#000', fontWeight: 900, padding: '16px' }}>
                  {loading ? 'TRANSACTION_IN_PROGRESS...' : 'AUTHORIZE_TRANSACTION'}
                </button>
              </>
            ) : (
              <div style={{ color: '#444', textAlign: 'center', padding: '56px 20px' }}>请选择一张黑市情报卡</div>
            )}
          </div>
        </div>
      )}

      {showMutatePanel && (
        <Overlay title="篡改情报变体" onClose={() => setShowMutatePanel(false)} color="#faad14">
          <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            <textarea value={mutateText} onChange={(e) => setMutateText(e.target.value)} rows={7} style={{ ...inputStyle, resize: 'vertical', minHeight: '160px' }} />
            <input value={mutateSpendCash} onChange={(e) => setMutateSpendCash(e.target.value)} placeholder="投入修改预算" style={inputStyle} />
            <button
              onClick={async () => {
                try {
                  const response = await Api.newsMutateVariant({
                    parent_variant_id: mutateVariantId,
                    editor_id: `user:${playerId}`,
                    new_text: mutateText,
                    spend_cash: mutateSpendCash ? Number(mutateSpendCash) : undefined,
                  })
                  notify('success', '篡改序列执行成功')
                  setTargetVariantId(response.new_variant_id)
                  setShowMutatePanel(false)
                  await refreshInbox()
                } catch {
                  notify('error', '篡改序列执行失败')
                }
              }}
              className="cyber-button"
              style={{ background: '#faad14', color: '#000', fontWeight: 900, padding: '14px' }}
            >
              注入修改变体
            </button>
          </div>
        </Overlay>
      )}

      {showSuppressPanel && (
        <Overlay title="抑制抹除序列" onClose={() => setShowSuppressPanel(false)} color="#ff4d4f">
          <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            <MetaBox label="情报链 ID" value={suppressChainId || '未检测到'} />
            <input type="number" value={suppressInfluence} onChange={(e) => setSuppressInfluence(Number(e.target.value))} style={inputStyle} />
            <button
              disabled={suppressing}
              onClick={async () => {
                if (!suppressChainId) {
                  notify('error', '未检测到情报链ID')
                  return
                }
                setSuppressing(true)
                try {
                  await Api.newsSuppress({
                    actor_id: `user:${playerId}`,
                    chain_id: suppressChainId,
                    spend_influence: suppressInfluence,
                  })
                  notify('success', '抹除序列已上线')
                  setShowSuppressPanel(false)
                } catch {
                  notify('error', '抹除序列初始化失败')
                } finally {
                  setSuppressing(false)
                }
              }}
              className="cyber-button"
              style={{ background: '#ff4d4f', color: '#fff', fontWeight: 900, padding: '14px' }}
            >
              {suppressing ? 'EXECUTING...' : '执行抹除'}
            </button>
          </div>
        </Overlay>
      )}

      {showContractPanel && contractNewsItem && (
        <Overlay title="引用签约协议" onClose={() => setShowContractPanel(false)} color="var(--terminal-info)">
          <ContractFormFromNews newsItem={contractNewsItem} onError={(message) => { if (message) notify('error', message) }} />
        </Overlay>
      )}

      <style>{`
        .market-blueprint-card:hover {
          border-color: #faad1488 !important;
          transform: translateY(-4px);
        }
        .market-blueprint-card.selected {
          box-shadow: 0 0 30px rgba(250, 173, 20, 0.16);
        }
      `}</style>
    </div>
  )
}

const storeGridStyle = {
  display: 'grid',
  gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))',
  gap: '20px',
} as const

const cardGridStyle = {
  display: 'grid',
  gridTemplateColumns: 'repeat(auto-fill, minmax(240px, 1fr))',
  gap: '20px',
} as const

const sidePanelStyle = {
  background: 'rgba(26,26,26,0.55)',
  border: '1px solid rgba(255,255,255,0.06)',
  borderRadius: '4px',
  padding: '24px',
  display: 'flex',
  flexDirection: 'column' as const,
  gap: '16px',
  backdropFilter: 'blur(10px)',
} as const

const sectionTitleStyle = {
  fontSize: '12px',
  color: '#555',
  marginBottom: '16px',
  letterSpacing: '2px',
} as const

const inputStyle = {
  background: 'rgba(0,0,0,0.45)',
  border: '1px solid #222',
  color: '#fff',
  padding: '12px',
  borderRadius: '2px',
  fontSize: '12px',
  fontFamily: 'monospace',
} as const

const ghostButtonStyle = {
  background: 'transparent',
  border: '1px solid #333',
  color: '#888',
  padding: '8px 12px',
  borderRadius: '2px',
  cursor: 'pointer',
} as const

const iconCloseButtonStyle = {
  background: 'none',
  border: 'none',
  color: '#555',
  cursor: 'pointer',
  fontSize: '18px',
} as const

function navButtonStyle(color: string, background: string) {
  return {
    background,
    border: `1px solid ${color}33`,
    color,
    padding: '8px 20px',
    borderRadius: '2px',
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
    fontSize: '12px',
    fontWeight: 'bold',
    letterSpacing: '1px',
    cursor: 'pointer',
  } as const
}

function actionButtonStyle(background: string, color: string) {
  return {
    background,
    border: `1px solid ${color}33`,
    color,
    padding: '12px',
    borderRadius: '2px',
    cursor: 'pointer',
    fontSize: '12px',
    fontWeight: 'bold',
  } as const
}

function TabBtn({ active, onClick, icon: Icon, label }: { active: boolean; onClick: () => void; icon: typeof Newspaper; label: string }) {
  return (
    <button onClick={onClick} style={{ background: active ? 'rgba(24,144,255,0.1)' : 'transparent', border: `1px solid ${active ? 'var(--terminal-info)' : 'rgba(255,255,255,0.05)'}`, padding: '12px 24px', borderRadius: '2px', color: active ? '#fff' : '#666', display: 'flex', alignItems: 'center', gap: '10px', cursor: 'pointer', fontWeight: 'bold' }}>
      <Icon size={16} color={active ? 'var(--terminal-info)' : '#666'} />
      {label}
    </button>
  )
}

function FilterChip({ active, onClick, label }: { active: boolean; onClick: () => void; label: string }) {
  return (
    <button onClick={onClick} style={{ background: active ? 'rgba(24,144,255,0.15)' : 'rgba(255,255,255,0.02)', border: `1px solid ${active ? 'var(--terminal-info)' : 'rgba(255,255,255,0.05)'}`, color: active ? '#fff' : '#444', padding: '4px 12px', borderRadius: '2px', cursor: 'pointer', fontSize: '10px', fontWeight: 900 }}>
      {label}
    </button>
  )
}

function MetaBox({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', background: 'rgba(255,255,255,0.02)', padding: '10px', borderRadius: '2px', border: '1px solid rgba(255,255,255,0.05)' }}>
      <span style={{ fontSize: '9px', color: '#444', textTransform: 'uppercase', fontWeight: 'bold' }}>{label}</span>
      <span style={{ fontSize: '12px', color: '#aaa', overflow: 'hidden', textOverflow: 'ellipsis', fontFamily: 'monospace' }}>{value}</span>
    </div>
  )
}

function Overlay({ title, children, onClose, color }: { title: string; children: ReactNode; onClose: () => void; color: string }) {
  return (
    <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.85)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000, backdropFilter: 'blur(4px)' }}>
      <div style={{ width: '500px', background: '#141414', border: `1px solid ${color}44`, borderRadius: '16px', padding: '24px', boxShadow: `0 20px 40px rgba(0,0,0,0.5), 0 0 20px ${color}11` }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
          <h3 style={{ margin: 0, color }}>{title}</h3>
          <button onClick={onClose} style={iconCloseButtonStyle}>✕</button>
        </div>
        {children}
      </div>
    </div>
  )
}
