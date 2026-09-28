---
okf_version: "0.2"
type: implementation
title: Label Viewer UI 마감 품질 개선
description: 디자인 토큰을 5단계 글자 크기·4px 간격·2종 컨트롤 높이로 정리하고, 전 화면의 컴포넌트·문구·상태 표현을 통일한 기록
tags: [label-viewer, ui, design-system, polish]
status: active
---

날짜: 2026-09-28
브랜치: `feat/label-viewer-ui-polish`
워크트리: `label_veiwer/.worktrees/label-viewer-ui-polish`

## 목적

앞선 두 차례 개편(교정지 검수대 콘셉트, 제품형 검수 workspace)으로 화면 구조는 갖췄지만 여전히 "허접해 보인다"는 평가가 있었다. 원인을 콘셉트가 아닌 마감 품질로 보고, 화면 구조와 기능은 그대로 둔 채 시각적 일관성만 정리했다.

## 진단 (개선 전 캡처 기준)

- font-size가 9px~30px 사이 18단계로 흩어져 있어 위계가 흐렸다.
- `DOCUMENTS`, `+ Add Field`, `Fit Width`, `Create Golden Set`처럼 영어와 한국어 문구가 섞여 있었다.
- 필드 행에서 AO·Harness 캡션과 값이 겹쳤다(`HARNES2026…`).
- 모든 행의 삭제 ✕가 항상 빨간색으로 보여 화면이 산만했다.
- 이미지 페이지가 여백 없이 두꺼운 테두리로 패널을 채웠다.
- 패널 헤더 높이가 서로 달랐고, 스플리터는 두꺼운 회색 띠였다.
- 네이티브 select·체크박스를 그대로 썼고, hover 행을 진한 노랑으로 채웠다.
- 목록 카드는 파일 유무를 취소선으로 표시했다. 업로드 화면은 한쪽으로 쏠려 있었다.

## 디자인 토큰

| 구분 | 값 |
|---|---|
| 글자 크기 | `--fs-xs` 11 · `--fs-sm` 12 · `--fs-md` 13 · `--fs-lg` 15 · `--fs-xl` 22 (px) |
| 간격 | `--sp-1`~`--sp-8`, 4px 배수 |
| 컨트롤 높이 | `--h-sm` 24 · `--h-md` 32 |
| 모서리 | `--r-sm` 4 · `--r-md` 6 · `--r-lg` 8 |
| 그림자 | `--shadow-sm`(카드), `--shadow-pop`(팝오버·툴팁·메뉴) |
| 포커스 | 전역 `:focus-visible` 2px accent outline |

상태색(ok/bad/warn/extra/type)은 작은 배지, 6px 점, 행 왼쪽 2px 바에만 쓴다. 형광 노랑(`--hl`)은 bbox 강조와 `M` 이동 플래시에만 쓴다.

## 공통 컴포넌트

- `.btn`은 `.primary`·`.ghost`·`.danger`·`.sm`·`.icon` 변형으로 정리했다. 기존 `btn-*` 클래스는 모두 대체했다.
- `.seg`(구 `.toggle-group`, 목록 보기 전환 포함), `.switch`(구 `.review-toggle`), `.badge`, `.dot`, `.chip` 컴포넌트를 둔다.
- `.panel-head`는 44px 높이다. 문서 레일, 이미지 툴바, 우측 탭, 재구성 보기 헤더에 적용했다.
- `.splitter`는 1px 선에 투명한 6px 잡는 영역을 두고, hover·드래그 때 accent 색으로 바뀐다.
- `.tooltip`(카드형)과 `.empty`(빈 상태)를 둔다.
- 아이콘은 `util.js`의 `icon(name)`이 만드는 Lucide 스타일 stroke 아이콘으로 통일했다. 텍스트 기호 버튼(`+`, `✕`, `?`, `‹ ›`)은 아이콘으로 바꿨다.
- `menuButton(label, items, iconName, extraClass)`로 아이콘 전용 메뉴도 만들 수 있다.

## 화면별 변경

- **상단 바**: ghost 아이콘 버튼으로 이전·다음·도움말을 두고, 저장 상태를 `저장됨`으로 표시한다. 검수 완료는 스위치로 바꿨다.
- **상세**:
  - 문서 레일 항목은 ID와 상태 배지, 유형과 `불일치 N`으로 구성한다. 선택한 항목은 accent-soft 배경에 왼쪽 2px 바로 표시한다.
  - 이미지는 라이트테이블 배경 위에 24px 여백을 두고 얇은 테두리로 보여 준다.
  - 편집 패널 상단에 자동 저장 스위치와 `⋯` 메뉴(JSON 보기, Golden 삭제)를 두었다.
  - 섹션 헤더와 추가 버튼은 조용한 ghost 스타일로 바꾸고, 빈 섹션은 한 줄로 줄였다.
  - AO·Harness 비교 칩은 flex 레이아웃으로 바꿔 겹침을 없앴다. 삭제 아이콘은 hover할 때만 강조한다.
  - 비교 탭 필터는 개수를 함께 보여 주는 `.seg`로 바꿨다. 빈 Golden 화면은 라디오 카드와 `Golden 만들기` 버튼으로 구성했다.
- **목록**: 썸네일은 4:3 비율에 contain으로 표시한다. 상태 배지는 ID 옆에 둔다. 파일 유무는 취소선 대신 채움·외곽선 칩으로 표시하고, 오류는 `오류 N` 배지로 보여 준다.
- **업로드**: 폭 960px 단일 열 가운데 정렬로 바꿨다. 번들 구조 예시는 접히는 `<details>`에 넣고, 번들 삭제는 hover할 때만 강조되는 휴지통 아이콘으로 바꿨다.
- **문구**: 문서, 편집, JSON, 필드/그룹/표 추가, 행/열 추가, 너비 맞춤, 전체 보기, 재구성 보기, Golden 만들기로 통일했다. 본문은 `word-break: keep-all`을 적용해 한국어가 단어 단위로 줄바꿈된다.

## 진행 방식

오케스트레이터가 Playwright로 개선 전 화면을 캡처해 문제를 진단하고 스펙을 작성했다. 구현은 경량 모델 sub-agent가 맡았다. 1단계에서 토큰·공통 컴포넌트를 만들었고, 2단계에서는 상세 화면과 목록·업로드 화면을 병렬로 작업했다. 마지막으로 오케스트레이터가 캡처를 다시 비교하며 마감을 손봤다(라이트 모드 라이트테이블 밝기, 줄바꿈, 레거시 토큰 제거).

## 검증

- 백엔드 테스트 24개 통과. `frontend/js/*.js` 전체 `node --check` 통과.
- 라이트/다크 × 1920/1440에서 업로드·목록·상세(MC001, hover, 빈 Golden, 오류 문서, 도움말)를 캡처했고 콘솔 에러는 0건이었다.
- `M` 이동 플래시, 행 hover, 툴팁 위치, 목록 보기 전환, 삭제 아이콘 hover를 확인했다.
- `app.css`는 572줄에서 610줄로 늘었다. font-size는 5개 토큰만 쓴다.

## 한계

- 더미 번들에 그룹 데이터가 거의 없어 그룹 블록 화면은 캡처로 확인하지 못했다.

## 관련

- [Label Viewer 상세 검수 Workspace 개편](2026-09-28-label-viewer-review-workspace.md)
- [번들 기반 Golden Set 관리 Web App](2026-09-28-bundle-golden-viewer.md)
- [README](../README.md)
