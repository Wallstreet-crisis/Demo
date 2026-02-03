import { useState } from 'react'
import { Api, ApiError, type ContractAgentDraftResponse, type ContractResponse } from '../api'
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

  // AI Drafting
  const [naturalLanguage, setNaturalLanguage] = useState('')
  const [draft, setDraft] = useState<ContractAgentDraftResponse | null>(null)

  // Contract Management (by ID)
  const [targetId, setTargetId] = useState('')
  const [actionLoading, setActionLoading] = useState(false)
  const [contractDetail, setContractDetail] = useState<ContractResponse | null>(null)

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
          <div style={{ borderRight: '1px solid #eee', paddingRight: 20 }}>
            <h4 style={{ margin: '0 0 10px' }}>AI 智能草拟</h4>
            <div style={{ display: 'grid', gap: 10 }}>
              <textarea
                style={{ width: '100%', minHeight: 100, padding: 10, boxSizing: 'border-box' }}
                placeholder="例如: 我想和 user:bob 签署一份对赌协议，如果 BLUEGOLD 价格超过 150，他付给我 1000 现金..."
                value={naturalLanguage}
                onChange={e => setNaturalLanguage(e.target.value)}
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
          <h3 style={{ marginTop: 0, color: '#52c41a' }}>合约草案已生成</h3>
          <div style={{ display: 'grid', gap: 10 }}>
            <div><strong>草案 ID:</strong> <code>{draft.draft_id}</code></div>
            <div><strong>风险评估:</strong> <span style={{ color: draft.risk_rating === 'HIGH' ? 'red' : 'green' }}>{draft.risk_rating}</span></div>
            <div style={{ background: '#f6ffed', padding: 15, borderRadius: 8 }}>
              <div style={{ fontWeight: 600, marginBottom: 5 }}>AI 解释:</div>
              {draft.explanation}
            </div>
            <details>
              <summary style={{ cursor: 'pointer', color: '#888' }}>查看 JSON 定义</summary>
              <pre style={{ fontSize: 11, background: '#f8f8f8', padding: 10, marginTop: 10 }}>
                {JSON.stringify(draft.contract_create, null, 2)}
              </pre>
            </details>
            <button 
              onClick={() => {
                handleCreateContract()
              }}
              style={{ width: '100%', padding: '12px', background: '#52c41a', color: '#fff', border: 'none', fontWeight: 700 }}
            >
              正式创建该合约
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
      const res = await Api.contractCreate({
        actor_id: `user:${playerId}`,
        kind: draft.contract_create.kind as string,
        title: draft.contract_create.title as string,
        terms: draft.contract_create.terms as Record<string, unknown>,
        parties: draft.contract_create.parties as string[],
        required_signers: draft.contract_create.required_signers as string[],
        participation_mode: draft.contract_create.participation_mode as string || null,
        invited_parties: draft.contract_create.invited_parties as string[] || null,
      })
      notify('success', `合约创建成功: ${res.contract_id}`)
      setTargetId(res.contract_id)
      setDraft(null)
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
