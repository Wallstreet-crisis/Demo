import { useCallback, useEffect, useState } from 'react'
import { Api, ApiError, type HostingStatusResponse } from '../api'
import { useAppSession } from '../app/context'
import { useNotification } from '../app/NotificationContext'
import CyberWidget from './CyberWidget'

export default function HostingWidget() {
  const { playerId } = useAppSession()
  const { notify } = useNotification()
  const [status, setStatus] = useState<HostingStatusResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [actionLoading, setActionLoading] = useState(false)

  const fetchStatus = useCallback(async () => {
    if (!playerId) return
    try {
      const res = await Api.hostingStatus(`user:${playerId}`)
      setStatus(res)
    } catch (e) {
      console.error('Failed to fetch hosting status', e)
    } finally {
      setLoading(false)
    }
  }, [playerId])

  useEffect(() => {
    fetchStatus()
    const t = setInterval(fetchStatus, 5000)
    return () => clearInterval(t)
  }, [fetchStatus])

  const handleToggle = async () => {
    if (!playerId) return
    setActionLoading(true)
    try {
      if (status?.enabled) {
        await Api.hostingDisable(`user:${playerId}`)
        notify('success', 'AI_HOSTING_DISABLED')
      } else {
        await Api.hostingEnable(`user:${playerId}`)
        notify('success', 'AI_HOSTING_ENABLED')
      }
      await fetchStatus()
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : (e instanceof Error ? e.message : String(e))
      notify('error', `OP_FAILED: ${msg}`)
    } finally {
      setActionLoading(false)
    }
  }

  const getStatusColor = (s: string) => {
    switch (s) {
      case 'ON_IDLE': return '#52c41a'
      case 'WORKING': return '#1890ff'
      case 'OFF': return '#ff4d4f'
      default: return '#888'
    }
  }

  return (
    <CyberWidget 
      title="AI_CO-PILOT_SYSTEM" 
      subtitle="AUTONOMOUS_TRADING_CORE"
    >
      <div style={{ display: 'flex', flexDirection: 'column', gap: '15px' }}>
        <div style={{ 
          padding: '12px', 
          border: '1px solid #333', 
          background: 'rgba(255,255,255,0.02)',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center'
        }}>
          <div>
            <div style={{ fontSize: '9px', opacity: 0.5, marginBottom: '4px' }}>OPERATIONAL_STATUS</div>
            <div style={{ 
              fontSize: '16px', 
              fontWeight: 'bold', 
              color: getStatusColor(status?.status ?? 'OFF'),
              textShadow: status?.enabled ? `0 0 8px ${getStatusColor(status?.status ?? 'OFF')}` : 'none'
            }}>
              {loading && !status ? 'INITIALIZING...' : (status?.enabled ? 'ACTIVE' : 'IDLE')}
            </div>
          </div>
          
          <button
            onClick={handleToggle}
            disabled={actionLoading || loading}
            className="cyber-button"
            style={{ 
              fontSize: '10px', 
              padding: '4px 12px',
              background: status?.enabled ? 'rgba(255, 77, 79, 0.1)' : 'rgba(82, 196, 26, 0.1)',
              borderColor: status?.enabled ? '#ff4d4f' : '#52c41a',
              color: status?.enabled ? '#ff4d4f' : '#52c41a'
            }}
          >
            {actionLoading ? 'PROCESSING...' : (status?.enabled ? 'TERMINATE' : 'INITIALIZE')}
          </button>
        </div>

        <div style={{ fontSize: '10px', opacity: 0.7, lineHeight: 1.6 }}>
          <div>// LOG_STREAM</div>
          <div style={{ padding: '8px', background: '#000', border: '1px solid #222', minHeight: '60px', fontFamily: 'monospace' }}>
            {status?.enabled ? (
              <div style={{ color: 'var(--terminal-info)' }}>
                [OK] Neural network engaged.<br/>
                [OK] Monitoring market for {playerId}...<br/>
                [OK] Auto-liquidation rules active.
              </div>
            ) : (
              <div style={{ opacity: 0.4 }}>[SYS] Waiting for initialization signal...</div>
            )}
          </div>
        </div>

        <div style={{ fontSize: '9px', opacity: 0.4, fontStyle: 'italic' }}>
          * Caution: AI co-pilot operates with full account permissions.
        </div>
      </div>
    </CyberWidget>
  )
}
