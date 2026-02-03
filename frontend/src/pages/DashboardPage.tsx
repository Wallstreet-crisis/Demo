import MarketWatchWidget from '../components/MarketWatchWidget'
import MarketWidget from '../components/MarketWidget'
import TradeWidget from '../components/TradeWidget'
import NewsWidget from '../components/NewsWidget'
import ChatWidget from '../components/ChatWidget'
import AccountWidget from '../components/AccountWidget'
import HostingWidget from '../components/HostingWidget'
import ContractsWidget from '../components/ContractsWidget'
import PropagandaWidget from '../components/PropagandaWidget'

export default function DashboardPage() {
  return (
    <div style={{ 
      display: 'grid', 
      gridTemplateColumns: 'repeat(12, 1fr)', 
      gridAutoRows: 'minmax(300px, auto)',
      gap: '15px',
      paddingBottom: '20px'
    }}>
      {/* 左侧：行情列表 (3列) */}
      <div style={{ gridColumn: 'span 3', gridRow: 'span 3' }}>
        <MarketWatchWidget />
      </div>

      {/* 中间/右侧：详情与交易 (9列) */}
      <div style={{ gridColumn: 'span 6', gridRow: 'span 2' }}>
        <MarketWidget />
      </div>
      <div style={{ gridColumn: 'span 3' }}>
        <AccountWidget />
      </div>
      <div style={{ gridColumn: 'span 3' }}>
        <TradeWidget />
      </div>

      {/* 下方功能块平铺 */}
      <div style={{ gridColumn: 'span 3' }}>
        <PropagandaWidget />
      </div>
      <div style={{ gridColumn: 'span 3' }}>
        <ContractsWidget />
      </div>
      <div style={{ gridColumn: 'span 3' }}>
        <HostingWidget />
      </div>

      {/* 情报与通讯 (占据下方较宽位置) */}
      <div style={{ gridColumn: 'span 6', gridRow: 'span 2' }}>
        <NewsWidget />
      </div>
      <div style={{ gridColumn: 'span 3', gridRow: 'span 2' }}>
        <ChatWidget />
      </div>
    </div>
  )
}
