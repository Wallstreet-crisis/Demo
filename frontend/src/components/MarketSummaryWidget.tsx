import { useEffect, useState, useCallback } from 'react'
import { Api, type MarketSummaryResponse } from '../api'
import CyberWidget from './CyberWidget'

export default function MarketSummaryWidget({ isFocused }: { isFocused?: boolean }) {
  void isFocused
  const [summary, setSummary] = useState<MarketSummaryResponse | null>(null)
  const [loading, setLoading] = useState(true)

  const refresh = useCallback(async () => {
    try {
      const s = await Api.marketSummary()
      setSummary(s)
    } catch (e) {
      console.error('Failed to fetch market summary', e)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    refresh()
    const t = setInterval(refresh, 5000)
    return () => clearInterval(t)
  }, [refresh])

  if (loading && !summary) {
    return (
      <CyberWidget title="MARKET_SUMMARY" subtitle="AGGREGATED_DATA">
        <div style={{ textAlign: 'center', padding: '20px', opacity: 0.5 }}>SCANNING_NETWORK...</div>
      </CyberWidget>
    )
  }

  return (
    <CyberWidget 
      title="MARKET_SUMMARY" 
      subtitle="SYSTEM_WIDE_STATS"
      actions={<button className="cyber-button" style={{ fontSize: '10px', height: '20px' }} onClick={refresh}>REFRESH</button>}
    >
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px', marginBottom: '15px' }}>
        <div style={{ padding: '10px', background: 'rgba(255,255,255,0.02)', border: '1px solid var(--terminal-border)', borderRadius: '4px' }}>
          <div style={{ fontSize: '9px', color: '#64748b' }}>TOTAL_TURNOVER</div>
          <div style={{ fontSize: '16px', fontWeight: 'bold', fontFamily: 'monospace', color: 'var(--terminal-info)' }}>
            ${summary?.total_turnover.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
          </div>
        </div>
        <div style={{ padding: '10px', background: 'rgba(255,255,255,0.02)', border: '1px solid var(--terminal-border)', borderRadius: '4px' }}>
          <div style={{ fontSize: '9px', color: '#64748b' }}>TOTAL_TRADES</div>
          <div style={{ fontSize: '16px', fontWeight: 'bold', fontFamily: 'monospace' }}>
            {summary?.total_trades}
          </div>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '15px' }}>
        <div>
          <div style={{ fontSize: '10px', color: 'var(--terminal-success)', marginBottom: '5px', fontWeight: 'bold' }}>TOP_GAINERS</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
            {(isFocused ? summary?.top_gainers : summary?.top_gainers.slice(0, 3))?.map(g => (
              <div key={g.symbol} style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', fontFamily: 'monospace' }}>
                <span>{g.symbol}</span>
                <span style={{ color: 'var(--terminal-success)' }}>+{(g.change_pct * 100).toFixed(2)}%</span>
              </div>
            ))}
            {summary?.top_gainers.length === 0 && <div style={{ fontSize: '10px', opacity: 0.3 }}>N/A</div>}
          </div>
        </div>
        <div>
          <div style={{ fontSize: '10px', color: 'var(--terminal-error)', marginBottom: '5px', fontWeight: 'bold' }}>TOP_LOSERS</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
            {(isFocused ? summary?.top_losers : summary?.top_losers.slice(0, 3))?.map(l => (
              <div key={l.symbol} style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', fontFamily: 'monospace' }}>
                <span>{l.symbol}</span>
                <span style={{ color: 'var(--terminal-error)' }}>{(l.change_pct * 100).toFixed(2)}%</span>
              </div>
            ))}
            {summary?.top_losers.length === 0 && <div style={{ fontSize: '10px', opacity: 0.3 }}>N/A</div>}
          </div>
        </div>
      </div>

      {isFocused && (
        <div style={{ marginTop: '15px' }}>
          <div style={{ fontSize: '10px', color: '#64748b', marginBottom: '5px', fontWeight: 'bold' }}>MOST_ACTIVE_BY_TURNOVER</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
            {summary?.active_symbols.map(s => (
              <div key={s.symbol} style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', fontFamily: 'monospace', padding: '2px 0', borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
                <span>{s.symbol}</span>
                <span style={{ color: '#cbd5e1' }}>${s.turnover.toLocaleString(undefined, { maximumFractionDigits: 0 })}</span>
              </div>
            ))}
          </div>
        </div>
      )}
      
      <div style={{ marginTop: '10px', fontSize: '8px', color: '#475569', textAlign: 'right' }}>
        REFRESHED_AT: {summary ? new Date(summary.refreshed_at).toLocaleTimeString() : '--'}
      </div>
    </CyberWidget>
  )
}
