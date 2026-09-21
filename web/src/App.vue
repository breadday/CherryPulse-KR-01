<script setup lang="ts">
import { storeToRefs } from 'pinia'

import TradingBoard from './components/TradingBoard.vue'
import { useTradingBoardStore } from './stores/tradingBoard'

const store = useTradingBoardStore()
const { totalItems } = storeToRefs(store)
</script>

<template>
  <div class="app-shell">
    <aside class="sidebar">
      <div class="brand">
        <span class="brand__mark">CP</span>
        <div>
          <strong>CherryPulse</strong>
          <span>KR execution board</span>
        </div>
      </div>

      <nav aria-label="주요 메뉴">
        <a class="active" href="#board">트레이딩 보드</a>
        <span class="nav-item nav-item--disabled" aria-disabled="true">종목 관리</span>
        <span class="nav-item nav-item--disabled" aria-disabled="true">매수 패턴</span>
        <span class="nav-item nav-item--disabled" aria-disabled="true">매도 패턴</span>
        <span class="nav-item nav-item--disabled" aria-disabled="true">주문·체결 기록</span>
        <span class="nav-item nav-item--disabled" aria-disabled="true">운영 상태</span>
      </nav>

      <div class="sidebar__footer">
        <span class="status-dot"></span>
        엔진 오프라인
      </div>
    </aside>

    <main>
      <header class="topbar">
        <div>
          <p>EXECUTION BOARD</p>
          <h1>트레이딩 보드</h1>
        </div>
        <div class="topbar__status">
          <span>등록 종목 {{ totalItems }}</span>
          <span>실주문 비활성</span>
        </div>
      </header>

      <section class="mock-banner" data-testid="mock-mode-banner">
        <strong>Mock 데이터 모드</strong>
        <span
          >현재 화면은 예시 데이터만 표시하며 증권사 API나 실제 주문 엔진에 연결되지 않습니다.</span
        >
      </section>

      <section class="summary-grid" aria-label="운영 상태 요약">
        <article>
          <span>실행 모드</span>
          <strong>PAPER / MOCK</strong>
        </article>
        <article>
          <span>엔진 연결</span>
          <strong class="danger">오프라인</strong>
        </article>
        <article>
          <span>최근 시세</span>
          <strong>Mock snapshot</strong>
        </article>
        <article>
          <span>설정 반영</span>
          <strong>예시 버전 v1</strong>
        </article>
      </section>

      <div id="board" class="board-scroll">
        <TradingBoard />
      </div>
    </main>
  </div>
</template>
