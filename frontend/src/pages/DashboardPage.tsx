import MarketWidget from '../components/MarketWidget'
import TradeWidget from '../components/TradeWidget'
import NewsWidget from '../components/NewsWidget'
import ChatWidget from '../components/ChatWidget'
import AccountWidget from '../components/AccountWidget'
import HostingWidget from '../components/HostingWidget'
import ContractsWidget from '../components/ContractsWidget'

export default function DashboardPage() {
  return (
    <div style={{ 
      display: 'grid', 
      gridTemplateColumns: 'repeat(12, 1fr)', 
      gridAutoRows: 'minmax(280px, auto)',
      gap: '15px',
      paddingBottom: '20px'
    }}>
      {/* 第一行：核心行情 (8) + 资产概览 (4) */}
      <div style={{ gridColumn: 'span 8', gridRow: 'span 2' }}>
        <MarketWidget />
      </div>
      <div style={{ gridColumn: 'span 4' }}>
        <AccountWidget />
      </div>

      {/* 第二行：交易执行 (4) - 与行情并列 */}
      <div style={{ gridColumn: 'span 4' }}>
        <TradeWidget />
      </div>

      {/* 第三行：智能合约 (4) + AI 托管 (4) + 聊天通讯 (4) */}
      <div style={{ gridColumn: 'span 4' }}>
        <ContractsWidget />
      </div>
      <div style={{ gridColumn: 'span 4' }}>
        <HostingWidget />
      </div>
      <div style={{ gridColumn: 'span 4' }}>
        <ChatWidget />
      </div>

      {/* 第四行：情报中心 (12) */}
      <div style={{ gridColumn: 'span 12' }}>
        <NewsWidget />
      </div>
    </div>
  )
}
