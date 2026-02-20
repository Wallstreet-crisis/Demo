import React from 'react';

interface CyberWidgetProps {
  title: string;
  children: React.ReactNode;
  subtitle?: string;
  titleActions?: React.ReactNode;
  actions?: React.ReactNode;
  height?: string | number;
  className?: string;
  style?: React.CSSProperties;
}

export default function CyberWidget({ 
  title, 
  children, 
  subtitle, 
  titleActions,
  actions, 
  height, 
  className = '', 
  style 
}: CyberWidgetProps) {
  return (
    <div 
      className={`cyber-card ${className}`} 
      style={{ 
        height: height || '100%', 
        display: 'flex', 
        flexDirection: 'column',
        border: '1px solid var(--terminal-border)',
        boxShadow: 'none',
        background: 'var(--panel-bg)',
        ...style 
      }}
    >
      <div style={{ 
        display: 'flex', 
        justifyContent: 'space-between', 
        alignItems: 'center',
        marginBottom: '10px',
        borderBottom: '1px solid var(--terminal-border)',
        paddingBottom: '6px',
        height: '24px'
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <div style={{ 
            fontSize: '13px', 
            fontWeight: '700', 
            color: '#fff',
            letterSpacing: '0.5px'
          }}>
            {title}
          </div>
          <div style={{ 
            fontSize: '10px', 
            textTransform: 'uppercase', 
            color: '#64748b',
            fontWeight: '500'
          }}>
            {subtitle}
          </div>
          {titleActions}
        </div>
        <div style={{ display: 'flex', gap: '6px' }}>
          {actions}
        </div>
      </div>
      
      <div style={{ flex: 1, overflow: 'auto' }}>
        {children}
      </div>

      <div style={{ 
        marginTop: '6px', 
        fontSize: '9px', 
        textAlign: 'right', 
        color: '#475569',
        letterSpacing: '0.5px',
        borderTop: '1px solid rgba(51, 65, 85, 0.3)',
        paddingTop: '4px'
      }}>
        LOG_LEVEL: TRACE // SYNC_OK
      </div>
    </div>
  );
}
