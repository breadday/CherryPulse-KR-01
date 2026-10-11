# D02 모바일 물리 확인 체크리스트
작성일: 2026-10-11
근거: D02-BOARD-PROGRESS.md 218줄 남은 완료 조건, 9d6599b 매수 폼 구현
대상: iOS Safari + Android Chrome 실기기 (에뮬레이션 아님)

## 공통 사전 조건
- 브랜치: origin/main HEAD = f2a6128 (보드 마지막 변경 9d6599b)
- 페이지: `web/board/index.html` 로컬 서빙 (file:// 아님, http://로)
- 캐시 비우기 후 로드

## 기기 기록란

### iOS Safari
- 기종: [미기입]
- iOS 버전: [미기입]
- Safari 버전: [미기입]
- 확인일시: [미기입]
- 확인자: [미기입]

### Android Chrome
- 기종: [미기입]
- Android 버전: [미기입]
- Chrome 버전: [미기입]
- 확인일시: [미기입]
- 확인자: [미기입]

## 체크 항목 (각 기기별 Pass/Fail)

### 1. 매수 폼 입력·검증 메시지
- [ ] buy-pattern-name 101자 초과 시 "100자 이내" 표시, 초안 저장 안 됨
- [ ] buy-target-price 빈 값/0 이하/비유한(NaN) 시 "0보다 큰 숫자" 표시, 초안 무변경
- [ ] buy-target-price 100001 이상 시 "10만원 초과" 표시, 초안 무변경
- [ ] 정상 입력(예: 이름 `테스트매수`, 목표가 `70000`) 시 "엔진에는 적용되지 않습니다" 성공 안내 + buy-pattern-list에 카드 추가
- iOS 결과: [ ] Pass [ ] Fail / 비고:
- Android 결과: [ ] Pass [ ] Fail / 비고:

### 2. 매수 목록 렌더 + detail 분기
- [ ] 매수 카드 타이틀·detail 문구 `70000원 이하 매수…` 정상 표시
- [ ] detail이 매도 카드와 구분 (매수=이하 매수, 매도=고정가/비율)
- [ ] 종목 카드에는 손절 연결 select만 있고 매수 연결 UI는 없음 (매수는 목록에서만 관리)
- iOS 결과: [ ] Pass [ ] Fail / 비고:
- Android 결과: [ ] Pass [ ] Fail / 비고:

### 3. 손절 연결 select에 매수 패턴 미노출
- [ ] 종목 카드의 손절 연결 select에 매수 패턴 이름이 노출되지 않음
- [ ] 손절(매도) 패턴만 노출되는지 확인
- iOS 결과: [ ] Pass [ ] Fail / 비고:
- Android 결과: [ ] Pass [ ] Fail / 비고:

### 4. 백업 내보내기·복원 (매수 kind 포함)
- [ ] 내보내기 → JSON에 BUY_PRICE_AT_OR_BELOW 포함
- [ ] 복원 → reload 후 매수 카드 유지, 손절 종목 연결 관계 유지
- [ ] 기존 매도 패턴 2종 복원도 함께 유지
- iOS 결과: [ ] Pass [ ] Fail / 비고:
- Android 결과: [ ] Pass [ ] Fail / 비고:

### 5. 390px에서 매수 폼 필드·고정 문구 줄바꿈 + 가로 넘침 없음
- [ ] viewport 390px에서 buy-pattern-form 가로 스크롤 없음
- [ ] 고정 문구 3종(보호 B -3% 체결 후 확정 / 09:00~15:20 / 1주 고정) 줄바꿈 정상, 잘림 없음
- [ ] input·버튼이 화면 밖으로 밀리지 않음
- iOS 결과: [ ] Pass [ ] Fail / 비고:
- Android 결과: [ ] Pass [ ] Fail / 비고:

### 6. 매수 토글 버튼 터치 영역 + 비활성 표시 가독성
- [ ] 매수 카드의 활성 토글 터치 영역 44px 이상 (손가락 탭 가능)
- [ ] 비활성 시 시각적 구분(opacity/아이콘) 가독성 확보
- [ ] 토글 후 상태 유지 + 백업 포함
- iOS 결과: [ ] Pass [ ] Fail / 비고:
- Android 결과: [ ] Pass [ ] Fail / 비고:

## D02 남은 조건 해소 기준
- 위 6항목 × 2기기 모두 Pass
- 기기·OS 버전 기록 완료
- Fail 있으면 `D02-BOARD-PROGRESS.md`에 Fail 사유 기록 후 수정 → 재확인

## 완료 시 기록
- D02-BOARD-PROGRESS.md에 "모바일 물리 확인 완료 - iOS [기종/OS] / Android [기종/OS] - 6/6 Pass" 기록
- 그 뒤에 D02 닫힘은 D01/D08 서버 동기화까지 끝나고 선언
