<script setup lang="ts">
import { storeToRefs } from 'pinia'

import TradingCard from './TradingCard.vue'
import { useTradingBoardStore } from '../stores/tradingBoard'

const store = useTradingBoardStore()
const { columns, itemsByStatus } = storeToRefs(store)
</script>

<template>
  <section class="board" aria-label="트레이딩 상태 보드">
    <article v-for="column in columns" :key="column.id" class="board-column" data-board-column>
      <header class="board-column__header">
        <div>
          <h2>{{ column.title }}</h2>
          <p>{{ column.description }}</p>
        </div>
        <span>{{ itemsByStatus[column.id].length }}</span>
      </header>

      <div class="board-column__cards">
        <TradingCard v-for="item in itemsByStatus[column.id]" :key="item.id" :item="item" />
      </div>
    </article>
  </section>
</template>

<style scoped>
.board {
  display: grid;
  grid-template-columns: repeat(6, minmax(250px, 1fr));
  gap: 12px;
  min-width: 1600px;
}

.board-column {
  min-height: 470px;
  padding: 12px;
  border: 1px solid var(--border-subtle);
  border-radius: 12px;
  background: var(--surface-panel);
}

.board-column__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  min-height: 76px;
  padding: 4px 4px 14px;
}

h2 {
  margin: 0;
  color: var(--text-primary);
  font-size: 14px;
  font-weight: 590;
}

p {
  margin: 6px 0 0;
  color: var(--text-muted);
  font-size: 11px;
  line-height: 1.5;
}

.board-column__header > span {
  display: grid;
  min-width: 24px;
  height: 24px;
  place-items: center;
  border: 1px solid var(--border-standard);
  border-radius: 999px;
  color: var(--text-secondary);
  background: rgb(255 255 255 / 3%);
  font-family: var(--font-mono);
  font-size: 11px;
}

.board-column__cards {
  display: grid;
  gap: 10px;
}
</style>
