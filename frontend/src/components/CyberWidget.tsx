import React from 'react';

interface CyberWidgetProps {
  title: string;
  children: React.ReactNode;
  subtitle?: string;
  actions?: React.ReactNode;
  height?: string | number;
  className?: string;
  style?: React.CSSProperties;
}

export default function CyberWidget({ 
  title, 
  children, 
  subtitle, 
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
        ...style 
      }}
    >
      <div style={{ 
        display: 'flex', 
        justifyContent: 'space-between', 
        alignItems: 'flex-start',
        marginBottom: '12px',
        borderBottom: '1px solid rgba(0, 255, 65, 0.3)',
        paddingBottom: '8px'
      }}>
        <div>
          <div style={{ 
            fontSize: '10px', 
            textTransform: 'uppercase', 
            letterSpacing: '1px',
            opacity: 0.7 
          }}>
            {subtitle || 'WIDGET_ID: ' + title.toUpperCase().replace(/\s+/g, '_')}
          </div>
          <div style={{ 
            fontSize: '14px', 
            fontWeight: 'bold', 
            color: 'var(--terminal-text)',
            textShadow: '0 0 5px var(--terminal-glow)'
          }}>
            {title}
          </div>
        </div>
        <div style={{ display: 'flex', gap: '8px' }}>
          {actions}
        </div>
      </div>
      
      <div style={{ flex: 1, overflow: 'auto' }}>
        {children}
      </div>

      <div style={{ 
        marginTop: '8px', 
        fontSize: '8px', 
        textAlign: 'right', 
        opacity: 0.3,
        letterSpacing: '1px'
      }}>
        STATUS: RUNNING // SECTOR: {title.toUpperCase().slice(0, 3)}
      </div>
    </div>
  );
}
