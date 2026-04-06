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
import NewsCard from '../components/NewsCard'

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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [purchasePresetId])

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
      // 尝试从 truth_payload 中提取 chain_id
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

  const filteredInbox = useMemo(() => {
    if (!inbox?.items) return []
    return inbox.items.filter(it => {
      if (filterKind === 'ALL') return true
      return it.kind.toUpperCase() === filterKind
    })
  }, [inbox, filterKind])

  const kinds = useMemo(() => {
    const k = new Set<string>()
    inbox?.items?.forEach(it => k.add(it.kind.toUpperCase()))
    return Array.from(k)
  }, [inbox])

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20, height: '100%' }}>
      {/* 顶部导航 Tabs */}
      <div style={{ display: 'flex', gap: 10, borderBottom: '1px solid var(--terminal-border)', paddingBottom: '10px' }}>
        <button 
          onClick={() => setActiveTab('collection')}
          className={`cyber-button ${activeTab === 'collection' ? 'active' : ''}`}
          style={{ padding: '8px 20px' }}
        >
          📁 情报仓库 (Collection)
        </button>
        <button 
          onClick={() => setActiveTab('store')}
          className={`cyber-button ${activeTab === 'store' ? 'active' : ''}`}
          style={{ padding: '8px 20px' }}
        >
          🛒 黑市情报 (Black Market)
        </button>
      </div>

      {activeTab === 'collection' && (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 350px', gap: 20, alignItems: 'start' }}>
          {/* 左侧：卡牌列表 */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 15 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                <button 
                  onClick={() => setFilterKind('ALL')}
                  className={`cyber-button mini ${filterKind === 'ALL' ? 'active' : ''}`}
                >全部</button>
                {kinds.map(k => (
                  <button 
                    key={k}
                    onClick={() => setFilterKind(k)}
                    className={`cyber-button mini ${filterKind === k ? 'active' : ''}`}
                  >{k}</button>
                ))}
              </div>
              <button onClick={refreshInbox} disabled={loading} className="cyber-button mini">
                {loading ? '同步中...' : '🔄 同步情报'}
              </button>
            </div>

            <div style={{ 
              display: 'grid', 
              gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', 
              gap: 15,
              maxHeight: 'calc(100vh - 250px)',
              overflowY: 'auto',
              padding: '5px'
            }}>
              {filteredInbox.length > 0 ? (
                filteredInbox.map(it => (
                  <NewsCard 
                    key={it.delivery_id} 
                    item={it} 
                    isSelected={selectedInboxItem?.delivery_id === it.delivery_id}
                    onClick={() => setSelectedInboxItem(it)}
                    onAction={handleAction}
                  />
                ))
              ) : (
                <div style={{ gridColumn: '1/-1', padding: '40px', textAlign: 'center', color: '#666', border: '1px dashed var(--terminal-border)', borderRadius: '8px' }}>
                  暂无匹配情报
                </div>
              )}
            </div>
          </div>

          {/* 右侧：行动中心 & 详情 */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 20, position: 'sticky', top: '0' }}>
            {selectedInboxItem ? (
              <div className="card" style={{ border: '1px solid var(--terminal-info)', background: 'rgba(0, 140, 255, 0.05)', display: 'grid', gap: '12px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                  <h4 style={{ margin: 0, color: 'var(--terminal-info)' }}>情报详情</h4>
                  <button onClick={() => setSelectedInboxItem(null)} style={{ background: 'none', border: 'none', color: '#666', cursor: 'pointer', padding: 0 }}>✕</button>
                </div>
                
                <div style={{ fontSize: '14px', lineHeight: '1.5', color: '#fff' }}>
                  {selectedInboxItem.text}
                </div>

                {/* 元数据特征 */}
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px', fontSize: '11px', background: 'rgba(0,0,0,0.2)', padding: '8px', borderRadius: '4px' }}>
                  <div>
                    <div style={{ color: '#888', marginBottom: '2px' }}>情报分类</div>
                    <div style={{ color: 'var(--terminal-info)', fontWeight: 'bold' }}>{selectedInboxItem.kind}</div>
                  </div>
                  <div>
                    <div style={{ color: '#888', marginBottom: '2px' }}>投递原因</div>
                    <div>{selectedInboxItem.delivery_reason}</div>
                  </div>
                  <div style={{ gridColumn: '1 / -1', borderTop: '1px solid #333', paddingTop: '4px', marginTop: '4px' }}>
                    <div style={{ color: '#888', marginBottom: '2px' }}>影响标的</div>
                    <div style={{ display: 'flex', gap: '4px' }}>
                      {(selectedInboxItem.symbols || []).length > 0 ? selectedInboxItem.symbols?.map(s => (
                        <span key={s} style={{ color: 'var(--terminal-warn)' }}>${s}</span>
                      )) : <span style={{ color: '#555' }}>无明确标的</span>}
                    </div>
                  </div>
                </div>

                {/* 真实载荷 (Truth Payload) 分析 */}
                {selectedInboxItem.truth_payload && (
                  <div style={{ background: 'rgba(255, 255, 255, 0.05)', padding: '8px', borderRadius: '4px', border: '1px dashed #444' }}>
                    <div style={{ fontSize: '10px', color: '#888', marginBottom: '4px', textTransform: 'uppercase' }}>内核载荷分析 (Core Analysis)</div>
                    <div style={{ fontSize: '11px', maxHeight: '100px', overflowY: 'auto' }}>
                      {selectedInboxItem.truth_payload && typeof selectedInboxItem.truth_payload === 'object' ? (
                        <pre style={{ margin: 0, whiteSpace: 'pre-wrap', color: '#aaa' }}>
                          {JSON.stringify(selectedInboxItem.truth_payload, null, 2)}
                        </pre>
                      ) : (
                        <span style={{ color: '#aaa' }}>{String(selectedInboxItem.truth_payload)}</span>
                      )}
                    </div>
                  </div>
                )}

                <div style={{ fontSize: '10px', color: '#555', display: 'flex', flexDirection: 'column', gap: '2px' }}>
                  <div>卡片ID: {selectedInboxItem.card_id}</div>
                  <div>变体ID: {selectedInboxItem.variant_id}</div>
                  <div>来源: {selectedInboxItem.from_actor_id}</div>
                </div>
              </div>
            ) : (
              <div className="card" style={{ textAlign: 'center', color: '#888', padding: '30px' }}>
                选择一张情报卡牌以查看详情及采取行动
              </div>
            )}

            {/* 传播面板 */}
            <div className="card">
              <h4 style={{ margin: '0 0 10px' }}>📢 传播决策 (Propagate)</h4>
              <div style={{ display: 'grid', gap: 10 }}>
                <label>
                  <div style={{ fontSize: '11px', color: '#888' }}>目标变体 ID</div>
                  <input 
                    value={targetVariantId} 
                    onChange={e => setTargetVariantId(e.target.value)} 
                    placeholder="选择卡牌自动填充"
                    style={{ width: '100%', padding: '6px', fontSize: '12px' }}
                  />
                </label>
                <div style={{ display: 'flex', gap: 8 }}>
                  <label style={{ flex: 1 }}>
                    <div style={{ fontSize: '11px', color: '#888' }}>送达人数</div>
                    <input type="number" value={propLimit} onChange={(e) => setPropLimit(Number(e.target.value))} style={{ width: '100%', padding: '6px' }} />
                  </label>
                  <label style={{ flex: 1 }}>
                    <div style={{ fontSize: '11px', color: '#888' }}>投入资金</div>
                    <input value={propSpendCash} onChange={(e) => setPropSpendCash(e.target.value)} placeholder="0" style={{ width: '100%', padding: '6px' }} />
                  </label>
                </div>
                <button onClick={propagateLast} className="cyber-button" style={{ width: '100%', background: '#52c41a' }}>执行传播</button>
                {propQuote && (
                  <div style={{ marginTop: '8px', fontSize: '10px', background: 'rgba(0,0,0,0.2)', padding: '8px', borderRadius: '4px', border: '1px solid var(--terminal-border)' }}>
                    <div style={{ color: 'var(--terminal-success)', fontWeight: 'bold' }}>传播估算:</div>
                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '4px', marginTop: '4px' }}>
                      <span>可达人数: {propQuote.affordable_limit}</span>
                      <span>单人成本: {propQuote.per_delivery_cost.toFixed(2)}</span>
                      <span style={{ gridColumn: '1/-1' }}>总预估费用: {propQuote.estimated_total_cost.toFixed(2)}</span>
                    </div>
                  </div>
                )}
              </div>
            </div>

            {/* 快速入口 */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
              <button 
                onClick={() => {
                  if (selectedInboxItem) handleAction('mutate', selectedInboxItem)
                  else notify('error', '请先选择一张情报卡牌')
                }}
                className="cyber-button mini"
              >🖋️ 篡改</button>
              <button 
                onClick={() => {
                  if (selectedInboxItem) handleAction('contract', selectedInboxItem)
                  else notify('error', '请先选择一张情报卡牌')
                }}
                className="cyber-button mini"
              >🤝 签约</button>
            </div>
          </div>
        </div>
      )}

      {activeTab === 'store' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <h3 style={{ margin: 0, color: '#faad14' }}>地下情报黑市 (Black Market)</h3>
            <div style={{ fontSize: '12px', color: '#666' }}>在这里买断独家情报，你可以选择不同的情报原型进行传播或篡改。</div>
          </div>

          <div style={{ 
            display: 'grid', 
            gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', 
            gap: 20 
          }}>
            {storeItems.map((it) => (
              <div 
                key={it.kind} 
                className="card" 
                style={{ 
                  background: '#141414', 
                  border: purchaseKind === it.kind ? '2px solid #faad14' : '1px solid #333',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '12px',
                  transition: 'all 0.2s ease',
                  cursor: 'pointer',
                  position: 'relative',
                  overflow: 'hidden'
                }}
                onClick={() => {
                  setPurchaseKind(it.kind)
                  setPurchasePrice(it.price_cash)
                  if (it.presets?.[0]) {
                    setPurchasePresetId(it.presets[0].preset_id)
                  } else {
                    setPurchasePresetId('')
                  }
                }}
              >
                {/* 装饰性背景 */}
                <div style={{ 
                  position: 'absolute', top: '-10px', right: '-10px', 
                  fontSize: '40px', opacity: 0.05, transform: 'rotate(15deg)',
                  pointerEvents: 'none'
                }}>
                  {it.kind === 'RUMOR' ? '🕵️' : it.kind === 'MAJOR_EVENT' ? '🔥' : '📄'}
                </div>

                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span style={{ color: '#faad14', fontWeight: 'bold', fontSize: '14px' }}>{it.kind}</span>
                  <span style={{ color: 'var(--terminal-warn)', fontWeight: 'bold' }}>${it.price_cash.toLocaleString()}</span>
                </div>

                <div style={{ fontSize: '12px', color: '#888', minHeight: '36px' }}>
                  {it.preview_text || '包含多套情报原型，可针对特定行业或标的进行深度定制。'}
                </div>

                {purchaseKind === it.kind && (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', borderTop: '1px solid #333', paddingTop: '10px', marginTop: 'auto' }}>
                    <label>
                      <div style={{ fontSize: '10px', color: '#666', marginBottom: '4px' }}>选择情报原型 (Preset)</div>
                      <select
                        value={purchasePresetId}
                        onClick={e => e.stopPropagation()}
                        onChange={(e) => {
                          setPurchasePresetId(e.target.value)
                        }}
                        style={{ width: '100%', padding: '6px', background: '#222', color: '#fff', border: '1px solid #444', fontSize: '12px' }}
                      >
                        {it.presets?.map(p => (
                          <option key={p.preset_id} value={p.preset_id}>{p.preset_id}</option>
                        ))}
                      </select>
                    </label>
                    
                    {it.symbol_options && it.symbol_options.length > 0 && (
                      <label>
                        <div style={{ fontSize: '10px', color: '#666', marginBottom: '4px' }}>注入影响标的 (Target)</div>
                        <select
                          value={purchaseSymbol}
                          onClick={e => e.stopPropagation()}
                          onChange={(e) => setPurchaseSymbol(e.target.value)}
                          style={{ width: '100%', padding: '6px', background: '#222', color: '#fff', border: '1px solid #444', fontSize: '12px' }}
                        >
                          {it.symbol_options.map(s => (
                            <option key={s} value={s}>{s}</option>
                          ))}
                        </select>
                      </label>
                    )}

                    <button 
                      onClick={(e) => { e.stopPropagation(); purchase(); }}
                      className="cyber-button" 
                      style={{ background: '#faad14', color: '#000', marginTop: '5px' }}
                    >
                      立即买断情报
                    </button>
                  </div>
                )}
              </div>
            ))}
          </div>

          <div className="card" style={{ marginTop: '20px' }}>
            <h3 style={{ marginTop: 0, fontSize: '14px' }}>已归档的变体凭证 (Owned Variant IDs)</h3>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(180px, 1fr))', gap: 12 }}>
              {ownedCards.length > 0 ? ownedCards.map(id => (
                <div key={id} style={{ padding: '8px', background: 'var(--terminal-bg)', border: '1px solid var(--terminal-border)', borderRadius: '4px', fontSize: '10px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <code style={{ color: 'var(--terminal-info)' }}>{id.slice(0, 16)}...</code>
                  <button className="cyber-button mini" onClick={() => { setTargetVariantId(id); setActiveTab('collection'); notify('success', '凭证已载入行动中心'); }}>载入</button>
                </div>
              )) : <div style={{ color: '#666', fontSize: '12px' }}>暂无买断记录</div>}
            </div>
          </div>
        </div>
      )}

      {/* 弹窗面板：篡改 */}
      {showMutatePanel && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.8)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000 }}>
          <div className="card" style={{ width: '500px', border: '2px solid #faad14' }}>
            <h3 style={{ marginTop: 0, color: '#faad14' }}>🖋️ 篡改变体 (Mutate)</h3>
            <div style={{ display: 'grid', gap: 15 }}>
              <textarea 
                value={mutateText} 
                onChange={e => setMutateText(e.target.value)}
                rows={5}
                style={{ width: '100%', padding: '10px', background: '#111', color: '#fff', border: '1px solid #444' }}
              />
              <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
                <span style={{ fontSize: '12px', color: '#888' }}>投入资金:</span>
                <input value={mutateSpendCash} onChange={e => setMutateSpendCash(e.target.value)} placeholder="0" style={{ flex: 1, padding: '6px' }} />
              </div>
              <div style={{ display: 'flex', gap: 10 }}>
                <button onClick={() => setShowMutatePanel(false)} className="cyber-button" style={{ flex: 1, background: '#444' }}>取消</button>
                <button 
                  onClick={async () => {
                    try {
                      const r = await Api.newsMutateVariant({
                        parent_variant_id: mutateVariantId,
                        editor_id: `user:${playerId}`,
                        new_text: mutateText,
                        spend_cash: mutateSpendCash ? Number(mutateSpendCash) : undefined,
                      })
                      notify('success', `篡改成功`)
                      setTargetVariantId(r.new_variant_id)
                      setShowMutatePanel(false)
                      refreshInbox()
                    } catch (e) {
                      notify('error', '篡改失败')
                    }
                  }}
                  className="cyber-button" 
                  style={{ flex: 1, background: '#faad14', color: '#000' }}
                >确认提交</button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* 弹窗面板：抑制 */}
      {showSuppressPanel && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.8)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000 }}>
          <div className="card" style={{ width: '400px', border: '2px solid #ff4d4f' }}>
            <h3 style={{ marginTop: 0, color: '#ff4d4f' }}>🚫 抑制抹除 (Suppress)</h3>
            <div style={{ display: 'grid', gap: 15 }}>
              <div style={{ fontSize: '13px', color: '#aaa' }}>
                消耗影响力或资金来抑制该情报链的传播。
              </div>
              <label>
                <div style={{ fontSize: '12px', color: '#888', marginBottom: '4px' }}>情报链 (Chain ID)</div>
                <input value={suppressChainId} onChange={e => setSuppressChainId(e.target.value)} style={{ width: '100%', padding: '8px', background: '#111', color: '#fff' }} />
              </label>
              <label>
                <div style={{ fontSize: '12px', color: '#888', marginBottom: '4px' }}>投入影响力</div>
                <input type="number" value={suppressInfluence} onChange={e => setSuppressInfluence(Number(e.target.value))} style={{ width: '100%', padding: '8px' }} />
              </label>
              <div style={{ display: 'flex', gap: 10 }}>
                <button onClick={() => setShowSuppressPanel(false)} className="cyber-button" style={{ flex: 1, background: '#444' }}>放弃</button>
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
                      notify('success', '指令已下达，情报抑制中')
                      setShowSuppressPanel(false)
                    } catch (e) {
                      notify('error', '指令执行失败')
                    } finally {
                      setSuppressing(false)
                    }
                  }}
                  className="cyber-button" 
                  style={{ flex: 1, background: '#ff4d4f' }}
                >
                  {suppressing ? '执行中...' : '下达抑制指令'}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* 弹窗面板：签约 */}
      {showContractPanel && contractNewsItem && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.8)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000 }}>
          <div className="card" style={{ width: '500px', border: '2px solid var(--terminal-info)' }}>
            <h3 style={{ marginTop: 0, color: 'var(--terminal-info)' }}>🤝 引用签约</h3>
            <ContractFormFromNews 
              newsItem={contractNewsItem}
              onError={(msg) => msg ? notify('error', msg) : setShowContractPanel(false)}
            />
            <button onClick={() => setShowContractPanel(false)} className="cyber-button" style={{ width: '100%', marginTop: '10px', background: '#444' }}>取消</button>
          </div>
        </div>
      )}

      <details style={{ textAlign: 'left', color: '#444', fontSize: '10px' }}>
        <summary style={{ cursor: 'pointer' }}>系统调试 (Console)</summary>
        <pre>{JSON.stringify({ targetVariantId, mutateVariantId, suppressChainId }, null, 2)}</pre>
      </details>
    </div>
  )
}
