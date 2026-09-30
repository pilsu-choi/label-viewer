---
okf_version: "0.2"
type: implementation
title: 비교 탭 채택 오클릭 방지·되돌리기·빈 값 채택
description: 비교 탭 값 칸 클릭이 바로 채택되던 문제를 근거 보기와 분리하고, 채택 되돌리기 토스트와 누락(빈) 값 채택을 추가한 기록
tags: [label-viewer, ui, compare-tab, adopt, undo]
status: active
---

날짜: 2026-09-30
브랜치: `feat/compare-adopt-ux`
워크트리: `label_veiwer/.worktrees/compare-adopt-ux`

## 배경

[비교 탭 사용성 개선](2026-09-29-compare-tab-usability.md)에서 AO·Harness 값 칸 전체를 채택 버튼(`.gs-chip`)으로 만들었다. 그 결과 하네스 근거를 보려고 값을 누르면 바로 Golden에 채택되고, 디바운스 자동 저장까지 이어졌다. 되돌리기 수단도 없었다. 소스 값이 비어 있는 항목(누락)은 채택할 수 없었다.

## 변경

### 클릭 의도 분리 (`compare.js`)
- `valueCell()`: 값 칸은 더 이상 버튼이 아니다. 값 칸을 누르면 행 클릭과 같이 근거 팝오버가 고정된다.
- 채택은 칸 오른쪽의 작은 `[채택]` 버튼(`.cmp-adopt`)으로 한다. 이 버튼은 행 hover·포커스·근거 고정(`tr.is-pinned`) 때만 보인다.
- 근거 팝오버 하단에 `[AO 채택 · 값] [Harness 채택 · 값]` 버튼(`.ev-actions`)을 두었다. 근거가 길어 스크롤돼도 하단에 고정(sticky)되어 있어서 근거를 본 뒤 바로 채택할 수 있다.
- 키보드 `A`/`H` 채택은 그대로다. `markAdopted()`는 다시 그리기 전에 팝오버를 닫는다. 그렇지 않으면 사라진 행에 고정 팝오버가 남는다.

### 되돌리기 (`util.js`·`goldenEditor.js`·`detail.js`)
- `toast(msg, kind, action)`: `action = { label, onClick }`을 넘기면 토스트 안에 버튼이 생긴다. 이때 토스트는 5초 동안 보인다.
- `applyAdopt()`·`adoptValue()`가 채택 전 값(새 칸이면 `''`)을 돌려준다.
- 비교 탭에서 채택하면 "Golden에 채택했습니다 · [되돌리기]" 토스트가 뜬다. 되돌리기를 누르면 이전 값을 다시 채택하는 방식으로 복원한다. 되돌리기 자체는 토스트를 다시 띄우지 않는다.

### 빈 값 채택
- 비어 있는 소스 값은 `''`로 채택한다(`adoptable()`). 백엔드 `norm()`이 `''`와 `None`을 같게 보므로 Golden `''`과 누락 소스는 MATCH가 된다.
- 비교 탭 채택 버튼·팝오버 버튼·A/H 키와 편집 탭 AO/Harness 칩(`compareCell`, 이전에는 `disabled`) 모두 빈 값을 채택할 수 있다. 제목(title)은 "… 빈 값을 Golden에 채택"이다.

## 검증

- pytest 45 passed.
- storage 복사본(`0930_golden_aws_harness`)으로 띄운 별도 서버와 Playwright(1600×900)로 다음을 확인했다.
  - 값 칸을 클릭하면 팝오버가 고정되고 채택(`is-pending`)은 0건이다.
  - 팝오버의 AO 채택 → "채택됨 · 저장 대기" 표시와 토스트가 뜬다. 되돌리기 → 원래 값(`0`)으로 저장된다.
  - Harness 누락 항목(`시작일자`)에서 빈 값 채택 → 저장 후 Harness는 "일치", AO는 "추가"로 바뀐다.
  - 고정 상태에서 `H` 키로 채택하면 팝오버가 닫힌다. 콘솔 오류는 없었다.
