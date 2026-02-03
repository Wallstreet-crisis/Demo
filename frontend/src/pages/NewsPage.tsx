import { useEffect, useMemo, useRef, useState } from 'react'
import {
  Api,
  ApiError,
  type NewsCreateCardResponse,
  type NewsEmitVariantResponse,
  type NewsInboxResponse,
  type NewsInboxResponseItem,
} from '../api'
import { useAppSession } from '../app/context'
import { WsClient } from '../api'
import { useNotification } from '../app/NotificationContext'

function getEventType(payload: unknown): string | null {
  if (!payload || typeof payload !== 'object') return null
  const v = (payload as Record<string, unknown>).event_type
  return typeof v === 'string' ? v : null
}

function formatTime(s: string): string {
  if (!s) return ''
  const d = new Date(s)
  if (Number.isNaN(d.getTime())) return s
  return d.toLocaleString()
}

async function copyToClipboard(text: string, notify: (type: 'success' | 'error' | 'info', message: string) => void) {
  try {
    await navigator.clipboard.writeText(text)
    notify('success', '已复制到剪贴板')
  } catch {
    notify('error', '复制失败')
  }
}

export default function NewsPage() {
  const { playerId, symbol } = useAppSession()
  const { notify } = useNotification()
  const [loading, setLoading] = useState(true)

  const [inbox, setInbox] = useState<NewsInboxResponse | null>(null)
  const [ownedCards, setOwnedCards] = useState<string[]>([])
  const [loadingOwned, setLoadingOwned] = useState(false)

  const [cardKind, setCardKind] = useState<string>('RUMOR')
  const [cardText, setCardText] = useState<string>('')
  const [lastCard, setLastCard] = useState<NewsCreateCardResponse | null>(null)
  const [lastVariant, setLastVariant] = useState<NewsEmitVariantResponse | null>(null)

  // Pre-fill fields
  const [targetVariantId, setTargetVariantId] = useState<string>('')
  const [propLimit, setPropLimit] = useState<number>(50)
  const [propSpendCash, setPropSpendCash] = useState<string>('')

  const [purchaseKind, setPurchaseKind] = useState<string>('RUMOR')
  const [purchasePrice, setPurchasePrice] = useState<number>(100)
  const [purchaseText, setPurchaseText] = useState<string>('')

  const [selectedInboxItem, setSelectedInboxItem] = useState<NewsInboxResponseItem | null>(null)

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
    setLoadingOwned(true)
    try {
      const r = await Api.newsOwnershipList(`user:${playerId}`)
      setOwnedCards(Array.isArray(r.cards) ? r.cards : [])
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : (e instanceof Error ? e.message : String(e))
      notify('error', `获取已购卡片失败: ${msg}`)
      setOwnedCards([])
    } finally {
      setLoadingOwned(false)
    }
  }

  async function createCardAndVariant(): Promise<void> {
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
      setTargetVariantId(v.variant_id)
      notify('success', `卡片与变体已创建`)
      await refreshInbox()
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : (e instanceof Error ? e.message : String(e))
      notify('error', msg)
    }
  }

  async function purchase(): Promise<void> {
    try {
      const r = await Api.newsStorePurchase({
        buyer_user_id: `user:${playerId}`,
        kind: purchaseKind,
        price_cash: Number(purchasePrice),
        symbols: [symbol],
        tags: [],
        initial_text: purchaseText,
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

  useEffect(() => {
    refreshInbox()
    refreshOwnedCards()
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
    const vid = targetVariantId || lastVariant?.variant_id
    if (!vid) {
      notify('error', '请先选择或创建一个变体')
      return
    }
    const spendCash = propSpendCash.trim() === '' ? undefined : Number(propSpendCash)
    if (spendCash !== undefined && (!Number.isFinite(spendCash) || spendCash <= 0)) {
      notify('error', 'spend_cash must be a positive number')
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

  return (
    <div style={{ display: 'grid', gap: 12 }}>
      <div className="card" style={{ textAlign: 'left' }}>
        <h3 style={{ marginTop: 0 }}>Inbox (收件箱)</h3>
        <button onClick={refreshInbox} disabled={loading}>{loading ? '刷新中...' : 'Refresh'}</button>

        {loading && !inbox ? (
          <div style={{ padding: 20, color: '#999' }}>加载中...</div>
        ) : inbox?.items?.length ? (
          <div style={{ display: 'grid', gap: 10, marginTop: 10 }}>
            {inbox.items.map((it) => (
              <div
                key={it.delivery_id}
                style={{
                  border: '1px solid #eee',
                  borderRadius: 10,
                  padding: 12,
                  background: '#fff',
                  cursor: 'pointer',
                  transition: 'background 0.2s'
                }}
                onClick={() => {
                  setTargetVariantId(it.variant_id)
                  setSelectedInboxItem(it)
                  notify('info', '已选择该消息并开启详情展示')
                }}
                onMouseOver={(e) => e.currentTarget.style.background = '#fafafa'}
                onMouseOut={(e) => e.currentTarget.style.background = '#fff'}
              >
                <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'baseline' }}>
                  <div style={{ fontWeight: 700, color: '#1890ff' }}>{formatTime(it.delivered_at)}</div>
                  <div style={{ color: '#666', background: '#f0f0f0', padding: '2px 6px', borderRadius: 4, fontSize: 12 }}>{it.delivery_reason}</div>
                  <div style={{ color: '#888', fontSize: 12 }}>from <code>{it.from_actor_id}</code></div>
                </div>

                <div style={{ marginTop: 8, fontSize: 15, lineHeight: 1.5 }}>{it.text}</div>
              </div>
            ))}
          </div>
        ) : (
          <div style={{ marginTop: 10, color: '#666' }}>暂无收件箱内容。</div>
        )}
      </div>

      {selectedInboxItem && (
        <div className="card" style={{ textAlign: 'left', border: '2px solid #1890ff', position: 'relative' }}>
          <button 
            onClick={() => setSelectedInboxItem(null)}
            style={{ position: 'absolute', right: 10, top: 10, padding: '4px 8px' }}
          >关闭</button>
          <h3 style={{ marginTop: 0, color: '#1890ff' }}>消息详情</h3>
          <div style={{ display: 'grid', gap: 10, fontSize: 14 }}>
            <div><strong>发送时间:</strong> {formatTime(selectedInboxItem.delivered_at)}</div>
            <div><strong>投递原因:</strong> {selectedInboxItem.delivery_reason}</div>
            <div><strong>发送者:</strong> <code style={{ cursor: 'pointer' }} onClick={() => copyToClipboard(selectedInboxItem.from_actor_id, notify)} title="点击复制">{selectedInboxItem.from_actor_id}</code></div>
            <div><strong>卡片 ID:</strong> <code style={{ cursor: 'pointer' }} onClick={() => copyToClipboard(selectedInboxItem.card_id, notify)} title="点击复制">{selectedInboxItem.card_id}</code></div>
            <div><strong>变体 ID:</strong> <code style={{ cursor: 'pointer' }} onClick={() => copyToClipboard(selectedInboxItem.variant_id, notify)} title="点击复制">{selectedInboxItem.variant_id}</code></div>
            <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap' }}>
              <div><strong>Symbols:</strong> {JSON.stringify(selectedInboxItem.symbols || [])}</div>
              <div><strong>Tags:</strong> {JSON.stringify(selectedInboxItem.tags || [])}</div>
            </div>
            {selectedInboxItem.truth_payload !== undefined && selectedInboxItem.truth_payload !== null && (
              <div style={{ border: '1px dashed #ffa39e', padding: 8, background: '#fff2f0', borderRadius: 4 }}>
                <strong>Truth Payload:</strong>
                <pre style={{ fontSize: 12, margin: '5px 0' }}>{JSON.stringify(selectedInboxItem.truth_payload, null, 2)}</pre>
              </div>
            )}
            <div style={{ borderTop: '1px solid #eee', paddingTop: 10, marginTop: 5 }}>
              <strong>正文:</strong>
              <div style={{ marginTop: 5, padding: 10, background: '#fafafa', borderRadius: 4, lineHeight: 1.6 }}>
                {selectedInboxItem.text}
              </div>
            </div>
            <div style={{ display: 'flex', gap: 10, marginTop: 10 }}>
              <button 
                onClick={() => {
                  setTargetVariantId(selectedInboxItem.variant_id)
                  notify('success', '变体 ID 已填入传播面板')
                }}
                style={{ flex: 1 }}
              >准备传播该变体</button>
              <button 
                onClick={() => {
                  setCardText(selectedInboxItem.text)
                  notify('info', '内容已填入创建面板，可在此基础上修改')
                  window.scrollTo({ top: document.body.scrollHeight, behavior: 'smooth' })
                }}
                style={{ flex: 1, background: '#52c41a', color: '#fff', border: 'none' }}
              >以此创建新变体</button>
            </div>
          </div>
        </div>
      )}

      <div className="card" style={{ textAlign: 'left' }}>
        <h3 style={{ marginTop: 0 }}>我的卡片 (Owned Cards)</h3>
        <button onClick={refreshOwnedCards} disabled={loadingOwned}>
          {loadingOwned ? '刷新中...' : 'Refresh'}
        </button>
        
        {loadingOwned && (!ownedCards || (Array.isArray(ownedCards) && ownedCards.length === 0)) ? (
          <div style={{ padding: 20, color: '#999' }}>加载中...</div>
        ) : (Array.isArray(ownedCards) && ownedCards.length > 0) ? (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', gap: 12, marginTop: 15 }}>
            {ownedCards.map((cardId) => (
              <div
                key={cardId}
                style={{
                  padding: '12px',
                  background: '#f6ffed',
                  borderRadius: 10,
                  border: '1px solid #b7eb8f',
                  fontSize: 13,
                  cursor: 'pointer',
                  color: '#389e0d',
                  transition: 'all 0.2s'
                }}
                onClick={() => {
                  copyToClipboard(cardId, notify)
                }}
                onMouseOver={(e) => {
                  e.currentTarget.style.boxShadow = '0 2px 8px rgba(0,0,0,0.1)'
                  e.currentTarget.style.borderColor = '#52c41a'
                }}
                onMouseOut={(e) => {
                  e.currentTarget.style.boxShadow = 'none'
                  e.currentTarget.style.borderColor = '#b7eb8f'
                }}
              >
                <div style={{ fontSize: 11, color: '#73d13d', marginBottom: 4 }}>Card ID (点击复制)</div>
                <code style={{ fontWeight: 700, wordBreak: 'break-all' }}>{cardId}</code>
              </div>
            ))}
          </div>
        ) : (
          <div style={{ marginTop: 10, color: '#666' }}>你目前没有拥有任何卡片。</div>
        )}
      </div>

      <div className="card" style={{ textAlign: 'left' }}>
        <h3 style={{ marginTop: 0 }}>新闻操作面板</h3>
        
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20 }}>
          <div style={{ borderRight: '1px solid #eee', paddingRight: 20 }}>
            <h4 style={{ margin: '0 0 10px' }}>第一步: 创建并发布 (Create & Emit)</h4>
            <div style={{ display: 'grid', gap: 10 }}>
              <label>
                <div style={{ fontSize: 12, color: '#888', marginBottom: 4 }}>新闻类型</div>
                <select value={cardKind} onChange={(e) => setCardKind(e.target.value)} style={{ width: '100%', padding: '6px' }}>
                  <option value="RUMOR">传闻 (Rumor)</option>
                  <option value="OFFICIAL">官方 (Official)</option>
                  <option value="ANALYSIS">分析 (Analysis)</option>
                </select>
              </label>
              <label>
                <div style={{ fontSize: 12, color: '#888', marginBottom: 4 }}>正文内容</div>
                <textarea
                  style={{ width: '100%', minHeight: 60, padding: '6px', boxSizing: 'border-box' }}
                  placeholder="输入新闻内容..."
                  value={cardText}
                  onChange={(e) => setCardText(e.target.value)}
                />
              </label>
              <button onClick={createCardAndVariant} style={{ width: '100%', padding: '12px', borderRadius: 8, background: '#1890ff', color: '#fff', border: 'none', fontWeight: 600, cursor: 'pointer', transition: 'all 0.2s' }} onMouseOver={e => e.currentTarget.style.opacity = '0.9'} onMouseOut={e => e.currentTarget.style.opacity = '1'}>发布新闻</button>
            </div>
          </div>

          <div>
            <h4 style={{ margin: '0 0 10px' }}>第二步: 传播 (Propagate)</h4>
            <div style={{ display: 'grid', gap: 10 }}>
              <label>
                <div style={{ fontSize: 12, color: '#888', marginBottom: 4 }}>选中的变体 ID</div>
                <input 
                  value={targetVariantId} 
                  onChange={e => setTargetVariantId(e.target.value)} 
                  placeholder="点击上方消息自动填充"
                  style={{ width: '100%', padding: '10px', borderRadius: 8, border: '1px solid #ddd', boxSizing: 'border-box' }}
                />
              </label>
              <div style={{ display: 'flex', gap: 10 }}>
                <label style={{ flex: 1 }}>
                  <div style={{ fontSize: 12, color: '#888', marginBottom: 4 }}>送达限制</div>
                  <input type="number" value={propLimit} onChange={(e) => setPropLimit(Number(e.target.value))} style={{ width: '100%', padding: '10px', borderRadius: 8, border: '1px solid #ddd', boxSizing: 'border-box' }} />
                </label>
                <label style={{ flex: 1 }}>
                  <div style={{ fontSize: 12, color: '#888', marginBottom: 4 }}>投入资金</div>
                  <input
                    value={propSpendCash}
                    onChange={(e) => setPropSpendCash(e.target.value)}
                    placeholder="0"
                    style={{ width: '100%', padding: '10px', borderRadius: 8, border: '1px solid #ddd', boxSizing: 'border-box' }}
                  />
                </label>
              </div>
              <button onClick={propagateLast} style={{ width: '100%', padding: '12px', background: '#52c41a', color: '#fff', border: 'none', borderRadius: 8, fontWeight: 600, cursor: 'pointer', boxShadow: '0 2px 4px rgba(82,196,26,0.2)', transition: 'all 0.2s' }} onMouseOver={e => e.currentTarget.style.opacity = '0.9'} onMouseOut={e => e.currentTarget.style.opacity = '1'}>开始传播</button>
            </div>
          </div>
        </div>
      </div>

      <div className="card" style={{ textAlign: 'left' }}>
        <h3 style={{ marginTop: 0 }}>新闻商店 (Store)</h3>
        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'flex-end' }}>
          <label style={{ flex: 1 }}>
            <div style={{ fontSize: 12, color: '#888', marginBottom: 4 }}>种类</div>
            <input value={purchaseKind} onChange={(e) => setPurchaseKind(e.target.value)} style={{ width: '100%', padding: '10px', borderRadius: 8, border: '1px solid #ddd', boxSizing: 'border-box' }} />
          </label>
          <label style={{ flex: 1 }}>
            <div style={{ fontSize: 12, color: '#888', marginBottom: 4 }}>价格</div>
            <input type="number" value={purchasePrice} onChange={(e) => setPurchasePrice(Number(e.target.value))} style={{ width: '100%', padding: '10px', borderRadius: 8, border: '1px solid #ddd', boxSizing: 'border-box' }} />
          </label>
          <label style={{ flex: 2 }}>
            <div style={{ fontSize: 12, color: '#888', marginBottom: 4 }}>初始文本</div>
            <input
              placeholder="initial_text"
              value={purchaseText}
              onChange={(e) => setPurchaseText(e.target.value)}
              style={{ width: '100%', padding: '10px', borderRadius: 8, border: '1px solid #ddd', boxSizing: 'border-box' }}
            />
          </label>
          <button onClick={purchase} style={{ padding: '10px 24px', borderRadius: 8, background: '#faad14', color: '#fff', border: 'none', fontWeight: 600, cursor: 'pointer', transition: 'all 0.2s' }} onMouseOver={e => e.currentTarget.style.opacity = '0.9'} onMouseOut={e => e.currentTarget.style.opacity = '1'}>购买</button>
        </div>
      </div>

      <details style={{ textAlign: 'left', color: '#999' }}>
        <summary style={{ cursor: 'pointer', fontSize: 13 }}>调试数据 (Debug Info)</summary>
        <div style={{ padding: 10, background: '#f8f8f8', borderRadius: 4, marginTop: 10 }}>
          <div><strong>Last Created:</strong> {JSON.stringify({ lastCard, lastVariant })}</div>
          <div><strong>Inbox Raw:</strong> {JSON.stringify(inbox)}</div>
        </div>
      </details>
    </div>
  )
}
