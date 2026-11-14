# HSdeck 확장팩 출시일 메타데이터

사이트가 사용하는 출시일은 카드별 최초 사용일과 구분합니다. 새로운 **공개 API 저장소** 루트에 `site-set.json`을 넣으면 이 저장소의 자동 등록 작업이 목록에 반영합니다.

```json
{
  "schema": 1,
  "timezone": "Asia/Seoul",
  "name": "검은 제국의 지배",
  "slug": "reign-of-the-black-empire",
  "assetKey": "reign-of-the-black-empire",
  "releasedAt": "2026-10-21",
  "rotation": "딱정벌레의 해",
  "rotationSlug": "year-of-the-beetle"
}
```

기존 목록은 `site-expansions.json`에 보존하며, 새 `site-set.json`은 같은 슬러그의 항목을 업데이트하거나 새로운 슬러그를 추가합니다. 기존 카드 데이터 JSON과 `release-policy.json`은 수정하지 않습니다.

자동 동기화는 **30분마다** GitHub Actions가 실행될 때 이루어집니다. 사이트는 갱신된 목록을 별도 주기로 불러옵니다. 따라서 GitHub에 JSON을 푸시하는 순간 **즉시 동기식 등록되는 방식은 아닙니다.** GitHub 예약 실행 지연 가능성도 있습니다. 즉시 등록이 필요하다면 인증된 webhook/dispatch 설정이 별도로 필요합니다.
