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
  ShoppingCart
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

const RARITY_CONFIG: Record<string, { color: string; label: string; glow: string }> = {
  COMMON: { color: '#8c8c8c', label: '基础', glow: 'none' },
  UNCOMMON: { color: '#52c41a', label: '罕见', glow: '0 0 10px rgba(82, 196, 26, 0.2)' },
  RARE: { color: '#1890ff', label: '珍稀', glow: '0 0 15px rgba(24, 144, 255, 0.3)' },
  EPIC: { color: '#722ed1', label: '史诗', glow: '0 0 20px rgba(114, 46, 209, 0.4)' },
  LEGENDARY: { color: '#faad14', label: '传说', glow: '0 0 25px rgba(250, 173, 20, 0.5)' },
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
        width: '240px',
        height: '340px',
        background: isExpired ? '#1a1a1a' : '#262626',
        border: isSelected ? `2px solid ${config.color}` : `1px solid ${rarityConfig.color}44`,
        borderRadius: '12px',
        display: 'flex',
        flexDirection: 'column',
        position: 'relative',
        cursor: 'pointer',
        overflow: 'hidden',
        transition: 'all 0.3s cubic-bezier(0.25, 0.8, 0.25, 1)',
        boxShadow: isSelected ? `0 0 20px ${config.color}44` : rarityConfig.glow,
        userSelect: 'none'
      }}
    >
      {/* Rarity Border Highlight */}
      <div style={{
        position: 'absolute',
        top: 0,
        left: 0,
        width: '100%',
        height: '4px',
        background: rarityConfig.color,
        opacity: isExpired ? 0.3 : 1
      }} />

      {/* Card Header: Kind & Stage */}
      <div style={{ 
        padding: '12px 12px 8px 12px', 
        display: 'flex', 
        justifyContent: 'space-between', 
        alignItems: 'center',
        background: `linear-gradient(180deg, ${rarityConfig.color}11 0%, transparent 100%)`,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
          <Icon size={14} color={config.color} />
          <span style={{ fontSize: '10px', fontWeight: 'bold', color: config.color, letterSpacing: '1px' }}>
            {config.label}
          </span>
          {getImpactIcon()}
        </div>
        <div style={{ 
          display: 'flex',
          alignItems: 'center',
          gap: '4px',
          fontSize: '9px', 
          padding: '2px 6px', 
          borderRadius: '10px', 
          background: 'rgba(0,0,0,0.3)', 
          color: stageInfo.color,
          border: `1px solid ${stageInfo.color}44`
        }}>
          <StageIcon size={10} />
          {stageInfo.text}
        </div>
      </div>

      {/* Rarity Label Overlay */}
      <div style={{
        position: 'absolute',
        top: '40px',
        right: '-20px',
        background: rarityConfig.color,
        color: '#000',
        fontSize: '9px',
        fontWeight: 'bold',
        padding: '2px 25px',
        transform: 'rotate(45deg)',
        boxShadow: '0 2px 4px rgba(0,0,0,0.3)',
        zIndex: 10,
        display: rarity === 'COMMON' ? 'none' : 'block'
      }}>
        {rarityConfig.label}
      </div>

      {/* Image Placeholder */}
      <div style={{ 
        height: '120px', 
        width: '100%', 
        background: '#141414',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        position: 'relative',
        overflow: 'hidden',
        borderBottom: '1px solid #333'
      }}>
        {truth?.image_uri ? (
          <img src={truth.image_uri} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
        ) : (
          <div style={{ opacity: 0.1, color: config.color }}>
            <Icon size={48} />
          </div>
        )}
        
        {/* Metadata Overlay: Impact Direction */}
        {impactInfo && !isExpired && (
          <div style={{
            position: 'absolute',
            top: '8px',
            left: '8px',
            background: 'rgba(0,0,0,0.6)',
            padding: '2px 8px',
            borderRadius: '4px',
            fontSize: '9px',
            color: impactInfo.color,
            border: `1px solid ${impactInfo.color}44`,
            backdropFilter: 'blur(2px)'
          }}>
            {impactInfo.text}
          </div>
        )}

        {/* Overlays for metadata like impacted symbols */}
        <div style={{ 
          position: 'absolute', 
          bottom: '6px', 
          right: '6px', 
          display: 'flex', 
          gap: '4px' 
        }}>
          {(item.symbols || []).map(s => (
            <div key={s} style={{ 
              background: 'rgba(0,0,0,0.7)', 
              color: 'var(--terminal-warn)', 
              fontSize: '10px', 
              padding: '2px 6px', 
              borderRadius: '4px',
              border: '1px solid var(--terminal-warn)44',
              backdropFilter: 'blur(2px)'
            }}>
              ${s}
            </div>
          ))}
        </div>
      </div>

      {/* Card Body: Content */}
      <div style={{ 
        flex: 1, 
        padding: '12px', 
        display: 'flex', 
        flexDirection: 'column',
        gap: '8px',
        overflow: 'hidden'
      }}>
        <div style={{ 
          fontSize: '13px', 
          lineHeight: '1.5', 
          color: isExpired ? '#888' : '#e0e0e0',
          display: '-webkit-box',
          WebkitLineClamp: 4,
          WebkitBoxOrient: 'vertical',
          overflow: 'hidden',
          fontWeight: 400
        }}>
          {isExpired && <span style={{ color: '#ff4d4f', fontWeight: 'bold', marginRight: '4px' }}>[已过期]</span>}
          {item.text}
        </div>
        
        {/* Progress bar for lifecycle */}
        {!isExpired && stage !== 'PREVIEW' && (
          <div style={{ marginTop: 'auto', marginBottom: '4px' }}>
            <div style={{ height: '2px', width: '100%', background: '#333', borderRadius: '1px', overflow: 'hidden' }}>
              <div style={{ 
                height: '100%', 
                width: `${Math.max(0, 100 - (ageHours / ttl) * 100)}%`, 
                background: isExpiringSoon ? 'var(--terminal-error)' : 'var(--terminal-info)',
                transition: 'width 0.3s'
              }} />
            </div>
          </div>
        )}

        {/* Footer info: time & author */}
        <div style={{ marginTop: stage === 'PREVIEW' ? 'auto' : '0', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '4px', color: '#666', fontSize: '10px' }}>
            <Clock size={10} />
            <span>{createdAt.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '4px', color: '#666', fontSize: '10px' }}>
            <UserCheck size={10} />
            <span style={{ maxWidth: '60px', overflow: 'hidden', textOverflow: 'ellipsis' }}>{item.from_actor_id || '未知'}</span>
          </div>
        </div>
      </div>

      {/* Card Actions (Hover or Selected) */}
      {showActions && !isExpired && (
        <div className="card-actions-overlay" style={{
          position: 'absolute',
          bottom: '0',
          left: '0',
          right: '0',
          background: 'linear-gradient(to top, rgba(0,0,0,0.9) 0%, transparent 100%)',
          padding: '10px',
          display: isSelected ? 'flex' : 'none',
          justifyContent: 'center',
          gap: '12px',
          zIndex: 5
        }}>
          <ActionBtn icon={Share2} title="传播" onClick={() => onAction?.('propagate', item)} color="var(--terminal-success)" />
          <ActionBtn icon={FileEdit} title="篡改" onClick={() => onAction?.('mutate', item)} color="var(--terminal-warn)" />
          <ActionBtn icon={UserCheck} title="签约" onClick={() => onAction?.('contract', item)} color="var(--terminal-info)" />
          <ActionBtn icon={Trash2} title="抑制" onClick={() => onAction?.('suppress', item)} color="#ff4d4f" />
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


