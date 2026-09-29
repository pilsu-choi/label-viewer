---
okf_version: "0.2"
type: feature
title: 편집 탭 불일치 강조와 Golden에 없는 키 ghost 행 표시
description: 편집 탭에서 불일치 칸을 테두리 색으로 강조하고, AO·Harness에만 있는 키를 채택 가능한 ghost 행으로 보여주는 변경 기록
tags: [label-viewer, golden-editor, ui, compare]
status: active
---

날짜: 2026-09-29
브랜치: `feat/editor-mismatch-viz`
워크트리: `label_veiwer/.worktrees/editor-mismatch-viz`

## 배경

`16.소견서 3`의 `진단 · 사고발생일자`는 비교 탭에는 `EXTRA`(Golden 값 없음)로 보이지만 편집 탭에는 없었다. 비교 탭은 Golden·AO·Harness 키의 합집합을 그리고, 편집 탭은 Golden JSON에 있는 키만 그리기 때문이다. 불일치 행도 왼쪽 2px 막대로만 표시돼 눈에 잘 띄지 않았다.

## 변경

- `frontend/app.css`
  - 불일치(`bad`) 행은 값 입력칸에 빨간 테두리와 옅은 빨간 배경을 준다. Golden 빈 값(`warn`)은 주황으로 표시한다. 표 셀도 같은 색 테두리를 쓰고, 왼쪽 막대는 3px로 키웠다.
  - `.field-row.ghost`, `.group-block.ghost`, `.table-ghosts`, `.ghost-cell` 스타일을 추가했다(빨간 점선 테두리).
- `frontend/js/goldenEditor.js`
  - `renderedPaths()`와 `ghostEntries(area, container)`가 compare 엔트리 중 소스 값은 있고 Golden에는 없는 위치(문서 0)를 고른다.
  - 필드와 그룹에는 `ghostRow`로 "Golden에 없음" 행을 붙인다. AO/Harness 칩을 누르면 `applyAdopt`가 그 위치를 만들어 값을 채택한다. 그룹이나 표 자체가 없으면 ghost 블록을 그린다.
  - 표에서 빠진 셀은 `ghostStrip`(행 N · key + 칩)으로 보여준다.
  - 그룹/표 불일치 배지(`mismatchBadge`)와 요약 바(`Golden에 없음 K`)에 ghost 개수를 포함하고, 이전/다음 불일치 이동에도 ghost 항목을 넣었다.

## 검증

- `node --check frontend/js/goldenEditor.js` 통과.
- 워크트리 앱을 8766 포트로 띄워 `16.소견서 3` 편집 탭을 확인했다(자동 저장 끔).
  - `진단` 그룹에 `사고발생일자` ghost 행과 AO·Harness 칩(20200729)이 보였다.
  - 요약 바에 `불일치 1 · 빈 값 0 · Golden에 없음 1`이 표시됐다.
  - AO 칩을 누르자 해당 값이 실제 행으로 바뀌었다.
- 표 ghost strip과 ghost 그룹/표 블록은 화면으로 확인하지 않았다.

## 후속 수정: 표 셀 강조가 절반만 칠해지던 문제

브랜치: `fix/table-cell-highlight`, 워크트리: `label_veiwer/.worktrees/table-cell-highlight`

`16.소견서 5`의 `병명내역` 표에서 주황 테두리가 셀의 절반에만 그려졌다. 원인은 두 가지다.
- 테두리를 셀(`td`)이 아니라 입력칸에 걸었다.
- 표 입력칸은 `field-sizing: content`여서 글자 길이만큼만 넓어진다. 열 머리글이 더 넓으면 입력칸이 셀보다 좁아진다.

테두리(`inset box-shadow`)를 `td.bad`·`td.warn`으로 옮기고, 입력칸 최소 폭을 `max(72px, 100%)`로 바꿔 셀을 채우게 했다. 수정 전후 스크린샷으로 셀 전체가 강조되는 것을 확인했다.
