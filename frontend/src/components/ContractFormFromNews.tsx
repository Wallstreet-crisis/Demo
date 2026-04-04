import { useNavigate } from 'react-router-dom'
import { type NewsInboxResponseItem } from '../api'

interface Props {
  newsItem: NewsInboxResponseItem
  onError: (msg: string) => void
}

export default function ContractFormFromNews({ newsItem, onError }: Props) {
  const navigate = useNavigate()

  const handleNavigate = () => {
    // 构建预填的自然语言描述
    const symbols = (newsItem.symbols || []).join(', ')
    const description = `基于新闻 "${newsItem.text.slice(0, 50)}..." 创建合约，涉及股票: ${symbols}，新闻变体ID: ${newsItem.variant_id}`
    
    // 跳转到合约页面，通过 state 传递预填内容
    navigate('/contracts', { 
      state: { 
        prefillDraft: description,
        newsReference: {
          variant_id: newsItem.variant_id,
          card_id: newsItem.card_id,
          text: newsItem.text,
          symbols: newsItem.symbols,
        }
      } 
    })
    onError('') // 清除错误（这里用于关闭面板）
  }

  return (
    <div style={{ display: 'grid', gap: 10 }}>
      <div style={{ fontSize: 13, color: '#666', lineHeight: 1.6 }}>
        点击下方按钮将跳转到<strong>智能合约中心</strong>，系统已预填基于该新闻的合约描述，你可以使用 AI 草拟功能快速生成合约。
      </div>
      <button 
        onClick={handleNavigate}
        style={{ padding: '12px', background: '#1890ff', color: '#fff', border: 'none', borderRadius: 8, fontWeight: 600, cursor: 'pointer' }}
      >
        前往智能合约中心
      </button>
    </div>
  )
}
