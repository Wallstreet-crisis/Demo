import { useCallback, useEffect, useState } from 'react'
import { Api, ApiError, type HostingStatusResponse } from '../api'
import { useAppSession } from '../app/context'
import { useNotification } from '../app/NotificationContext'

export default function HostingPage() {
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
        notify('success', 'AI 托管已关闭')
      } else {
        await Api.hostingEnable(`user:${playerId}`)
        notify('success', 'AI 托管已开启')
      }
      await fetchStatus()
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : (e instanceof Error ? e.message : String(e))
      notify('error', `操作失败: ${msg}`)
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
    <div style={{ maxWidth: 600, margin: '0 auto' }}>
      <div className="card" style={{ textAlign: 'left' }}>
        <h2 style={{ marginTop: 0, borderBottom: '1px solid #eee', paddingBottom: 10 }}>AI 托管中心</h2>
        
        <div style={{ margin: '20px 0', padding: 20, background: '#fafafa', borderRadius: 12, border: '1px solid #f0f0f0' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <div>
              <div style={{ fontSize: 14, color: '#888', marginBottom: 4 }}>当前状态</div>
              <div style={{ fontSize: 24, fontWeight: 700, color: getStatusColor(status?.status ?? 'UNKNOWN') }}>
                {loading && !status ? '加载中...' : (status?.enabled ? '托管中' : '未开启')}
              </div>
              <div style={{ fontSize: 12, color: '#999', marginTop: 4 }}>
                {status?.status && `运行详情: ${status.status}`}
              </div>
            </div>
            
            <button
              onClick={handleToggle}
              disabled={actionLoading || loading}
              style={{
                padding: '12px 24px',
                borderRadius: 30,
                border: 'none',
                background: status?.enabled ? '#ff4d4f' : '#52c41a',
                color: '#fff',
                fontSize: 16,
                fontWeight: 600,
                cursor: 'pointer',
                boxShadow: '0 4px 10px rgba(0,0,0,0.1)',
                transition: 'transform 0.1s'
              }}
              onMouseDown={e => e.currentTarget.style.transform = 'scale(0.95)'}
              onMouseUp={e => e.currentTarget.style.transform = 'scale(1)'}
            >
              {actionLoading ? '处理中...' : (status?.enabled ? '停止托管' : '开启 AI 代理')}
            </button>
          </div>
        </div>

        <div style={{ padding: '0 10px' }}>
          <h4 style={{ color: '#666' }}>功能说明</h4>
          <ul style={{ fontSize: 14, color: '#888', lineHeight: 1.6, paddingLeft: 20 }}>
            <li>开启托管后，AI 将自动分析市场新闻。</li>
            <li>AI 会根据您的资产状况尝试进行套利或趋势交易。</li>
            <li>系统支持 24/7 全天候运行，即使您关闭网页也不会中断。</li>
            <li>请注意：托管交易涉及风险，建议账户预留足够现金。</li>
          </ul>
        </div>

        <details style={{ marginTop: 20, color: '#ccc' }}>
          <summary style={{ cursor: 'pointer', fontSize: 12 }}>Raw Status</summary>
          <pre style={{ fontSize: 11, background: '#f8f8f8', padding: 10, borderRadius: 4 }}>
            {JSON.stringify(status, null, 2)}
          </pre>
        </details>
      </div>
    </div>
  )
}
