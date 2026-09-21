import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it } from 'vitest'

import { useTradingBoardStore } from '../stores/tradingBoard'

describe('trading board store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('groups every mock trading item into its execution-state column', () => {
    const store = useTradingBoardStore()

    expect(store.columns).toHaveLength(6)
    expect(store.totalItems).toBe(6)
    expect(store.itemsByStatus.registered).toHaveLength(1)
    expect(store.itemsByStatus.buyWatching).toHaveLength(1)
    expect(store.itemsByStatus.buyOrdering).toHaveLength(1)
    expect(store.itemsByStatus.holding).toHaveLength(1)
    expect(store.itemsByStatus.sellOrdering).toHaveLength(1)
    expect(store.itemsByStatus.closed).toHaveLength(1)
  })

  it('does not leak item mutations into a new Pinia instance', () => {
    const firstStore = useTradingBoardStore()
    const firstItem = firstStore.items[0]

    expect(firstItem).toBeDefined()
    if (!firstItem) return
    firstItem.status = 'closed'

    setActivePinia(createPinia())
    const secondStore = useTradingBoardStore()

    expect(secondStore.itemsByStatus.registered).toHaveLength(1)
    expect(secondStore.itemsByStatus.closed).toHaveLength(1)
  })
})
