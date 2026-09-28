---
okf_version: "0.2"
type: implementation
title: Label Viewer 상세 화면 레이아웃·그리드·스크롤 개선
description: 패널 접기, 이미지 동적 재조정, 편집·재구성 데이터 그리드, 비교 근거 팝오버 스크롤, 추가·삭제 시 스크롤 유지를 반영한 기록
tags: [label-viewer, ui, layout, grid, compare, usability]
status: active
---

날짜: 2026-09-29
브랜치: `feat/label-viewer-layout-grid`
워크트리: `label_veiwer/.worktrees/label-viewer-layout-grid`

## 요청

1. 내보내기 버튼에 마우스를 올려도 포인터 커서가 나오지 않았다.
2. 우측 패널 폭을 바꾸면 중앙 이미지도 동적으로 확대·축소되어야 한다.
3. 편집 탭의 필드·그룹과 재구성 보기에 격자가 없어 내용이 눈에 잘 들어오지 않았다.
4. 좌측·우측 패널을 접고 펼 수 있어야 한다.
5. 비교 탭의 Harness 근거가 길면 넘쳐서 스크롤로 볼 수 없었다.
6. 필드를 추가하면 스크롤과 포커스가 맨 위로 올라갔다.

## 변경

| 항목 | 내용 |
|---|---|
| 포인터 | 공통 `.btn`에 `cursor: pointer`를 추가했다. disabled 버튼은 `not-allowed`다. |
| 동적 재조정 | `imageViewer`가 `fitMode`(`page`/`width`/`manual`)를 기억한다. stage의 `ResizeObserver`가 rAF 단위로 fit을 다시 적용하고, 수동 확대 상태에서는 중심을 기준으로 폭 비율만큼 배율을 조정한다. bbox 포커스 중에는 건너뛴다. |
| 이미지 툴바 | 폭이 560px 이하이면 `너비 맞춤`·`전체 보기` 라벨을 숨기고 아이콘만 남긴다(container query). 더 좁으면 두 줄로 줄바꿈한다. 스플리터를 드래그하는 동안 텍스트가 선택되지 않게 막았다. |
| 패널 접기 | 문서 레일과 검수 패널 헤더에 접기 버튼을 두었다. 접으면 36px 세로 스트립이 된다. 단축키는 `[`와 `]`이고, 상태는 `lv.railCollapsed`·`lv.panelCollapsed`에 저장한다. 펼치면 이전 폭으로 돌아온다. |
| 편집 그리드 | 필드와 그룹 필드는 `항목 \| 값 \| AO \| Harness \| 타입 \| 삭제` 열로 된 격자로 표시한다. 헤더와 행이 같은 `grid-template-areas`를 쓴다. 불일치한 셀에만 `bad-soft` 색을 칠한다. 패널 폭이 640px 이하이면 예전처럼 값 아래에 칩으로 쌓는다(container query). 그룹은 카드로 감쌌다. |
| 재구성 보기 | key-value 영역은 테두리가 있는 2열 격자로 바꾸고 라벨 열에 색을 넣었다. 표는 헤더, 옅은 줄무늬, 숫자 정렬(`tabular-nums`)을 적용했다. Markdown 출력도 같은 스타일이다. |
| 비교 근거 | 행에서 팝오버로 마우스를 옮길 때 200ms 동안 닫지 않도록 했다. 팝오버는 `max-height: min(60vh, 420px)`에 내부 스크롤과 `overscroll-behavior: contain`을 적용했다. 화면 아래쪽에서는 위로 뒤집어 표시하고, 행을 클릭하면 고정된다(Esc나 바깥 클릭으로 닫는다). 표 헤더는 스크롤할 때 뒤 내용이 비치지 않도록 z-index를 올렸다. |
| 스크롤 유지 | 필드·그룹·표 추가, `+` 단축키, 필드 삭제를 모두 기존 `rerenderAt(selector, fallback)`로 처리한다. 스크롤 위치를 유지하고, 새 행이나 인접 행에 포커스를 준다. |

## 검증

- 백엔드 테스트 31개 통과. `frontend/js/*.js` 전체 `node --check` 통과.
- dummy2 번들(D2-DET-001)을 Playwright로 확인했다.
  - 내보내기 버튼 커서가 pointer로 나온다.
  - 스플리터를 드래그하면 이미지 배율이 바뀌고, 수동 확대 상태에서는 비율대로 조정된다.
  - `[`·`]`로 패널을 접고 펼 수 있고, 새로고침 후에도 상태가 유지된다.
  - 근거 팝오버를 휠로 스크롤할 수 있다(scrollTop 261px).
  - 추가·삭제 뒤에도 scrollTop이 바뀌지 않는다.
- 라이트/다크 × 1920/1440 전체 캡처에서 콘솔 에러는 0건이다.

## 관련

- [Label Viewer UI 마감 품질 개선](2026-09-28-label-viewer-ui-polish.md)
- [README](../README.md)
