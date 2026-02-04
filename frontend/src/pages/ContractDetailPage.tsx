import { useCallback, useEffect, useMemo, useState } from 'react'
import { useParams } from 'react-router-dom'
import { Api, ApiError, type ContractResponse } from '../api'
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
    if (!detail || !actorId) return false
    if (!detail.required_signers?.includes(actorId)) return false
    if (detail.signatures && detail.signatures[actorId]) return false
    return true
  }, [detail, actorId])

  const canJoin = useMemo(() => {
    if (!detail || !actorId) return false
    if (detail.participation_mode !== 'OPT_IN') return false
    if (!detail.invited_parties?.includes(actorId)) return false
    if (detail.parties?.includes(actorId)) return false
    return true
  }, [detail, actorId])

  const handleSign = async () => {
    if (!contractId || !actorId) return
    if (!canSign) return
    setActionLoading(true)
    try {
      await Api.contractSign(contractId, { signer: actorId })
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
    if (!canJoin) return
    setActionLoading(true)
    try {
      await Api.contractJoin(contractId, { joiner: actorId })
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

            <div style={{ display: 'flex', gap: 8, marginTop: 6 }}>
              <button
                className="cyber-button"
                onClick={handleSign}
                disabled={actionLoading || !canSign}
                style={{
                  fontSize: '11px',
                  padding: '4px 12px',
                  background: canSign ? 'var(--terminal-success)' : 'transparent',
                  borderColor: canSign ? 'var(--terminal-success)' : 'var(--terminal-border)',
                  color: canSign ? '#fff' : '#94a3b8',
                }}
              >
                签署
              </button>

              <button
                className="cyber-button"
                onClick={handleJoin}
                disabled={actionLoading || !canJoin}
                style={{
                  fontSize: '11px',
                  padding: '4px 12px',
                  background: canJoin ? 'var(--terminal-info)' : 'transparent',
                  borderColor: canJoin ? 'var(--terminal-info)' : 'var(--terminal-border)',
                  color: canJoin ? '#fff' : '#94a3b8',
                }}
              >
                响应加入
              </button>
            </div>
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
        </div>
      ) : (
        <div style={{ marginTop: 12, opacity: 0.7 }}>{loading ? 'LOADING...' : 'NO_DATA'}</div>
      )}
    </div>
  )
}
