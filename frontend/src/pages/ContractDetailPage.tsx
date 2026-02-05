import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useParams } from 'react-router-dom'
import { Api, ApiError, type ContractAgentAuditResponse, type ContractResponse } from '../api'
import { useAppSession } from '../app/context'
import { useNotification } from '../app/NotificationContext'

export default function ContractDetailPage() {
  const { playerId } = useAppSession()
  const { notify } = useNotification()
  const params = useParams()
  const contractId = params.contractId || ''

  const [loading, setLoading] = useState(false)
  const [actionLoading, setActionLoading] = useState(false)
  const [detail, setDetail] = useState<ContractResponse | null>(null)
  const [auditLoading, setAuditLoading] = useState(false)
  const [audit, setAudit] = useState<ContractAgentAuditResponse | null>(null)
  const autoAuditRef = useRef<{ contractId: string; done: boolean }>({ contractId: '', done: false })

  const refresh = useCallback(async () => {
    if (!contractId) return
    setLoading(true)
    try {
      const res = await Api.contractGet(contractId)
      setDetail(res)
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : (e instanceof Error ? e.message : String(e))
      notify('error', `获取合约失败: ${msg}`)
    } finally {
      setLoading(false)
    }
  }, [contractId, notify])

  useEffect(() => {
    refresh()
  }, [refresh])

  const actorId = useMemo(() => {
    return playerId ? `user:${playerId}` : ''
  }, [playerId])

  const resolvedActorId = useMemo(() => {
    if (!actorId) return ''
    if (!detail) return actorId
    const probe = actorId.toLowerCase()
    const pools = [detail.required_signers || [], detail.parties || [], detail.invited_parties || []]
    for (const arr of pools) {
      const hit = arr.find(x => String(x).toLowerCase() === probe)
      if (hit) return String(hit)
    }
    return actorId
  }, [actorId, detail])

  const signDisabledReason = useMemo(() => {
    if (!playerId) return '当前未登录：请先 RE_AUTH / onboarding'
    if (!detail) return '合约未加载'
    const reqs = (detail.required_signers || []).map(x => String(x).toLowerCase())
    const me = String(resolvedActorId || actorId).toLowerCase()
    if (!reqs.includes(me)) return '你不是 required_signer'
    const sigs = detail.signatures || {}
    const hasSigned = Object.keys(sigs).some(k => String(k).toLowerCase() === me)
    if (hasSigned) return '你已签署'
    if (!['DRAFT', 'SIGNED'].includes(detail.status)) return `当前状态不可签署: ${detail.status}`
    return ''
  }, [playerId, detail, actorId, resolvedActorId])

  const joinDisabledReason = useMemo(() => {
    if (!playerId) return '当前未登录：请先 RE_AUTH / onboarding'
    if (!detail) return '合约未加载'
    if (detail.participation_mode !== 'OPT_IN') return `非 OPT_IN: ${detail.participation_mode}`
    const invited = (detail.invited_parties || []).map(x => String(x).toLowerCase())
    const parties = (detail.parties || []).map(x => String(x).toLowerCase())
    const me = String(resolvedActorId || actorId).toLowerCase()
    if (!invited.includes(me)) return '你不在 invited_parties'
    if (parties.includes(me)) return '你已加入 parties'
    return ''
  }, [playerId, detail, actorId, resolvedActorId])

  const requiredSignerStatus = useMemo(() => {
    const reqs = detail?.required_signers || []
    const sigs = detail?.signatures || {}
    return reqs.map((s) => ({ signer: s, signed: Boolean(sigs[s]) }))
  }, [detail])

  const invitedStatus = useMemo(() => {
    const invited = detail?.invited_parties || []
    const parties = new Set(detail?.parties || [])
    return invited.map((u) => ({ user_id: u, joined: parties.has(u) }))
  }, [detail])

  const canSign = useMemo(() => {
    return !signDisabledReason
  }, [signDisabledReason])

  const canJoin = useMemo(() => {
    return !joinDisabledReason
  }, [joinDisabledReason])

  const refreshAudit = useCallback(async (force: boolean) => {
    if (!playerId || !contractId) return
    setAuditLoading(true)
    try {
      const res = await Api.contractAgentAudit({
        actor_id: `user:${playerId}`,
        contract_id: contractId,
        force,
      })
      setAudit(res)
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : (e instanceof Error ? e.message : String(e))
      notify('error', `审计失败: ${msg}`)
    } finally {
      setAuditLoading(false)
    }
  }, [playerId, contractId, notify])

  useEffect(() => {
    if (!playerId || !contractId) return
    if (autoAuditRef.current.contractId !== contractId) {
      autoAuditRef.current = { contractId, done: false }
    }
    if (autoAuditRef.current.done) return
    autoAuditRef.current.done = true
    refreshAudit(false)
  }, [playerId, contractId, refreshAudit])

  const handleSign = async () => {
    if (!contractId || !actorId) return
    if (!canSign) {
      notify('info', signDisabledReason || '当前不可签署')
      return
    }
    setActionLoading(true)
    try {
      await Api.contractSign(contractId, { signer: resolvedActorId || actorId })
      notify('success', '已签署')
      await refresh()
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : (e instanceof Error ? e.message : String(e))
      notify('error', `签署失败: ${msg}`)
    } finally {
      setActionLoading(false)
    }
  }

  const handleJoin = async () => {
    if (!contractId || !actorId) return
    if (!canJoin) {
      notify('info', joinDisabledReason || '当前不可响应加入')
      return
    }
    setActionLoading(true)
    try {
      await Api.contractJoin(contractId, { joiner: resolvedActorId || actorId })
      notify('success', '已响应加入')
      await refresh()
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : (e instanceof Error ? e.message : String(e))
      notify('error', `响应失败: ${msg}`)
    } finally {
      setActionLoading(false)
    }
  }

  return (
    <div className="card" style={{ textAlign: 'left' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 10 }}>
        <div>
          <div style={{ fontSize: '10px', color: '#64748b' }}>CONTRACT</div>
          <div style={{ fontWeight: 700, fontSize: '16px', color: '#fff', wordBreak: 'break-word' }}>
            {detail?.title || contractId}
          </div>
          <div style={{ fontFamily: 'monospace', fontSize: '11px', color: '#94a3b8' }}>{contractId}</div>
        </div>

        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <button
            className="cyber-button"
            disabled={loading}
            onClick={refresh}
            style={{ fontSize: '11px', padding: '4px 12px' }}
          >
            {loading ? 'SYNC...' : 'REFRESH'}
          </button>
        </div>
      </div>

      {detail ? (
        <div style={{ marginTop: 12, display: 'grid', gap: 12 }}>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
            <div>
              <div style={{ fontSize: '10px', color: '#64748b' }}>STATUS</div>
              <div style={{ fontWeight: 700, color: detail.status === 'ACTIVE' ? 'var(--terminal-success)' : '#fff' }}>{detail.status}</div>
            </div>
            <div>
              <div style={{ fontSize: '10px', color: '#64748b' }}>KIND</div>
              <div style={{ fontFamily: 'monospace' }}>{detail.kind}</div>
            </div>
          </div>

          <div style={{ display: 'grid', gap: 6 }}>
            <div style={{ fontSize: '10px', color: '#64748b' }}>REQUIRED_SIGNERS</div>
            <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
              {requiredSignerStatus.map((it) => (
                <span
                  key={it.signer}
                  style={{
                    padding: '2px 8px',
                    borderRadius: 12,
                    fontSize: 12,
                    border: `1px solid ${it.signed ? '#b7eb8f' : '#ffa39e'}`,
                    background: it.signed ? '#0b3d1f' : '#3b0b0b',
                    color: it.signed ? '#86efac' : '#fecaca',
                    fontFamily: 'monospace',
                  }}
                >
                  {it.signer} {it.signed ? 'SIGNED' : 'PENDING'}
                </span>
              ))}
              {requiredSignerStatus.length === 0 ? (
                <div style={{ opacity: 0.6, fontSize: 12 }}>无</div>
              ) : null}
            </div>

            <div style={{ display: 'flex', gap: 8, marginTop: 6, flexWrap: 'wrap' }}>
              <button
                className="cyber-button"
                onClick={handleSign}
                style={{
                  fontSize: '11px',
                  padding: '4px 12px',
                  background: canSign ? 'var(--terminal-success)' : 'transparent',
                  borderColor: canSign ? 'var(--terminal-success)' : 'var(--terminal-border)',
                  color: canSign ? '#fff' : '#94a3b8',
                  opacity: actionLoading ? 0.6 : (canSign ? 1 : 0.6),
                  cursor: canSign ? 'pointer' : 'not-allowed',
                }}
              >
                签署
              </button>

              <button
                className="cyber-button"
                onClick={handleJoin}
                style={{
                  fontSize: '11px',
                  padding: '4px 12px',
                  background: canJoin ? 'var(--terminal-info)' : 'transparent',
                  borderColor: canJoin ? 'var(--terminal-info)' : 'var(--terminal-border)',
                  color: canJoin ? '#fff' : '#94a3b8',
                  opacity: actionLoading ? 0.6 : (canJoin ? 1 : 0.6),
                  cursor: canJoin ? 'pointer' : 'not-allowed',
                }}
              >
                响应加入
              </button>
            </div>

            {signDisabledReason ? (
              <div style={{ fontSize: '11px', color: '#94a3b8', marginTop: 6 }}>
                签署不可用：{signDisabledReason}
              </div>
            ) : null}
            {joinDisabledReason ? (
              <div style={{ fontSize: '11px', color: '#94a3b8', marginTop: 4 }}>
                响应不可用：{joinDisabledReason}
              </div>
            ) : null}
          </div>

          <div style={{ display: 'grid', gap: 6 }}>
            <div style={{ fontSize: '10px', color: '#64748b' }}>INVITED_PARTIES</div>
            <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
              {invitedStatus.map((it) => (
                <span
                  key={it.user_id}
                  style={{
                    padding: '2px 8px',
                    borderRadius: 12,
                    fontSize: 12,
                    border: `1px solid ${it.joined ? '#b7eb8f' : '#334155'}`,
                    background: it.joined ? '#0b3d1f' : 'rgba(15, 23, 42, 0.6)',
                    color: it.joined ? '#86efac' : '#cbd5e1',
                    fontFamily: 'monospace',
                  }}
                >
                  {it.user_id} {it.joined ? 'JOINED' : 'INVITED'}
                </span>
              ))}
              {invitedStatus.length === 0 ? (
                <div style={{ opacity: 0.6, fontSize: 12 }}>无</div>
              ) : null}
            </div>
          </div>

          <details>
            <summary style={{ cursor: 'pointer', color: '#94a3b8' }}>TERMS_JSON</summary>
            <pre style={{ fontSize: 11, background: '#000', padding: 10, marginTop: 10, overflow: 'auto', color: '#52c41a' }}>
              {JSON.stringify(detail.terms, null, 2)}
            </pre>
          </details>

          <div style={{ marginTop: 10, padding: 12, border: '1px solid rgba(59,130,246,0.3)', background: 'rgba(15, 23, 42, 0.5)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', gap: 10, alignItems: 'center' }}>
              <div>
                <div style={{ fontSize: '10px', color: '#64748b' }}>FIN_AUDIT</div>
                <div style={{ fontSize: '12px', color: '#cbd5e1' }}>
                  风险评级：<span style={{ color: audit?.risk_rating === 'HIGH' ? 'var(--terminal-error)' : 'var(--terminal-success)' }}>{audit?.risk_rating || '--'}</span>
                </div>
              </div>
              <button
                className="cyber-button"
                onClick={() => refreshAudit(true)}
                style={{ fontSize: '11px', padding: '4px 12px' }}
              >
                {auditLoading ? 'AUDITING...' : '强制重审'}
              </button>
            </div>

            {audit ? (
              <details style={{ marginTop: 10 }}>
                <summary style={{ cursor: 'pointer', color: '#94a3b8' }}>查看审计详情</summary>
                <div style={{ marginTop: 10, display: 'grid', gap: 10 }}>
                  <div style={{ color: '#e2e8f0', fontSize: '12px', lineHeight: 1.5 }}>{audit.summary}</div>

                  {audit.issues.length > 0 ? (
                    <div>
                      <div style={{ fontSize: '10px', color: '#64748b', marginBottom: 4 }}>ISSUES</div>
                      <div style={{ display: 'grid', gap: 4, fontSize: '12px', color: '#fecaca' }}>
                        {audit.issues.map((x, i) => (
                          <div key={i}>- {x}</div>
                        ))}
                      </div>
                    </div>
                  ) : null}

                  {audit.questions.length > 0 ? (
                    <div>
                      <div style={{ fontSize: '10px', color: '#64748b', marginBottom: 4 }}>QUESTIONS</div>
                      <div style={{ display: 'grid', gap: 4, fontSize: '12px', color: '#e2e8f0' }}>
                        {audit.questions.map((x, i) => (
                          <div key={i}>- {x}</div>
                        ))}
                      </div>
                    </div>
                  ) : null}
                </div>
              </details>
            ) : (
              <div style={{ marginTop: 10, opacity: 0.7, fontSize: 12 }}>
                {auditLoading ? '审计中...' : (playerId ? '暂无审计结果' : '未登录，无法审计')}
              </div>
            )}
          </div>
        </div>
      ) : (
        <div style={{ marginTop: 12, opacity: 0.7 }}>{loading ? 'LOADING...' : 'NO_DATA'}</div>
      )}
    </div>
  )
}
