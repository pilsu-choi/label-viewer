---
okf_version: "0.2"
type: feature
title: 문서 유형 필터와 편집 탭 표 다중 셀 일괄 입력
description: 번들 문서 목록에 문서 유형 select 필터를 추가하고, Golden 편집 표에서 드래그·Shift+클릭으로 고른 칸에 같은 값을 한 번에 넣는 기능을 추가한 기록
tags: [label-viewer, list, filter, golden-editor, table]
status: active
---

날짜: 2026-09-29
브랜치: `feat/doctype-filter-multicell`
워크트리: `label_veiwer/.worktrees/filter-multicell`

## 문서 유형 필터

- `frontend/js/list.js`: 상태 칩 오른쪽에 문서 유형 select를 둔다. 옵션은 번들 문서의 `doc_type`에서 모으고 문서 수를 붙인다. 유형이 빈 문서는 "유형 없음"으로 맨 뒤에 둔다.
- 상태 칩과 AND로 걸린다. "전체" 값은 빈 유형과 겹치지 않게 `'*'`로 둔다.

## 표 다중 셀 일괄 입력

- `frontend/js/goldenEditor.js` `renderTablesSection`: 표마다 `anchor`·`sel`(직사각형 범위)을 둔다.
  - 셀 위에서 누른 채 다른 셀로 끌면 범위가 잡히고(`td.sel`), 놓으면 기준 칸 입력에 포커스·전체 선택이 된다.
  - 기준 칸이 있으면 Shift+클릭으로 범위를 바로 잡는다.
  - 선택 범위 안 칸에 입력하면 `fillSel`이 범위의 모든 셀 값과 입력칸을 같은 값으로 바꾼 뒤 한 번 `markDirty` 한다(자동 저장 대상).
  - Esc 또는 다른 칸 클릭으로 선택을 푼다.
- 채택 바(`.table-adopt-bar`)는 기본 안내 ↔ 셀 AO/Harness 비교 ↔ "N칸 선택" 안내를 오가며 항상 자리를 차지한다.

## 결정: 채택 바를 항상 표시

기존에는 셀에 포커스하면 채택 바가 표 위에 나타나며 표가 40px 아래로 밀렸다. 드래그 시작 순간 표가 밀려 포인터가 한 행 위 셀에 닿아 범위가 어긋났다(2×2를 끌었는데 1×2 선택). 바를 항상 보이게 하고 빈 상태에는 사용 안내를 넣어 해결했다.

## 검증

- `pytest` 40건 통과.
- Playwright(표본 205건 복사본): 유형 select 옵션 7종·개수 표시, `세부내역서` 선택 시 205→25건, 상태 칩과 조합 유지. `16.소견서 5` 병명내역 표에서 2×2 드래그 → 4칸 선택, 입력값 4칸 반영, 새로고침 뒤 저장값 유지, Esc 해제, Shift+클릭 3칸 선택, 페이지 오류 없음.
