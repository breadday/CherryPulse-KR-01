import { createPinia } from 'pinia'
import { mount } from '@vue/test-utils'
import { afterEach, describe, expect, it } from 'vitest'

import App from '../App.vue'

let mountedApp: ReturnType<typeof mount> | undefined

afterEach(() => {
  mountedApp?.unmount()
  mountedApp = undefined
})

describe('App', () => {
  it('renders the six execution-state columns with explicit mock data', () => {
    const wrapper = (mountedApp = mount(App, {
      global: {
        plugins: [createPinia()],
      },
    }))

    const mockBanner = wrapper.get('[data-testid="mock-mode-banner"]')
    expect(mockBanner.text()).toContain('Mock 데이터')
    expect(mockBanner.text()).toContain('증권사 API나 실제 주문 엔진에 연결되지 않습니다.')
    expect(wrapper.findAll('[data-board-column]')).toHaveLength(6)

    for (const title of [
      '등록·설정',
      '매수 감시',
      '매수 주문 중',
      '보유·매도 감시',
      '매도 주문 중',
      '종료',
    ]) {
      expect(wrapper.text()).toContain(title)
    }

    expect(wrapper.findAll('[data-trading-card]')).toHaveLength(6)
    expect(wrapper.text()).toContain('삼성전자')
    expect(wrapper.text()).toContain('엔진 오프라인')
    expect(wrapper.text()).toContain('실주문 비활성')
    expect(wrapper.get('[data-testid="sync-status"]').text()).toContain('오프라인')
  })
})
