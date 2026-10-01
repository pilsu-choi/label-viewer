---
okf_version: "0.2"
type: implementation
title: Label Viewer 비교 탭 사용성 개선
description: 비교 탭 점검에서 찾은 채택 흐름·개수 기준·Golden 없음 문제 수정, 기본 불일치 필터, 점수 요약, 셀 채택, 두 탭 공용 상태 색, 근거 팝오버, 표 행 묶기, 소스 필터·검색, 키보드 조작 기록
tags: [label-viewer, ui, compare-tab, usability, keyboard]
status: active
---

날짜: 2026-09-29
브랜치: `feat/compare-tab-ui` (하위 `feat/compare-tab-ui-rows`, `feat/compare-tab-ui-pop` 병합 후 삭제)
워크트리: `label_veiwer/.worktrees/compare-tab-ui`

## 배경

[편집 탭 개선](2026-09-29-edit-tab-usability.md)에 이어 비교 탭을 같은 방식으로 점검했다. 대상은 D2-INP-001, D2-DET-001(434행), MC001, Golden 없는 문서, 1280×800, 다크, 필터, hover, 채택이다. 채택 → 자동 저장 → 목록 갱신 흐름은 storage 복사본을 쓰는 별도 서버에서 실제 저장까지 확인했다.

## 점검에서 찾은 문제

| # | 문제 | 근거 |
|---|---|---|
| 1 | 채택 후 저장되면 목록 스크롤이 맨 위로 돌아감 | `refresh()` → `draw()`가 host를 비움. scrollTop 2000 → 0 |
| 2 | 채택해도 저장 전까지 행이 그대로 is-off·"추가" | 낙관적 표시 없음 |
| 3 | Golden 없는 문서도 비교 결과·AO 점수 표시 | 단건 조회가 Golden 없이도 compare/score를 계산 |
| 4 | 필터 칩 숫자 ≠ 표시 행 수 | AO·Harness를 따로 세어 합산(INP-001: 4+1+22=27, 실제 14행) |
| 5 | 기본 "전체"라 일치 항목까지 나옴 | DET-001 434행 중 105행 일치 |
| 6 | 점수 카드가 세로 약 130px를 차지 | 1600×900에서 목록 약 7행 |
| 7 | 늘 비어 있는 채택 열(137px) | hover 때만 버튼 노출, `AO 채택`/`H 채택` 표기 혼재 |
| 8 | 좁은 화면에서 값이 글자 중간에서 줄바꿈 | `word-break: break-word` |
| 9 | Golden이 비어서 생긴 차이를 소스 오류처럼 빨강으로 표시 | 상태 색의 의미가 뒤바뀜 |
| 10~13 | 표 항목 평면 나열, 소스 필터·검색 없음, 팝오버 첫 줄이 내부 경로이고 행을 가림, 키보드 조작 없음 | — |

## 변경

### 동작 수정
- `draw(preserveScroll)`: 다시 그리기 전 scrollTop과 맨 위 앵커 행(data-path)을 기억했다가 refresh 때 복원한다. 필터를 바꾸면 맨 위로 간다.
- `markAdopted(path, value)`: 채택 즉시 행에 `is-pending`과 "채택됨 · 저장 대기"를 표시하고 Golden 칸 값을 갱신한다. 저장 뒤 refresh에서 비운다. detail.js의 onAdopt가 호출한다.
- 백엔드 `doc_detail()`: Golden이 없으면 `compare: []`, `score: {ao: None, harness: None}`으로 목록 API와 맞춘다. 비교 탭은 "Golden이 없어 비교할 수 없습니다"와 [편집 탭에서 Golden 만들기]를 보여 준다. 테스트 `test_doc_detail_without_golden_matches_list_api`를 추가했다.
- `matchesFilter(e, key, source)` 하나로 칩 개수와 필터링을 함께 판정한다(`countsByFilter`). "불일치 전체" 칩은 탭 배지·사이드바·편집 요약과 같은 `isMismatch` 기준이다.

