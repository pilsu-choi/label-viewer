---
okf_version: "0.2"
type: change
title: 세부내역서 집계 행 추출과 급여 인쇄값 정책 통합
description: 2026-10-03 사용자 정책(집계 행도 행으로 추출, 급여는 인쇄된 값만)을 Docraft·harness-v2에 반영했다. 정답지 59건으로 한 번 검증해 dev 병합과 push를 마쳤다. 행 번호(#)는 정답지에서 실패해 보류했다
tags: [docraft, harness-v2, harness-installer, 세부내역서, 급여, summary-rows, validation]
status: active
---

- 날짜: 2026-10-03
- 브랜치(병합 뒤 삭제):
  - Docraft `fix/summary-rows-benefit` → dev `120feef`
  - harness-v2 `fix/summary-rows-benefit` → dev `5ddf433`
  - harness-installer `fix/pin-summary-rows` → dev `e9e588f`
- 워크트리: 각 저장소 `.worktrees/summary-rows-benefit`(정리함)
- 결과: `e2e/out/integrate-1003/summary.md`. 감사: `e2e/out/policy-1003/audit.md`. 정답지 정책: [급여 인쇄된 문서만](2026-10-03-golden-benefit-printed-only.md)

## 무엇을 바꿨나

- **Docraft**([wiki](../../Docraft/wiki/2026-10-03-summary-rows-printed-benefit.md))
  - 세부내역서 전용 표 힌트를 따로 둔다.
  - `keep_totals`에 세부내역서를 넣는다.
  - 집계 라벨 변형을 표준 이름(소계·계·합계·끝수처리조정금액·조정금액)으로 바꾼다.
  - 집계 행에는 일자를 채우지 않는다.
  - '급여=총액이면 지운다' 규칙을 없앴다. 인쇄된 급여액은 남긴다.
- **harness-v2**([wiki](../../harness-v2/wiki/2026-10-03-summary-rows-printed-benefit.md))
  - 요약 행을 식으로 배치한 값은 `confirm=True`로 둔다. 인쇄된 판독(Docraft)으로 확인될 때만 고친다.
  - 미인쇄 급여는 `0`도 총액 복사도 아닌 `""`로 둔다.
  - 요약 행은 같은 종류끼리만 짝짓는다(`align.row_key`).
  - `recover_rows`가 요약 행을 중복으로 추가하지 않는다.
  - 테스트 1920 통과.
- **harness-installer**: 위 두 dev 커밋으로 고정 커밋을 올렸다.

## 검증 (OpenRouter 58회, AWS 0회)

- 정답지 59건이 93.14%에서 **96.24%**로 올랐다.
  - 세부내역서: 87.49 → 93.29
  - 영수증: 99.71 그대로
  - 누락 행: 101 → 3
- 집계 행 칸: 77.7 → 98.9%
- 급여 칸: 98.7%. 파생된 급여 값은 0개다.
- 지연 p50 15.6 → 16.2초.
- 영수증은 프롬프트가 같아서 저장 응답에 새 규칙을 다시 적용했다(호출 0회).

## 보류: 표 행 번호(#)

- `fix/dense-page-json`을 정답지에 써 보았다.
  - 14건 중 13건이 번호 검사에 걸려 asis로 대체됐다.
  - 번호 자리에 URL을 쓰는 등 번호 쓰기가 흔들렸다.
- dev에 넣지 않았다. 재설계 제안은 그 브랜치 wiki에 적었다(키 `row_no`, 반복·감소일 때만 asis, 빽빽한 쪽에만 사용).
- 건국대·청담은 다시 돌리지 않았다.

## 남은 일

- 코드2개_급여액 서식: 인쇄된 급여액 열이 열 배치에서 빠진다.
- 방문별 합계 행에 모델이 적은 날짜를 어떻게 다룰지 정해야 한다.
- 20250102091737a3 계 행의 소수 값을 정답지와 대조해야 한다.
- 합계 필드를 '계'와 '합계' 중 어느 행으로 채울지 정해야 한다.
- 하네스의 식 배치 값을 `confirm`으로 바꾸면 동기(sync) 경로가 AO 값을 유지한다. AWS 배포 때 확인한다(배포 담당 6c 경유).
- 앱 번들 재빌드는 필요할 때 한다.
