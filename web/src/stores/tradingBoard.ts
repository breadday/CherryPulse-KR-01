import { computed, ref } from 'vue'
import { defineStore } from 'pinia'

import { mockBoardColumns, mockTradingItems } from '../data/mockTrading'
import type { TradingItem, TradingStatus } from '../domain/trading'

export const useTradingBoardStore = defineStore('tradingBoard', () => {
  const columns = ref(mockBoardColumns.map((column) => ({ ...column })))
  const items = ref(mockTradingItems.map((item) => ({ ...item })))

  const itemsByStatus = computed<Record<TradingStatus, TradingItem[]>>(() => ({
    registered: items.value.filter((item) => item.status === 'registered'),
    buyWatching: items.value.filter((item) => item.status === 'buyWatching'),
    buyOrdering: items.value.filter((item) => item.status === 'buyOrdering'),
    holding: items.value.filter((item) => item.status === 'holding'),
    sellOrdering: items.value.filter((item) => item.status === 'sellOrdering'),
    closed: items.value.filter((item) => item.status === 'closed'),
  }))

  const totalItems = computed(() => items.value.length)

  return { columns, items, itemsByStatus, totalItems }
})
