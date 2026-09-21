<script setup lang="ts">
import type { TradingItem } from '../domain/trading'

defineProps<{
  item: TradingItem
}>()
</script>

<template>
  <article class="trading-card" data-trading-card>
    <header class="trading-card__header">
      <div>
        <strong>{{ item.name }}</strong>
        <span>{{ item.symbol }} · {{ item.market }}</span>
      </div>
      <span class="price">{{ item.lastPrice }}</span>
    </header>

    <p class="status-detail">{{ item.statusDetail }}</p>

    <dl>
      <div>
        <dt>매수</dt>
        <dd>{{ item.buyPattern }}</dd>
      </div>
      <div>
        <dt>매도</dt>
        <dd>{{ item.sellPattern }}</dd>
      </div>
      <div>
        <dt>수량</dt>
        <dd>{{ item.quantity }}주</dd>
      </div>
    </dl>

    <div v-if="item.warning" class="warning">{{ item.warning }}</div>

    <footer>업데이트 {{ item.updatedAt }}</footer>
  </article>
</template>

<style scoped>
.trading-card {
  display: grid;
  gap: 14px;
  padding: 16px;
  border: 1px solid var(--border-standard);
  border-radius: 10px;
  background: var(--surface-card);
  box-shadow: inset 0 1px rgb(255 255 255 / 3%);
}

.trading-card__header {
  display: flex;
  justify-content: space-between;
  gap: 12px;
}

.trading-card__header div {
  display: grid;
  gap: 4px;
}

strong {
  color: var(--text-primary);
  font-size: 14px;
  font-weight: 590;
}

.trading-card__header span,
footer {
  color: var(--text-muted);
  font-size: 11px;
}

.price {
  color: var(--text-secondary);
  font-family: var(--font-mono);
  white-space: nowrap;
}

.status-detail {
  margin: 0;
  color: var(--text-secondary);
  font-size: 13px;
}

dl {
  display: grid;
  gap: 8px;
  margin: 0;
}

dl div {
  display: grid;
  grid-template-columns: 38px 1fr;
  gap: 8px;
}

dt,
dd {
  margin: 0;
  font-size: 11px;
}

dt {
  color: var(--text-subtle);
}

dd {
  color: var(--text-secondary);
}

.warning {
  width: fit-content;
  padding: 4px 8px;
  border: 1px solid rgb(248 113 113 / 24%);
  border-radius: 999px;
  color: #fca5a5;
  background: rgb(248 113 113 / 8%);
  font-size: 10px;
  font-weight: 590;
}
</style>
