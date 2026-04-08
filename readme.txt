🎯 최종 운영 흐름

🌙 전날 저녁
@@ python save_condition_snapshot.py

👉 결과:

@@  condition_snapshot.json 생성

👉 내용:

주도주_스나이퍼 종목 저장

🌅 다음날 아침
@@ python main_live.py

👉 동작:

snapshot 파일 읽음
종목 먼저 실시간 등록
장 시작 감시 시작
09:00 이후 조건검색 추가 편입 반영