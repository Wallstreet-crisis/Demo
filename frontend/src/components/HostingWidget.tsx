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
      <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
        <div style={{ 
          padding: '12px', 
          border: '1px solid var(--terminal-border)', 
          background: 'rgba(255,255,255,0.02)',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          borderRadius: '2px'
        }}>
          <div>
            <div style={{ fontSize: '10px', color: '#64748b', marginBottom: '4px' }}>OPERATIONAL_STATUS</div>
            <div style={{ 
              fontSize: '16px', 
              fontWeight: 'bold', 
              color: getStatusColor(status?.status ?? 'OFF'),
            }}>
              {loading && !status ? 'INITIALIZING...' : (status?.enabled ? 'ACTIVE_RUNNING' : 'SYSTEM_IDLE')}
            </div>
          </div>
          
          <button
            onClick={handleToggle}
            disabled={actionLoading || loading}
            className="cyber-button"
            style={{ 
              fontSize: '11px', 
              padding: '6px 16px',
              background: status?.enabled ? 'rgba(239, 68, 68, 0.1)' : 'rgba(16, 185, 129, 0.1)',
              borderColor: status?.enabled ? 'var(--terminal-error)' : 'var(--terminal-success)',
              color: status?.enabled ? 'var(--terminal-error)' : 'var(--terminal-success)',
              fontWeight: '600'
            }}
          >
            {actionLoading ? 'PROCESSING...' : (status?.enabled ? 'TERMINATE' : 'INITIALIZE')}
          </button>
        </div>

        <div style={{ fontSize: '11px', fontWeight: '600', color: '#94a3b8' }}>// SYSTEM_LOG_STREAM</div>
        <div style={{ 
          padding: '10px', 
          background: 'var(--terminal-bg)', 
          border: '1px solid var(--terminal-border)', 
          minHeight: '80px', 
          fontFamily: 'monospace',
          fontSize: '11px',
          borderRadius: '2px',
          lineHeight: '1.4'
        }}>
          {status?.enabled ? (
            <div style={{ color: 'var(--terminal-info)' }}>
              <span style={{ opacity: 0.5 }}>[{new Date().toLocaleTimeString()}]</span> NEURAL_NET_ENGAGED<br/>
              <span style={{ opacity: 0.5 }}>[{new Date().toLocaleTimeString()}]</span> MONITORING_MARKET: {playerId}<br/>
              <span style={{ opacity: 0.5 }}>[{new Date().toLocaleTimeString()}]</span> RISK_MITIGATION_ACTIVE
            </div>
          ) : (
            <div style={{ opacity: 0.4 }}>[SYS] WAITING_FOR_SIGNAL...</div>
          )}
        </div>

        <div style={{ fontSize: '10px', color: '#64748b', fontStyle: 'italic' }}>
          * AUTH_NOTICE: AI CO-PILOT HAS FULL CLEARANCE.
        </div>
      </div>
    </CyberWidget>
  )
}
