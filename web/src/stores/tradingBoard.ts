import { computed, ref } from 'vue'
import { defineStore } from 'pinia'

import { mockBoardColumns, mockTradingItems } from '../data/mockTrading'
import type { TradingItem, TradingStatus } from '../domain/trading'
import { createSyncState, summarizeSync } from '../sync/state'

export const useTradingBoardStore = defineStore('tradingBoard', () => {
  const columns = ref(mockBoardColumns.map((column) => ({ ...column })))
  const items = ref(mockTradingItems.map((item) => ({ ...item })))
  const syncState = ref(createSyncState())

  const itemsByStatus = computed<Record<TradingStatus, TradingItem[]>>(() => ({
    registered: items.value.filter((item) => item.status === 'registered'),
    buyWatching: items.value.filter((item) => item.status === 'buyWatching'),
    buyOrdering: items.value.filter((item) => item.status === 'buyOrdering'),
    holding: items.value.filter((item) => item.status === 'holding'),
    sellOrdering: items.value.filter((item) => item.status === 'sellOrdering'),
    closed: items.value.filter((item) => item.status === 'closed'),
  }))

  const totalItems = computed(() => items.value.length)
  const syncClock = ref(Date.now())
  const syncSummary = computed(() => summarizeSync(syncState.value, syncClock.value))
  const refreshSyncClock = () => {
    syncClock.value = Date.now()
  }

  return { columns, items, itemsByStatus, totalItems, syncState, syncSummary, refreshSyncClock }
})