### 공간과 기본값
- 필터 순서는 `불일치 전체 · 불일치 · 누락 · 추가 · 전체`이고 기본은 불일치 전체다(`lv.cmpFilter`). `flashPath`는 대상이 현재 필터에 없을 때만 필터를 바꾼다.
- 점수는 한 줄 요약(`scoreMini`)으로 두고 누르면 상세 카드를 펼친다(`lv.cmpScoreExpanded`).
- 채택 열을 제거했다. AO·Harness 값 칸 자체가 `.gs-chip` 채택 버튼이다(`valueCell`). Golden이 비었으면 문자 diff 없이 중립색으로 보인다. (2026-09-30 [채택 오클릭 방지](2026-09-30-compare-adopt-ux.md)에서 값 칸은 근거 고정, 채택은 별도 버튼으로 바뀜)
- 항목 열은 한 줄 말줄임과 title, 값은 공백 기준으로 줄바꿈한다.
- 1600×900 가시 행: DET-001 12행, INP-001 11행(그룹 헤더가 많음).

### 두 탭 공용 상태 색
`util.entryState(entry, goldenValue)`가 편집 탭 필드 행·표 셀·AO/Harness 칸과 비교 탭 행·셀에 같은 상태를 준다. 개수 기준(`isMismatch`)은 바꾸지 않았다.

| 상태 | 조건 | 표시 |
|---|---|---|
| `bad` | 한쪽이라도 MISMATCH/TYPE_MISMATCH | 빨강 |
| `warn` | Golden이 비어 있고 소스에 값이 있음 | 주황(소스 값은 중립) |
| `weak` | 그 밖에 한쪽 소스만 누락·추가 | 옅은 회색 |
| (없음) | 일치 | — |

그 결과 DET-001 편집 탭 표에서 AO 누락 때문에 열 전체가 빨갛던 현상이 없어지고, 실제 값 불일치 셀만 빨강으로 남는다.

### 근거 팝오버
- 첫 줄은 `entryLocation()`으로 "필드 › 항목", "그룹 › 항목", "표 › #행 › 열"(추가 행은 "추가 행 N")을 보여 준다. 내부 경로와 복사 버튼은 접힌 "상세" 안에 있다.
- 배치는 hover한 행의 위나 아래 중 공간이 큰 쪽이고, 행을 덮지 않으며 뷰포트 안으로 맞춘다. 고정, Esc, 바깥 클릭, 긴 근거 내부 스크롤은 그대로다.

### 표 행 묶기·소스 필터·검색·키보드
- 표 항목은 `#행` 소그룹으로 묶는다. 헤더에는 행 번호, 대표 값(첫 열), 불일치 수를 보여 준다. 처음에는 불일치가 있는 행만 펼치고, 이후 토글 상태는 유지한다. `M` 이동 대상이 접혀 있으면 펼친다. 대표 값·불일치 수는 필터·검색과 무관하게 행 전체 기준으로 정한다(2026-10-01 `fix/rowgroup-label`: 불일치 필터에서 `항목` 칸이 걸러지면 헤더가 `#9 121956`처럼 다른 칸 값으로 바뀌던 문제 수정).
- 소스 세그먼트(`둘 다 · AO · Harness`, `lv.cmpSource`)와 항목·값 검색(200ms debounce)을 추가했다. 칩 개수도 이것을 반영한다. 검색 중 다시 그려도 입력 포커스와 커서를 유지한다.
- 키보드는 행에 포커스가 있을 때 동작한다. `↑/↓`는 이동(펼쳐진 헤더는 건너뜀), `A`/`H`는 채택, `Enter`는 근거 고정·해제, 접힌 소그룹에서 `Enter`/`Space`는 펼치기다. 펼친 뒤에는 첫 데이터 행으로 포커스를 옮긴다.

## 검증
- `python3 -m pytest tests -q`: 33 passed.
- 실제 저장 왕복(D2-DET-001): scrollTop 2000 → 저장 후 2026(앵커 행 기준 복원), pending 표시 → 저장 후 해제.
- 칩 숫자 = 필터 결과 행 수: INP-001 14/2/1/11/33, DET-001 309/10/179/128/434, 소스=Harness 16.
- Golden 없는 문서는 빈 상태와 편집 탭 이동 버튼이 나오고 탭 배지에 숫자가 없다.
- 팝오버 rect가 hover 행과 겹치지 않고, 뷰포트 안에 있다(하단 행 포함).
- 키보드: ↓×3 후 H 채택 → 저장 대기, Enter 고정 / Esc 해제, 접힌 행 묶음을 Enter로 펼치면 첫 데이터 행으로 포커스.
- 1600×900 / 1280×800 / 다크 모드에서 콘솔 에러 없음.

## 남은 과제
- INP-001처럼 그룹이 많은 문서는 가시 행이 11개다. 필요하면 그룹 헤더를 더 줄인다.
