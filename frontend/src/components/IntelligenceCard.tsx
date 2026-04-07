import type { LucideIcon } from 'lucide-react'
import { 
  Newspaper, 
  Flame, 
  ShieldAlert, 
  TrendingUp, 
  Globe, 
  Zap,
  Clock,
  Trash2,
  FileEdit,
  Share2,
  UserCheck,
  AlertCircle,
  Eye,
  Lock,
  ShoppingCart,
  ShieldCheck,
  Building2,
  Sword,
  Cpu,
  Fingerprint
} from 'lucide-react'
import { type NewsInboxResponseItem } from '../api'

export type CardStage = 'HELD' | 'FOR_SALE' | 'CIRCULATING' | 'EXPIRED' | 'PREVIEW'

export interface IntelligenceCardProps {
  item: NewsInboxResponseItem
  stage?: CardStage
  isSelected?: boolean
  onClick?: () => void
  onAction?: (action: 'propagate' | 'mutate' | 'contract' | 'suppress', item: NewsInboxResponseItem) => void
  className?: string
  showActions?: boolean
}

const KIND_CONFIG: Record<string, { color: string; icon: LucideIcon; label: string; description: string }> = {
  RUMOR: { color: '#ff4d4f', icon: ShieldAlert, label: '传闻', description: '来源不明的非官方消息，传播力强但可信度存疑。' },
  LEAK: { color: '#fa8c16', icon: Flame, label: '泄密', description: '内部流出的机密文件，极具杀伤力。' },
  ANALYST_REPORT: { color: '#1890ff', icon: TrendingUp, label: '研报', description: '机构发布的专业分析，对市场预期有显著引导。' },
  OMEN: { color: '#722ed1', icon: Zap, label: '征兆', description: '即将发生重大事件的前置信号。' },
  DISCLOSURE: { color: '#52c41a', icon: Newspaper, label: '公告', description: '企业或官方正式发布的声明。' },
  EARNINGS: { color: '#eb2f96', icon: TrendingUp, label: '财报', description: '反映财务状况的核心数据披露。' },
  MAJOR_EVENT: { color: '#faad14', icon: Flame, label: '要闻', description: '足以改变行业格局的重大突发事件。' },
  WORLD_EVENT: { color: '#13c2c2', icon: Globe, label: '全服', description: '影响所有参与者的宏观系统性事件。' },
  SYSTEM: { color: '#8c8c8c', icon: Clock, label: '系统', description: '系统发送的指令或通知。' },
}

const RARITY_CONFIG: Record<string, { 
  color: string; 
  label: string; 
  glow: string; 
  animation?: string;
  bgGradient: string;
  borderGlow: string;
}> = {
  COMMON: { 
    color: '#8c8c8c', 
    label: '基础', 
    glow: 'none',
    bgGradient: 'linear-gradient(135deg, rgba(40,40,40,0.9) 0%, rgba(20,20,20,0.9) 100%)',
    borderGlow: 'rgba(140, 140, 140, 0.2)'
  },
  UNCOMMON: { 
    color: '#52c41a', 
    label: '罕见', 
    glow: '0 0 10px rgba(82, 196, 26, 0.2)',
    bgGradient: 'linear-gradient(135deg, rgba(20,40,20,0.9) 0%, rgba(10,20,10,0.9) 100%)',
    borderGlow: 'rgba(82, 196, 26, 0.3)'
  },
  RARE: { 
    color: '#1890ff', 
    label: '珍稀', 
    glow: '0 0 15px rgba(24, 144, 255, 0.3)',
    bgGradient: 'linear-gradient(135deg, rgba(20,30,50,0.9) 0%, rgba(10,15,30,0.9) 100%)',
    borderGlow: 'rgba(24, 144, 255, 0.4)'
  },
  EPIC: { 
    color: '#722ed1', 
    label: '史诗', 
    glow: '0 0 20px rgba(114, 46, 209, 0.4)', 
    animation: 'rarity-pulse-epic 3s infinite',
    bgGradient: 'linear-gradient(135deg, rgba(40,20,60,0.9) 0%, rgba(20,10,30,0.9) 100%)',
    borderGlow: 'rgba(114, 46, 209, 0.6)'
  },
  LEGENDARY: { 
    color: '#faad14', 
    label: '传说', 
    glow: '0 0 25px rgba(250, 173, 20, 0.5)', 
    animation: 'rarity-pulse-legendary 2s infinite',
    bgGradient: 'linear-gradient(135deg, rgba(60,40,10,0.9) 0%, rgba(30,20,5,0.9) 100%)',
    borderGlow: 'rgba(250, 173, 20, 0.8)'
  },
}

