import { type NewsInboxResponseItem } from '../api'
import IntelligenceCard from './IntelligenceCard'

interface NewsCardProps {
  item: NewsInboxResponseItem
  onAction: (action: 'propagate' | 'mutate' | 'contract' | 'suppress', item: NewsInboxResponseItem) => void
  isSelected?: boolean
  onClick?: () => void
}

export default function NewsCard({ item, onAction, isSelected, onClick }: NewsCardProps) {
  return (
    <IntelligenceCard
      item={item}
      isSelected={isSelected}
      onClick={onClick}
      onAction={onAction}
    />
  )
}
