# HSdeck 레거시 카드 API

레거시 카드의 **최초 추가일 스펙과 이후 날짜별 변경 사항**을 원본으로 관리합니다. 그 외 확장팩의 데이터는 수정하지 않습니다.

- `data/<카드ID>.json` — 원본: `card.releasedAt`의 최초 스펙(`cost`, `attack`, `health` 등) + 날짜순 `card.patches`(변경된 속성만)
- `taxonomy-history.json` — 종족·주문 속성의 도입 날짜(한국 시간), 카드별 예외, 기존 종족 보존 규칙을 저장합니다. 생성기는 이를 각 카드의 `card.history`에 기록합니다.
- `cards.json` — 워드프레스 관리자에서 가져오는 현재 카드 목록
- `render.json` — WebGL·워드프레스 날짜 조회를 위한 **현재 카드 정보 + 변경 이력 통합 파일**
- `art/` — 카드 원화
- `golden/index.json`, `golden/cards/`, `golden/textures/` — 카드 ID와 DBF ID가 일치하는 현행 원본 황금 원화 재질, 애니메이션 설정 및 텍스처. 과거 버전의 황금 효과를 보증하지 않습니다. `golden/unavailable.json`은 원본 황금 재질을 확인하지 못한 카드를 기록합니다. 영웅 능력 자료도 보관하지만 현재 HSdeck 카드 렌더러는 영웅 능력을 표시하지 않습니다.
- `tools/migrate-chronology.py` — 과거의 역방향 이력을 최초 스펙+전진형 변경점으로 일회성 변환하는 도구
- `tools/build-api.py` — 위 원본 스펙과 변경점을 적용해 최신 카드 목록 및 이전 플러그인 호환 이력을 자동 생성하는 도구
- `tools/test-chronology.py` — 카드별 스펙과 생성 결과의 일치 여부 확인

`history.json`은 HScard 7.12.10 이하가 정상 동작하도록 **일시적으로 유지한 호환 파일**입니다. 7.12.11부터는 별도 `history.json`을 요청하지 않습니다. 운영 사이트의 플러그인을 업그레이드한 뒤 삭제할 수 있습니다.

다른 확장팩의 변경 이력은 각 확장팩 저장소의 카드별 JSON에서 관리합니다. 카드 이름만 같다는 이유로 토큰·재출시 카드에 이력을 복사하지 않습니다.

기본·오리지널 시기의 한국어 이름과 설명은 `tools/import-original-descriptions.py`로 구버전 클라이언트의 같은 카드 ID를 순서대로 비교합니다. 설명의 줄바꿈·공백·굵기·기울기를 보존하고, 동일한 연속 구간만 합칩니다. `historicalTextObservations`는 원문과 처음/마지막 확인 빌드이며, `card.history`는 날짜 조회용 표시값입니다. 날짜 기준과 이미 승인된 표시 예외는 `tools/original-text-patches.json`에서 관리합니다. 앱스토어 업로드 날짜를 패치 적용일로 사용하지 않으며, 원본이 없는 중간 빌드나 미확정 전환 시각을 확인된 사실로 취급하지 않습니다. 비교용 임시 파일은 검사 후 삭제합니다.


날짜별 표시: 원본 JSON의 `card`는 최초 스펙, `card.patches`는 변경된 값만 순서대로 저장합니다. `render.json` / `history.json`에는 현행 워드프레스 호환을 위한 최신 상태+과거 구간의 역방향 `history`를 **생성**합니다. 최신 `cards.json` 역시 빌드 결과물이므로 미래의 카드 스펙 수정은 `cards.json`이 아니라 개별 JSON의 `patches`에 적용합니다. `taxonomy-history.json`의 기존 종족 및 주문 속성 변경도 각 카드의 `patches`에 날짜별로 이전됩니다.

**복원 한계:** 기존 자료에 없던 과거 공격력·생명력 변경은 자동으로 추정하지 않습니다. 미확인 최초 스펙은 보유 중인 현행값을 임시 기준으로 두며, 실제 과거 자료 검증 후 개별 카드의 최초 스펙과 해당 날짜 패치를 정정해야 합니다. `releaseStatus: estimated`와 `pending`은 확인되지 않은 날짜를 의미합니다. `nativeTags`는 최신 클라이언트에서 추출한 참고 원본이며 역사 시점의 스펙은 `card`와 `patches`로 판단합니다.

누락된 수치 밸런스 패치는 `tools/verified-legacy-balances.json`에 출처와 함께 기록합니다. `tools/apply-verified-balances.py`가 개별 카드 JSON의 `patches`로 병합하며, 같은 날짜에 이미 입력된 동일한 값은 건너뛰고 충돌하거나 현행 카드 스펙이 불일치하면 오류를 냅니다. 승인되지 않은 클라이언트 빌드 차이는 `tools/legacy-balance-candidates.json`의 검증 후보로만 보관합니다.


역대 클라이언트 수치 비교는 `tools/legacy-balance-candidates.json`(334개 HearthSim 빌드)과 `tools/archived-build-dates.json`(한국 날짜와 근거)을 출처로 합니다. `tools/import-archived-stats.py`는 출시일 이후 수치 변경만 선택적으로 `card.patches`에 병합하고, 이미 일치하는 변경은 건너뜁니다. 다른 기록과 충돌하거나 최신 수치가 맞지 않는 항목은 데이터를 덮어쓰지 않고 `tools/legacy-stat-reconstruction-report.json`에 검토 대상으로 남깁니다. 최초 베타 이전 수치는 2013-08-17 스펙 복원용으로만 사용하고 패치를 만들지 않습니다.