const FACTION_CONFIG: Record<string, { icon: LucideIcon; label: string; color: string }> = {
  CORPORATE: { icon: Building2, label: '企业联盟', color: '#1890ff' },
  UNDERGROUND: { icon: Fingerprint, label: '地下阵线', color: '#ff4d4f' },
  GOVERNMENT: { icon: ShieldCheck, label: '联邦政府', color: '#52c41a' },
  NEUTRAL: { icon: Globe, label: '中立势力', color: '#8c8c8c' },
  MERCENARY: { icon: Sword, label: '雇佣兵团', color: '#faad14' },
  HACKER: { icon: Cpu, label: '黑客组织', color: '#722ed1' },
}

export default function IntelligenceCard({ 
  item, 
  stage = 'HELD', 
  isSelected, 
  onClick, 
  onAction,
  className = '',
  showActions = true
}: IntelligenceCardProps) {
  const kind = (item.kind || 'RUMOR').toUpperCase()
  const config = KIND_CONFIG[kind] || KIND_CONFIG.SYSTEM
  const Icon = config.icon

  const rarity = (item.rarity || 'COMMON').toUpperCase()
  const rarityConfig = RARITY_CONFIG[rarity] || RARITY_CONFIG.COMMON

  const faction = (item.faction || 'NEUTRAL').toUpperCase()
  const factionConfig = FACTION_CONFIG[faction] || FACTION_CONFIG.NEUTRAL
  const FactionIcon = factionConfig.icon

  // Calculate life cycle / expiration
  const createdAt = new Date(item.delivered_at || Date.now())
  const now = new Date()
  const ageHours = (now.getTime() - createdAt.getTime()) / (1000 * 60 * 60)
  
  // 模拟生命周期：大部分情报 6 小时后过期，全服事件 24 小时
  const ttl = kind === 'WORLD_EVENT' ? 24 : 6
  const isExpiringSoon = ageHours > (ttl - 1) && ageHours < ttl
  const isExpired = ageHours >= ttl || stage === 'EXPIRED'

  const getStageLabel = () => {
    switch (stage) {
      case 'HELD': return { text: '持有中', color: 'var(--terminal-info)', icon: Lock }
      case 'FOR_SALE': return { text: '待售中', color: 'var(--terminal-warn)', icon: ShoppingCart }
      case 'CIRCULATING': return { text: '流通中', color: 'var(--terminal-success)', icon: Globe }
      case 'EXPIRED': return { text: '已过期', color: '#555', icon: Trash2 }
      case 'PREVIEW': return { text: '原型预览', color: '#aaa', icon: Eye }
      default: return { text: '未知', color: '#555', icon: AlertCircle }
    }
  }

  const stageInfo = getStageLabel()
  const StageIcon = stageInfo.icon
  const truth = item.truth_payload as any

  const getImpactLabel = () => {
    if (!truth) return null
    const direction = truth.direction || (truth.impact === 'POSITIVE' ? 'UP' : truth.impact === 'NEGATIVE' ? 'DOWN' : 'STABLE')
    const strength = truth.intensity || truth.signal_strength || 1
    
    let color = '#8c8c8c'
    let text = '影响平衡'
    
    if (direction === 'UP') {
      color = 'var(--terminal-success)'
      text = strength > 0.7 ? '重大利好' : '偏向正面'
    } else if (direction === 'DOWN') {
      color = 'var(--terminal-error)'
      text = strength > 0.7 ? '重大利空' : '偏向负面'
    }
    
    return { text, color, strength }
  }

  const impactInfo = getImpactLabel()

  const getImpactIcon = () => {
    if (!truth) return null
    const direction = truth.direction || (truth.impact === 'POSITIVE' ? 'UP' : truth.impact === 'NEGATIVE' ? 'DOWN' : 'STABLE')
    if (direction === 'UP') return <TrendingUp size={14} color="var(--terminal-success)" />
    if (direction === 'DOWN') return <TrendingUp size={14} color="var(--terminal-error)" style={{ transform: 'rotate(90deg)' }} />
    return null
  }

  return (
    <div 
      onClick={onClick}
      className={`intelligence-card ${isSelected ? 'selected' : ''} ${isExpired ? 'expired' : ''} rarity-${rarity.toLowerCase()} ${className}`}
      style={{
        width: '260px',
        height: '380px',
        background: isExpired ? '#1a1a1a' : rarityConfig.bgGradient,
        borderWidth: '1px',
        borderStyle: 'solid',
        borderColor: isSelected ? config.color : `${rarityConfig.color}33`,
        borderRadius: '4px', // 尖锐边缘更有科技感
        display: 'flex',
        flexDirection: 'column',
        position: 'relative',
        cursor: 'pointer',
        overflow: 'hidden',
        transition: 'all 0.4s cubic-bezier(0.165, 0.84, 0.44, 1)',
        boxShadow: isSelected ? `0 0 30px ${config.color}33` : rarityConfig.glow,
        animation: !isExpired ? rarityConfig.animation : 'none',
        userSelect: 'none',
        backdropFilter: 'blur(10px)',
        margin: '10px'
      }}
    >
      {/* Background Tech Pattern */}
      {!isExpired && (
        <div style={{
          position: 'absolute',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          opacity: 0.05,
          pointerEvents: 'none',
          backgroundImage: `radial-gradient(${rarityConfig.color} 1px, transparent 1px)`,
          backgroundSize: '20px 20px',
          zIndex: 0
        }} />
      )}

      {/* Rarity Corner Accents */}
      {!isExpired && rarity !== 'COMMON' && (
        <>
          <div style={{ position: 'absolute', top: 0, left: 0, width: '20px', height: '20px', borderTop: `2px solid ${rarityConfig.color}`, borderLeft: `2px solid ${rarityConfig.color}`, zIndex: 2 }} />
          <div style={{ position: 'absolute', top: 0, right: 0, width: '20px', height: '20px', borderTop: `2px solid ${rarityConfig.color}`, borderRight: `2px solid ${rarityConfig.color}`, zIndex: 2 }} />
          <div style={{ position: 'absolute', bottom: 0, left: 0, width: '20px', height: '20px', borderBottom: `2px solid ${rarityConfig.color}`, borderLeft: `2px solid ${rarityConfig.color}`, zIndex: 2 }} />
          <div style={{ position: 'absolute', bottom: 0, right: 0, width: '20px', height: '20px', borderBottom: `2px solid ${rarityConfig.color}`, borderRight: `2px solid ${rarityConfig.color}`, zIndex: 2 }} />
        </>
      )}

      {/* Faction & Type Header */}
      <div style={{ 
        padding: '12px',
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        background: 'rgba(0,0,0,0.4)',
        borderBottom: `1px solid ${rarityConfig.color}22`,
        zIndex: 5
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          <FactionIcon size={14} color={factionConfig.color} />
          <span style={{ fontSize: '10px', fontWeight: '800', color: factionConfig.color, textTransform: 'uppercase', letterSpacing: '1px' }}>
            {factionConfig.label}
          </span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
          <Icon size={12} color={config.color} />
          <span style={{ fontSize: '10px', fontWeight: 'bold', color: config.color }}>{config.label}</span>
        </div>
      </div>

      {/* Main Image / Visual Area */}
      <div style={{ 
        height: '140px', 
        width: '100%', 
        background: '#000',
        position: 'relative',
        overflow: 'hidden',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center'
      }}>
        {/* Scanline Effect */}
        <div style={{
          position: 'absolute',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          background: 'linear-gradient(rgba(18, 16, 16, 0) 50%, rgba(0, 0, 0, 0.25) 50%), linear-gradient(90deg, rgba(255, 0, 0, 0.06), rgba(0, 255, 0, 0.02), rgba(0, 0, 255, 0.06))',
          backgroundSize: '100% 2px, 3px 100%',
          pointerEvents: 'none',
          zIndex: 2,
          opacity: 0.3
        }} />

        {truth?.image_uri ? (
          <img src={truth.image_uri} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover', opacity: isExpired ? 0.3 : 0.8 }} />
        ) : (
          <div style={{ opacity: 0.15, color: rarityConfig.color, transform: 'scale(1.5)' }}>
            <Icon size={64} />
          </div>
        )}

        {/* Impact Indicator */}
        {impactInfo && !isExpired && (
          <div style={{
            position: 'absolute',
            bottom: '10px',
            left: '10px',
            background: 'rgba(0,0,0,0.8)',
            padding: '4px 10px',
            borderRadius: '2px',
            fontSize: '10px',
            fontWeight: 'bold',
            color: impactInfo.color,
            border: `1px solid ${impactInfo.color}66`,
            backdropFilter: 'blur(4px)',
            display: 'flex',
            alignItems: 'center',
            gap: '6px',
            zIndex: 3
          }}>
            {getImpactIcon()}
            {impactInfo.text}
          </div>
        )}

        {/* Rarity Label Overlay */}
        {rarity !== 'COMMON' && (
          <div style={{
            position: 'absolute',
            top: '10px',
            right: '10px',
            background: rarityConfig.color,
            color: '#000',
            fontSize: '10px',
            fontWeight: '900',
            padding: '2px 8px',
            borderRadius: '2px',
            zIndex: 3,
            boxShadow: `0 0 10px ${rarityConfig.color}`
          }}>
            {rarityConfig.label}
          </div>
        )}
      </div>

      {/* Content Area */}
      <div style={{ 
        flex: 1, 
        padding: '16px', 
        display: 'flex', 
        flexDirection: 'column',
        gap: '12px',
        background: 'linear-gradient(180deg, rgba(0,0,0,0.2) 0%, transparent 100%)',
        position: 'relative'
      }}>
        {/* Symbol Tags */}
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
          {(item.symbols || []).map(s => (
            <span key={s} style={{ 
              fontSize: '10px', 
              color: 'var(--terminal-warn)', 
              background: 'rgba(250, 173, 20, 0.1)',
              padding: '2px 6px',
              border: '1px solid rgba(250, 173, 20, 0.2)',
              borderRadius: '2px',
              fontFamily: 'monospace'
            }}>${s}</span>
          ))}
        </div>

        <div style={{ 
          fontSize: '14px', 
          lineHeight: '1.6', 
          color: isExpired ? '#666' : '#eee',
          fontWeight: 400,
          overflow: 'hidden',
          display: '-webkit-box',
          WebkitLineClamp: 3,
          WebkitBoxOrient: 'vertical',
          fontFamily: 'system-ui, -apple-system, sans-serif'
        }}>
          {isExpired && <span style={{ color: '#ff4d4f', fontWeight: 'bold' }}>[ARCHIVED] </span>}
          {item.text}
        </div>

        {/* Footer info: time & status */}
        <div style={{ marginTop: 'auto', display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderTop: '1px solid rgba(255,255,255,0.05)', paddingTop: '10px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '4px', color: '#555', fontSize: '9px', fontFamily: 'monospace' }}>
            <Clock size={10} />
            <span>{createdAt.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}</span>
          </div>
          
          <div style={{ 
            display: 'flex',
            alignItems: 'center',
            gap: '4px',
            fontSize: '9px', 
            fontWeight: 'bold',
            color: stageInfo.color,
            textTransform: 'uppercase'
          }}>
            <StageIcon size={10} />
            {stageInfo.text}
          </div>
        </div>

        {/* Lifecycle Progress */}
        {!isExpired && stage !== 'PREVIEW' && (
          <div style={{ position: 'absolute', bottom: 0, left: 0, right: 0, height: '2px', background: 'rgba(255,255,255,0.05)' }}>
            <div style={{ 
              height: '100%', 
              width: `${Math.max(0, 100 - (ageHours / ttl) * 100)}%`, 
              background: isExpiringSoon ? 'var(--terminal-error)' : rarityConfig.color,
              boxShadow: isExpiringSoon ? '0 0 5px var(--terminal-error)' : 'none',
              transition: 'width 1s linear'
            }} />
          </div>
        )}
      </div>

      {/* Actions Overlay */}
      {showActions && !isExpired && (
        <div className="card-actions-overlay" style={{
          position: 'absolute',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          background: 'rgba(0,0,0,0.85)',
          display: isSelected ? 'flex' : 'none',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          gap: '20px',
          zIndex: 10,
          backdropFilter: 'blur(4px)',
          transition: 'all 0.3s'
        }}>
          <div style={{ fontSize: '12px', color: rarityConfig.color, fontWeight: 'bold', letterSpacing: '2px', textTransform: 'uppercase' }}>
            Execute Operation
          </div>
          <div style={{ display: 'flex', gap: '16px' }}>
            <ActionBtn icon={Share2} title="传播" onClick={() => onAction?.('propagate', item)} color="var(--terminal-success)" />
            <ActionBtn icon={FileEdit} title="篡改" onClick={() => onAction?.('mutate', item)} color="var(--terminal-warn)" />
            <ActionBtn icon={UserCheck} title="签约" onClick={() => onAction?.('contract', item)} color="var(--terminal-info)" />
            <ActionBtn icon={Trash2} title="抑制" onClick={() => onAction?.('suppress', item)} color="#ff4d4f" />
          </div>
          <button 
            onClick={(e) => { e.stopPropagation(); onClick?.(); }}
            style={{ marginTop: '10px', fontSize: '10px', color: '#444', background: 'none', border: 'none', cursor: 'pointer' }}
          >
            DISMISS
          </button>
        </div>
      )}

      {/* Warning highlight for expiring news */}
      {isExpiringSoon && (
        <div style={{
          position: 'absolute',
          top: '0',
          left: '0',
          width: '100%',
          height: '2px',
          background: '#ff4d4f',
          boxShadow: '0 0 10px #ff4d4f',
          zIndex: 10
        }} />
      )}

      <style>{`
        @keyframes rarity-pulse-epic {
          0% { box-shadow: 0 0 10px rgba(114, 46, 209, 0.2); }
          50% { box-shadow: 0 0 25px rgba(114, 46, 209, 0.5); }
          100% { box-shadow: 0 0 10px rgba(114, 46, 209, 0.2); }
        }
        @keyframes rarity-pulse-legendary {
          0% { box-shadow: 0 0 15px rgba(250, 173, 20, 0.3); border-color: rgba(250, 173, 20, 0.4); }
          50% { box-shadow: 0 0 35px rgba(250, 173, 20, 0.7); border-color: rgba(250, 173, 20, 0.8); }
          100% { box-shadow: 0 0 15px rgba(250, 173, 20, 0.3); border-color: rgba(250, 173, 20, 0.4); }
        }
        .intelligence-card:hover {
          transform: translateY(-8px) scale(1.02);
          box-shadow: 0 12px 24px rgba(0,0,0,0.5);
        }
        .intelligence-card:hover .card-actions-overlay {
          display: flex !important;
        }
        .intelligence-card.expired {
          filter: grayscale(0.5) contrast(0.8);
        }
      `}</style>
    </div>
  )
}

function ActionBtn({ icon: Icon, title, onClick, color }: { icon: any, title: string, onClick: () => void, color: string }) {
  return (
    <button 
      onClick={(e) => { e.stopPropagation(); onClick(); }}
      title={title}
      style={{
        background: 'rgba(255,255,255,0.1)',
        border: '1px solid rgba(255,255,255,0.2)',
        borderRadius: '50%',
        width: '32px',
        height: '32px',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        color: '#fff',
        cursor: 'pointer',
        transition: 'all 0.2s'
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.background = color
        e.currentTarget.style.borderColor = color
        e.currentTarget.style.transform = 'scale(1.2)'
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.background = 'rgba(255,255,255,0.1)'
        e.currentTarget.style.borderColor = 'rgba(255,255,255,0.2)'
        e.currentTarget.style.transform = 'scale(1)'
      }}
    >
      <Icon size={16} />
    </button>
  )
}


