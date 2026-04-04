import React from 'react'
import { type NewsInboxResponseItem } from '../api'

interface NewsCardProps {
  item: NewsInboxResponseItem
  onAction: (action: 'propagate' | 'mutate' | 'contract' | 'suppress', item: NewsInboxResponseItem) => void
  isSelected?: boolean
  onClick?: () => void
}

const KIND_COLORS: Record<string, string> = {
  RUMOR: '#fff1f0', // red-1
  LEAK: '#fff7e6', // orange-1
  ANALYST_REPORT: '#e6f7ff', // blue-1
  OMEN: '#f9f0ff', // purple-1
  DISCLOSURE: '#f6ffed', // green-1
  EARNINGS: '#fcffe6', // lime-1
  MAJOR_EVENT: '#fffbe6', // gold-1
  WORLD_EVENT: '#feffe6', // yellow-1
}

const KIND_BORDER_COLORS: Record<string, string> = {
  RUMOR: '#ffa39e',
  LEAK: '#ffd591',
  ANALYST_REPORT: '#91d5ff',
  OMEN: '#d3adf7',
  DISCLOSURE: '#b7eb8f',
  EARNINGS: '#eaff8f',
  MAJOR_EVENT: '#ffe58f',
  WORLD_EVENT: '#fffb8f',
}

const KIND_TEXT_COLORS: Record<string, string> = {
  RUMOR: '#cf1322',
  LEAK: '#d46b08',
  ANALYST_REPORT: '#096dd9',
  OMEN: '#531dab',
  DISCLOSURE: '#389e0d',
  EARNINGS: '#7cb305',
  MAJOR_EVENT: '#d48806',
  WORLD_EVENT: '#d4b106',
}

export default function NewsCard({ item, onAction, isSelected, onClick }: NewsCardProps) {
  const kind = (item.kind || 'RUMOR').toUpperCase()
  const bgColor = KIND_COLORS[kind] || '#fff'
  const borderColor = isSelected ? 'var(--terminal-info)' : (KIND_BORDER_COLORS[kind] || '#eee')
  const textColor = KIND_TEXT_COLORS[kind] || '#666'

  const formatTime = (s: string) => {
    if (!s) return ''
    const d = new Date(s)
    return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
  }

  const getImpactIcon = () => {
    const payload = item.truth_payload as any
    if (!payload) return null
    if (payload.direction === 'UP' || payload.impact === 'POSITIVE') return <span style={{ color: 'var(--terminal-success)' }}>▲</span>
    if (payload.direction === 'DOWN' || payload.impact === 'NEGATIVE') return <span style={{ color: 'var(--terminal-error)' }}>▼</span>
    return null
  }

  return (
    <div 
      onClick={onClick}
      className={`cyber-card ${isSelected ? 'active' : ''}`}
      style={{
        padding: '12px',
        background: bgColor,
        border: isSelected ? '2px solid var(--terminal-info)' : `1px solid ${borderColor}`,
        borderRadius: '8px',
        cursor: 'pointer',
        transition: 'all 0.2s ease',
        position: 'relative',
        display: 'flex',
        flexDirection: 'column',
        gap: '8px',
        boxShadow: isSelected ? '0 0 15px rgba(0, 140, 255, 0.4)' : '0 2px 5px rgba(0,0,0,0.1)',
        minWidth: '240px',
        opacity: isSelected ? 1 : 0.9,
        transform: isSelected ? 'scale(1.02)' : 'none',
        zIndex: isSelected ? 10 : 1
      }}
      onMouseEnter={(e) => {
        if (!isSelected) {
          e.currentTarget.style.opacity = '1'
          e.currentTarget.style.transform = 'translateY(-4px)'
          e.currentTarget.style.boxShadow = '0 5px 15px rgba(0,0,0,0.2)'
        }
      }}
      onMouseLeave={(e) => {
        if (!isSelected) {
          e.currentTarget.style.opacity = '0.9'
          e.currentTarget.style.transform = 'translateY(0)'
          e.currentTarget.style.boxShadow = '0 2px 5px rgba(0,0,0,0.1)'
        }
      }}
    >
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          <span style={{ 
            fontSize: '10px', 
            fontWeight: 'bold', 
            color: textColor, 
            background: 'rgba(255,255,255,0.8)', 
            padding: '2px 6px', 
            borderRadius: '4px',
            border: `1px solid ${borderColor}`,
            letterSpacing: '0.5px'
          }}>
            {kind}
          </span>
          {getImpactIcon()}
        </div>
        <span style={{ fontSize: '10px', color: '#888', fontFamily: 'monospace' }}>
          {formatTime(item.delivered_at)}
        </span>
      </div>

      <div style={{ 
        fontSize: '14px', 
        lineHeight: '1.4', 
        color: '#222', 
        fontWeight: 500,
        wordBreak: 'break-word',
        minHeight: '40px'
      }}>
        {item.text}
      </div>

      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px' }}>
        {(item.symbols || []).map(s => (
          <span key={s} style={{ fontSize: '10px', background: '#eee', padding: '1px 4px', borderRadius: '3px', color: '#666' }}>
            ${s}
          </span>
        ))}
        {(item.tags || []).map(t => (
          <span key={t} style={{ fontSize: '10px', background: '#f0f0f0', padding: '1px 4px', borderRadius: '3px', color: '#999' }}>
            #{t}
          </span>
        ))}
      </div>

      <div style={{ 
        marginTop: 'auto', 
        paddingTop: '8px', 
        borderTop: '1px solid rgba(0,0,0,0.05)',
        display: 'flex',
        justifyContent: 'flex-end',
        gap: '8px'
      }}>
        <button 
          title="传播宣传"
          className="cyber-button mini"
          onClick={(e) => { e.stopPropagation(); onAction('propagate', item); }}
          style={{ padding: '2px 6px', fontSize: '10px' }}
        >
          📣
        </button>
        <button 
          title="篡改伪造"
          className="cyber-button mini"
          onClick={(e) => { e.stopPropagation(); onAction('mutate', item); }}
          style={{ padding: '2px 6px', fontSize: '10px', background: 'var(--terminal-warn)' }}
        >
          🖋️
        </button>
        <button 
          title="引用签约"
          className="cyber-button mini"
          onClick={(e) => { e.stopPropagation(); onAction('contract', item); }}
          style={{ padding: '2px 6px', fontSize: '10px', background: 'var(--terminal-info)' }}
        >
          🤝
        </button>
        <button 
          title="抑制抹除"
          className="cyber-button mini"
          onClick={(e) => { e.stopPropagation(); onAction('suppress', item); }}
          style={{ padding: '2px 6px', fontSize: '10px', background: '#ff4d4f' }}
        >
          🚫
        </button>
      </div>
    </div>
  )
}
