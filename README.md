# HSdeck legacy 카드 API

- `data/<카드ID>.json`: 카드 원본 정보와 `card.history`의 날짜별 변경점
- `cards.json`: WordPress 카드 JSON 관리자에서 가져올 현재 카드 정보
- `render.json`: WebGL 렌더러용 경량 카드 정보
- `history.json`: 날짜별로 바뀐 부분만 담은 경량 조회용 파일
- `art/`: 원화 원본 (있는 경우)
- `tools/build-api.py`: 현재 `cards.json`은 보존하고 두 경량 색인을 다시 생성
- `history-pending.json`: 아직 저장소가 없는 카드 44종의 이관 대기 기록 (사이트 로딩에 사용하지 않음)

`cards.json`, `render.json`, `history.json`은 서로 다른 소비자를 위해 필요한 출력이므로 임의로 삭제하지 않습니다. 이전 일회용 마이그레이션 스크립트와 전체 규칙 복사본은 제거했습니다.
