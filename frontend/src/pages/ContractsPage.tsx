import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Api, ApiError, type ContractAgentDraftResponse, type ContractResponse, type ContractParty, type ContractBriefResponse } from '../api'
import { useAppSession } from '../app/context'
import { useNotification } from '../app/NotificationContext'

async function copyToClipboard(text: string, notify: (type: 'success' | 'error' | 'info', message: string) => void) {
  try {
    await navigator.clipboard.writeText(text)
    notify('success', '已复制到剪贴板')
  } catch {
    notify('error', '复制失败')
  }
}

export default function ContractsPage() {
  const { playerId } = useAppSession()
  const { notify } = useNotification()
  const [loading, setLoading] = useState(false)

  // Contract Management (by ID)
  const [targetId, setTargetId] = useState('')
  const [actionLoading, setActionLoading] = useState(false)
  const [contractDetail, setContractDetail] = useState<ContractResponse | null>(null)

  // AI Drafting
  const [naturalLanguage, setNaturalLanguage] = useState('')
  const [draft, setDraft] = useState<ContractAgentDraftResponse | null>(null)
  const [isEditingDraft, setIsEditingDraft] = useState(false)
  const [editedDraftJson, setEditedDraftJson] = useState('')

  // Mentions state
  const [showMentionList, setShowMentionList] = useState(false)
  const [mentionType, setMentionType] = useState<'PLAYER' | 'CONTRACT' | null>(null)
  const [mentionQuery, setMentionQuery] = useState('')
  const [mentionIndex, setMentionIndex] = useState(0)
  const [players, setPlayers] = useState<string[]>([])
  const [contracts, setContracts] = useState<ContractBriefResponse[]>([])
  
  const inputRef = useRef<HTMLTextAreaElement>(null)

  const fetchMentionsData = useCallback(async () => {
    if (!playerId) return
    try {
      const [pRes, cRes] = await Promise.all([
        Api.listPlayers(50),
        Api.listContracts(playerId, 50)
      ])
      setPlayers(pRes.items)
      setContracts(cRes.items)
    } catch (e) {
      console.error('Mention data fetch failed', e)
    }
  }, [playerId])

  useEffect(() => {
    fetchMentionsData()
  }, [fetchMentionsData])

  const handleInputChange = (val: string) => {
    setNaturalLanguage(val)
    const cursor = inputRef.current?.selectionStart || 0

    // Detect @ for players
    const lastAt = val.lastIndexOf('@', cursor - 1)
    if (lastAt !== -1 && (lastAt === 0 || val[lastAt - 1] === ' ')) {
      const query = val.slice(lastAt + 1, cursor)
      if (!query.includes(' ')) {
        setMentionType('PLAYER')
        setMentionQuery(query)
        setMentionIndex(0)
        setShowMentionList(true)
        return
      }
    }

    // Detect # for contracts
    const lastHash = val.lastIndexOf('#', cursor - 1)
    if (lastHash !== -1 && (lastHash === 0 || val[lastHash - 1] === ' ')) {
      const query = val.slice(lastHash + 1, cursor)
      if (!query.includes(' ')) {
        setMentionType('CONTRACT')
        setMentionQuery(query)
        setMentionIndex(0)
        setShowMentionList(true)
        return
      }
    }

    setShowMentionList(false)
  }

  const filteredItems = useMemo(() => {
    if (mentionType === 'PLAYER') {
      return players.filter(p => p.toLowerCase().includes(mentionQuery.toLowerCase()));
    } else if (mentionType === 'CONTRACT') {
      return contracts.filter(c => c.title.toLowerCase().includes(mentionQuery.toLowerCase()) || c.contract_id.includes(mentionQuery));
    }
    return [];
  }, [mentionType, players, contracts, mentionQuery]);

  const selectMention = (item: string | ContractBriefResponse) => {
    const cursor = inputRef.current?.selectionStart || 0
    let replacement = ''
    let startIdx = 0

    if (mentionType === 'PLAYER') {
      replacement = `@${item} `
      startIdx = naturalLanguage.lastIndexOf('@', cursor - 1)
    } else {
      const c = item as ContractBriefResponse
      replacement = `#${c.contract_id} `
      startIdx = naturalLanguage.lastIndexOf('#', cursor - 1)
    }

    const newVal = naturalLanguage.slice(0, startIdx) + replacement + naturalLanguage.slice(cursor)
    setNaturalLanguage(newVal)
    setShowMentionList(false)
    inputRef.current?.focus()
  }

  const handleDraft = async () => {
    if (!naturalLanguage.trim()) return
    setDraft(null)
    setLoading(true)
    try {
      const res = await Api.contractAgentDraft({
        actor_id: `user:${playerId}`,
        natural_language: naturalLanguage
      })
      setDraft(res)
      setEditedDraftJson(JSON.stringify(res.contract_create, null, 2))
      setIsEditingDraft(false)
      notify('success', '合约草案已生成')
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : (e instanceof Error ? e.message : String(e))
      notify('error', msg)
    } finally {
      setLoading(false)
    }
  }

  // Refined plan: I need to check Api client for contract methods.
  return (
    <div style={{ display: 'grid', gap: 20 }}>
      <div className="card" style={{ textAlign: 'left' }}>
        <h2 style={{ marginTop: 0 }}>智能合约中心</h2>
        <div style={{ color: '#666', marginBottom: 20 }}>
          通过 AI 草拟合约，或者管理已知的合约 ID。
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20 }}>
          {/* Left: AI Drafting */}
          <div style={{ borderRight: '1px solid #eee', paddingRight: 20, position: 'relative' }}>
            <h4 style={{ margin: '0 0 10px' }}>AI 智能草拟</h4>
            
            {/* Mention List UI */}
            {showMentionList && (
              <div style={{
                position: 'absolute',
                top: '100%',
                left: 0,
                right: 20,
                background: '#fff',
                border: '1px solid #ddd',
                boxShadow: '0 -5px 15px rgba(0,0,0,0.1)',
                zIndex: 100,
                maxHeight: '150px',
                overflowY: 'auto',
                marginTop: '5px',
                borderRadius: '4px'
              }}>
                {mentionType === 'PLAYER' ? (
                  (filteredItems as string[]).map((p, idx) => {
                    const isSelected = mentionIndex === idx;
                    return (
                      <div 
                        key={p} 
                        onClick={() => selectMention(p)}
                        style={{ 
                          padding: '8px 12px', 
                          cursor: 'pointer', 
                          borderBottom: '1px solid #eee',
                          fontSize: '12px',
                          background: isSelected ? '#f0f7ff' : '#fff',
                        }}
                      >
                        @{p}
                      </div>
                    );
                  })
                ) : (
                  (filteredItems as ContractBriefResponse[]).map((c, idx) => {
                    const isSelected = mentionIndex === idx;
                    const partiesText = (c.parties && c.parties.length > 0) ? c.parties.join(',') : ''
                    const total = (c.required_signers && c.required_signers.length > 0) ? c.required_signers.length : 0
                    const signed = (c.signatures && c.signatures.length > 0) ? c.signatures.length : 0
                    const signText = total > 0 ? `${signed}/${total}` : ''
                    const timeText = c.created_at ? String(c.created_at).slice(11, 16) : ''
                    const parts: string[] = []
                    if (partiesText) parts.push(partiesText)
                    if (signText) parts.push(`signed:${signText}`)
                    if (timeText) parts.push(timeText)
                    const summary = parts.length > 0 ? ` | ${parts.join(' | ')}` : ''
                    return (
                      <div 
                        key={c.contract_id} 
                        onClick={() => selectMention(c)}
                        style={{ 
                          padding: '8px 12px', 
                          cursor: 'pointer', 
                          borderBottom: '1px solid #eee',
                          background: isSelected ? '#f0f7ff' : '#fff',
                        }}
                      >
                        #{c.title}{summary} | {c.status} | {c.kind} ({c.contract_id.slice(0, 8)})
                      </div>
                    );
                  })
                )}
              </div>
            )}

            <div style={{ display: 'grid', gap: 10 }}>
              <textarea
                ref={inputRef}
                style={{ width: '100%', minHeight: 100, padding: 10, boxSizing: 'border-box' }}
                placeholder="例如: 我想和 @bob 签署一份对赌协议，如果 #BLUEGOLD 价格超过 150..."
                value={naturalLanguage}
                onChange={e => handleInputChange(e.target.value)}
                onKeyDown={e => {
                  if (showMentionList && filteredItems.length > 0) {
                    if (e.key === 'ArrowDown') {
                      e.preventDefault();
                      setMentionIndex(prev => (prev + 1) % filteredItems.length);
                    } else if (e.key === 'ArrowUp') {
                      e.preventDefault();
                      setMentionIndex(prev => (prev - 1 + filteredItems.length) % filteredItems.length);
                    } else if (e.key === 'Enter' || e.key === 'Tab') {
                      e.preventDefault();
                      selectMention(filteredItems[mentionIndex]);
                    } else if (e.key === 'Escape') {
                      setShowMentionList(false);
                    }
                    return;
                  }
                }}
              />
              <button 
                onClick={handleDraft} 
                disabled={loading || !naturalLanguage.trim()}
                style={{ width: '100%', padding: '12px' }}
              >
                {loading ? 'AI 思考中...' : '生成合约草案'}
              </button>
            </div>
          </div>

          {/* Right: Manual Management */}
          <div>
            <h4 style={{ margin: '0 0 10px' }}>单体合约管理</h4>
            <div style={{ display: 'grid', gap: 10 }}>
              <input 
                placeholder="输入 Contract ID (如 con:...)"
                value={targetId}
                onChange={e => setTargetId(e.target.value)}
                style={{ width: '100%', padding: '10px', boxSizing: 'border-box' }}
              />
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
                <button 
                  onClick={() => handleAction('sign')} 
                  disabled={!targetId || actionLoading}
                  style={{ padding: '10px', borderRadius: 8, cursor: 'pointer', border: '1px solid #ddd', background: '#fff', transition: 'all 0.2s' }}
                  onMouseOver={e => e.currentTarget.style.background = '#f0f0f0'}
                  onMouseOut={e => e.currentTarget.style.background = '#fff'}
                >签署 (Sign)</button>
                <button 
                  onClick={() => handleAction('activate')} 
                  disabled={!targetId || actionLoading}
                  style={{ padding: '10px', borderRadius: 8, cursor: 'pointer', border: '1px solid #ddd', background: '#fff', transition: 'all 0.2s' }}
                  onMouseOver={e => e.currentTarget.style.background = '#f0f0f0'}
                  onMouseOut={e => e.currentTarget.style.background = '#fff'}
                >激活 (Activate)</button>
                <button 
                  onClick={() => handleAction('settle')} 
                  disabled={!targetId || actionLoading}
                  style={{ padding: '10px', borderRadius: 8, cursor: 'pointer', border: '1px solid #ddd', background: '#fff', transition: 'all 0.2s' }}
                  onMouseOver={e => e.currentTarget.style.background = '#f0f0f0'}
                  onMouseOut={e => e.currentTarget.style.background = '#fff'}
                >结算 (Settle)</button>
                <button 
                  onClick={() => handleAction('run_rules')} 
                  disabled={!targetId || actionLoading}
                  style={{ padding: '10px', borderRadius: 8, cursor: 'pointer', border: '1px solid #ddd', background: '#fff', transition: 'all 0.2s' }}
                  onMouseOver={e => e.currentTarget.style.background = '#f0f0f0'}
                  onMouseOut={e => e.currentTarget.style.background = '#fff'}
                >执行规则</button>
                <button 
                  onClick={fetchContractDetail} 
                  disabled={!targetId || actionLoading}
                  style={{ gridColumn: 'span 2', marginTop: 5, background: '#1890ff', color: '#fff', border: 'none', padding: '10px', borderRadius: 8, fontWeight: 600, cursor: 'pointer', boxShadow: '0 2px 4px rgba(24,144,255,0.2)' }}
                >
                  查看详情 (Fetch Detail)
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>

      {contractDetail && (
        <div className="card" style={{ textAlign: 'left', border: '2px solid #1890ff', position: 'relative' }}>
          <button 
            onClick={() => setContractDetail(null)}
            style={{ position: 'absolute', right: 10, top: 10, padding: '4px 8px' }}
          >关闭</button>
          <h3 style={{ marginTop: 0, color: '#1890ff' }}>合约详情</h3>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 15, fontSize: 14 }}>
            <div>
              <div style={{ color: '#888', marginBottom: 4 }}>ID</div>
              <code 
                style={{ cursor: 'pointer', display: 'block', background: '#f0f0f0', padding: '4px 8px', borderRadius: 4 }}
                onClick={() => copyToClipboard(contractDetail.contract_id, notify)}
                title="点击复制"
              >{contractDetail.contract_id}</code>
            </div>
            <div>
              <div style={{ color: '#888', marginBottom: 4 }}>状态</div>
              <div style={{ fontWeight: 700, color: contractDetail.status === 'ACTIVE' ? '#52c41a' : '#faad14' }}>
                {contractDetail.status}
              </div>
            </div>
            <div>
              <div style={{ color: '#888', marginBottom: 4 }}>类型 (Kind)</div>
              <div>{contractDetail.kind}</div>
            </div>
            <div>
              <div style={{ color: '#888', marginBottom: 4 }}>标题</div>
              <div>{contractDetail.title}</div>
            </div>
            <div style={{ gridColumn: 'span 2' }}>
              <div style={{ color: '#888', marginBottom: 4 }}>参与方 (Parties)</div>
              <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                {contractDetail.parties.map(p => (
                  <span 
                    key={p} 
                    style={{ 
                      padding: '2px 8px', 
                      background: contractDetail.signatures[p] ? '#f6ffed' : '#fff1f0',
                      border: `1px solid ${contractDetail.signatures[p] ? '#b7eb8f' : '#ffa39e'}`,
                      borderRadius: 12,
                      fontSize: 12,
                      color: contractDetail.signatures[p] ? '#389e0d' : '#cf1322'
                    }}
                  >
                    {p} {contractDetail.signatures[p] ? '✓' : '✗'}
                  </span>
                ))}
              </div>
            </div>
            <div style={{ gridColumn: 'span 2' }}>
              <details>
                <summary style={{ cursor: 'pointer', color: '#888' }}>查看详细条款 (Terms)</summary>
                <pre style={{ fontSize: 11, background: '#f8f8f8', padding: 10, marginTop: 10, overflow: 'auto' }}>
                  {JSON.stringify(contractDetail.terms, null, 2)}
                </pre>
              </details>
            </div>
          </div>
        </div>
      )}

      {draft && (
        <div className="card" style={{ textAlign: 'left', border: '2px solid #52c41a' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
            <h3 style={{ margin: 0, color: '#52c41a' }}>合约草案已生成</h3>
            <button 
              className="cyber-button"
              onClick={() => setIsEditingDraft(!isEditingDraft)}
              style={{ fontSize: '11px', padding: '4px 12px' }}
            >
              {isEditingDraft ? '查看 AI 解释' : '手动编辑 JSON'}
            </button>
          </div>

          <div style={{ display: 'grid', gap: 10 }}>
            <div><strong>风险评估:</strong> <span style={{ color: draft.risk_rating === 'HIGH' ? 'red' : 'green' }}>{draft.risk_rating}</span></div>
            
            {isEditingDraft ? (
              <textarea
                style={{ 
                  width: '100%', minHeight: 200, padding: 10, fontFamily: 'monospace', 
                  fontSize: '12px', background: '#f8f8f8', border: '1px solid #ddd' 
                }}
                value={editedDraftJson}
                onChange={e => setEditedDraftJson(e.target.value)}
              />
            ) : (
              <div style={{ background: '#f6ffed', padding: 15, borderRadius: 8 }}>
                <div style={{ fontWeight: 600, marginBottom: 5 }}>AI 解释:</div>
                {draft.explanation}
              </div>
            )}

            <button 
              onClick={() => {
                handleCreateContract()
              }}
              style={{ width: '100%', padding: '12px', background: '#52c41a', color: '#fff', border: 'none', fontWeight: 700, marginTop: 10 }}
            >
              {isEditingDraft ? '保存并正式创建' : '正式创建该合约'}
            </button>
          </div>
        </div>
      )}
    </div>
  )

  async function handleCreateContract() {
    if (!draft) return
    setLoading(true)
    try {
      let finalContractCreate = draft.contract_create
      if (isEditingDraft) {
        try {
          finalContractCreate = JSON.parse(editedDraftJson)
        } catch {
          notify('error', 'JSON 格式错误')
          setLoading(false)
          return
        }
      }

      const parties: ContractParty[] = Array.isArray(finalContractCreate.parties) 
        ? finalContractCreate.parties.map((p: string | ContractParty) => typeof p === 'string' ? { party_id: p, role: 'PARTY' } : p)
        : []

      const res = await Api.contractCreate({
        actor_id: `user:${playerId}`,
        kind: finalContractCreate.kind as string,
        title: finalContractCreate.title as string,
        terms: finalContractCreate.terms as Record<string, unknown>,
        parties: parties,
        required_signers: finalContractCreate.required_signers as string[],
        participation_mode: finalContractCreate.participation_mode as string || null,
        invited_parties: finalContractCreate.invited_parties as string[] || null,
      })
      notify('success', `合约创建成功: ${res.contract_id}`)

      try {
        await fetchMentionsData()
      } catch {
        // ignore
      }
      
      setTargetId(res.contract_id)
      setDraft(null)
      setIsEditingDraft(false)
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : (e instanceof Error ? e.message : String(e))
      notify('error', `创建失败: ${msg}`)
    } finally {
      setLoading(false)
    }
  }

  async function handleAction(type: string) {
    setActionLoading(true)
    try {
      const actor_id = `user:${playerId}`
      switch(type) {
        case 'sign':
          await Api.contractSign(targetId, { signer: actor_id })
          notify('success', '合约已签署')
          break
        case 'activate':
          await Api.contractActivate(targetId, { actor_id })
          notify('success', '合约已激活')
          break
        case 'settle':
          await Api.contractSettle(targetId, { actor_id })
          notify('success', '合约已提交结算')
          break
        case 'run_rules':
          await Api.contractRunRules(targetId, { actor_id })
          notify('success', '规则执行指令已下达')
          break
      }
      // Refresh detail if open
      if (contractDetail) fetchContractDetail()
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : (e instanceof Error ? e.message : String(e))
      notify('error', `操作失败: ${msg}`)
    } finally {
      setActionLoading(false)
    }
  }

  async function fetchContractDetail() {
    if (!targetId) return
    setActionLoading(true)
    try {
      const res = await Api.contractGet(targetId)
      setContractDetail(res)
      notify('success', '合约详情已更新')
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : (e instanceof Error ? e.message : String(e))
      notify('error', `获取详情失败: ${msg}`)
    } finally {
      setActionLoading(false)
    }
  }
}
