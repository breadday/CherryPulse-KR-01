export const tradingStatuses = [
  'registered',
  'buyWatching',
  'buyOrdering',
  'holding',
  'sellOrdering',
  'closed',
] as const

export type TradingStatus = (typeof tradingStatuses)[number]

export interface BoardColumn {
  id: TradingStatus
  title: string
  description: string
}

export interface TradingItem {
  id: string
  symbol: string
  name: string
  market: 'KOSPI' | 'KOSDAQ'
  status: TradingStatus
  buyPattern: string
  sellPattern: string
  lastPrice: string
  quantity: number
  statusDetail: string
  updatedAt: string
  warning?: string
}
