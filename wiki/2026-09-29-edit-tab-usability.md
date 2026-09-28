---
okf_version: "0.2"
type: implementation
title: Label Viewer 편집 탭 버그 수정·사용성 개선
description: 편집 탭 점검에서 찾은 버그 4건 수정, 필드 행 시각 위계, 재구성 패널 접기, 표 셀 불일치 표시·채택, 불일치 개수 기준 통일, 편집 탭 안 불일치 이동 기록
tags: [label-viewer, ui, edit-tab, golden-editor, table, usability]
status: active
---

날짜: 2026-09-29
브랜치: `feat/edit-tab-ui` (하위 `feat/edit-tab-ui-rows`, `feat/edit-tab-ui-count` 병합 후 삭제)
워크트리: `label_veiwer/.worktrees/edit-tab-ui`

## 배경

편집 탭이 눈에 잘 들어오지 않는다는 요청에서 시작했다. D2-INP-001(그룹·빈 값), D2-DET-001(19열×20행 표, 표 셀 불일치 약 300건), D2-REC-001, MC001, Golden이 없는 문서, 1280×800, 다크, JSON 보기, 채택 클릭을 Playwright로 점검했다. 저장 요청은 route로 막았다.

## 점검에서 찾은 문제

| 구분 | 문제 | 원인 |
|---|---|---|
| 버그 | JSON 보기 textarea가 비어 있음 | `el()`이 `value`를 `setAttribute`로 넣어 textarea 내용이 채워지지 않음 |
| 버그 | 표 열 머리글이 보이지 않음 | `.gs-table{width:100%}`로 19열이 36px씩 눌리고, 머리글 input의 `padding-right:23px`가 글자를 가림 |
| 버그 | 채택 후 툴팁이 남고 행이 밀림 | 다시 그릴 때 mouseleave가 나지 않고, 같은 좌표의 새 요소에 브라우저가 hover를 다시 발생시킴 |
| 버그 | "필드이 없습니다" | 조사를 고정으로 씀 |
| 흐름 | 표 셀에 불일치 표시·채택이 없음 | `renderTablesSection`이 compare 상태를 쓰지 않음 |
| 흐름 | 편집 영역이 527px(1280×800은 427px) | 재구성 패널이 고정 높이 280px |
| 흐름 | 빈 Golden 값·key 오편집·빨강 과다·dtype 폭 | 입력칸 스타일과 상태 표현 |
| 흐름 | 사이드바 `불일치 27`과 탭 `비교 14`가 다름 | 사이드바는 AO·Harness score 합산, 탭은 compare 항목 수 |

## 변경

### 버그 수정
- `util.el()`: `value` 키는 property로 넣는다.
- 표: `width:max-content; min-width:100%`, 입력 폭은 `field-sizing:content`(72~220px). 열 삭제 버튼 여백은 hover/focus 때만 준다.
- `rerenderAt(find, fallback, focus)`: 선택자나 함수로 대상을 찾아 스크롤을 유지한다. 다시 그리기 전과 다음 프레임에 `hideTip()`을 호출한다. 추가·삭제·접기·채택이 모두 이 경로를 쓴다.
- `util.josa()`: 받침 여부로 이/가를 고른다.

### 필드 행 (dev의 필드 그리드 위에 적용)
- 작업 중 dev에 들어온 필드 그리드(항목/값/AO/Harness/타입 컬럼, 좁은 패널은 컨테이너 쿼리로 칩 줄)를 기준으로 삼았다.
- 행 좌측 바: 불일치는 `--bad`, Golden 빈 값은 `--warn`(`rowStateClass`).
- 값 입력: 늘 테두리를 두고, 빈 값은 `값 없음` placeholder와 점선 테두리로 표시한다.
- key·그룹명: `keyInput`은 기본 readOnly이고, 더블클릭이나 Enter로 편집한다. key가 바뀌면 compare 연결이 끊기므로 실수로 수정되지 않게 막는다. 새로 추가한 key는 바로 편집할 수 있다.
- 타입: 평소에는 작은 텍스트이고, 행 hover/focus 때만 select 모양을 보인다.
- 그룹 헤더: 굵은 글씨와 불일치 배지.
- AO·Harness 값이 같을 때 칩을 하나로 합치는 기능은 컬럼 구조와 맞지 않아 제외했다.

### 재구성 패널
- 접기 버튼을 추가했다. 접힘 상태(`lv.reconCollapsed`, 공용 `readFlag`/`writeFlag`)와 높이(`lv.reconHeight`)를 기억한다. 기본 높이는 220px이다.
- 1600×900에서 편집 영역에 보이는 필드 행은 펼친 상태 8개, 접은 상태 11개다.

### 표 편집
- 머리글(top)과 행 번호 열(left)을 sticky로 고정하고, 표 영역은 `max-height:min(60vh,480px)` 안에서 스크롤한다.
- 셀 상태 클래스: 불일치는 `mismatch`, 빈 값이면서 소스에 값이 있으면 `warn`. 셀에 `data-path`를 둔다.
- 셀에 포커스가 가면 표마다 하나인 채택 바(`행 i · 열명` + AO/Harness)를 보인다. 칩은 필드와 같은 `compareCell`을 쓴다(`refocus` 인자로 채택 후 같은 셀에 포커스).
- 표 이름 옆에 불일치 배지를 단다. golden에 없는 추가 행(EXTRA row)은 표시할 셀이 없어 배지에서 빠진다.

### 불일치 개수와 이동
- 기준 통일: compare 항목 중 AO나 Harness 한쪽이라도 MATCH가 아닌 항목 수다. 판정은 `util.isMismatch()` 하나로 한다(detail.js 중복 filter와 goldenEditor `mismatchOf` 제거).
- 백엔드 문서 목록에 `mismatch`를 추가하고, 사이드바는 이 값을 쓴다. 테스트 `test_list_mismatch_matches_compare`를 추가했다.
- 편집 탭 상단 요약: `불일치 N`(저장된 compare 기준)과 `빈 값 M`(편집 중인 Golden 기준, 소스에 값이 있는 것만), 이전/다음 버튼.
- `M` / `Shift+M`: 편집 탭에서는 `editor.focusMismatch(dir)`로 필드 행과 표 셀을 문서 순서대로 돈다(접힌 그룹 펼침, flash, bbox 연동). 다른 탭에서는 기존처럼 비교 탭 행으로 간다.

## 검증
- `python3 -m pytest tests -q`: 32 passed.
- D2-INP-001: 사이드바 14 = 탭 14 = 요약 14. 채택 뒤 툴팁 0개, 채택한 행이 화면 안에 있음.
- D2-DET-001: 309로 일치, 표 배지 275, 열 폭 72~220px, 스크롤 중에도 머리글·행 번호 고정.
- MC001: 4로 일치.
- 1280×800과 다크 모드에서 콘솔 에러 없음.

## 남은 과제
- ~~AO 누락이 많은 표에서 열 전체가 빨갛게 칠해지는 문제~~ → [비교 탭 개선](2026-09-29-compare-tab-usability.md)의 공용 상태 색(`entryState`)으로 해결.
- 비교 탭 점검 결과는 [비교 탭 사용성 개선](2026-09-29-compare-tab-usability.md)에서 반영.
