---
okf_version: "0.2"
type: implementation
title: 상세 검수 상호작용 개선
description: bbox 위치 추적, 표 편집 포커스, 원문 JSON 탐색과 비교 상태 설명을 개선한 변경 기록
tags: [label-viewer, review, bbox, json, table-editor, comparison]
status: active
---

날짜: 2026-09-28
브랜치: `fix/bbox-hover`
워크트리: `.worktrees/bbox-hover`

## 목적

상세 검수 중 이미지와 비교 항목의 연결을 분명하게 하고, Golden 표의 구조 편집과 AO·Harness 원문 확인을 빠르게 한다.

## 동작

- 편집 행 또는 비교 항목에 hover하면 해당 bbox가 이미지에서 눈에 띄는 테두리와 반투명 채움으로 강조된다. bbox가 있는 항목으로 이동할 때 이미지가 해당 영역을 중심으로 확대되고, hover가 끝나면 기존 확대·이동 상태로 돌아간다. 페이지·이미지가 바뀔 때는 강조를 해제한다.
- AO UI sidecar는 `ao_ui/`·`aiocr_ui/` 폴더 또는 `.aiocr.ui.json` 접미사로 번들에 포함한다. 번들 내 문서 stem으로 연결하고 `result.fields`, `result.groups`, `result.tables`의 `token_bbox`에서 페이지와 정규화 좌표를 가져와 비교 행에 붙인다. AO UI sidecar는 비교 점수에 영향을 주지 않고 위치 근거만 제공한다.
- 그룹·표의 bbox는 AO UI sidecar의 그룹/테이블 이름과 필드 키를 사용해 매핑한다. 표는 정답 비교에서 정렬된 행 위치를 AO UI 행 위치에 연결한다. 일치하는 항목에 bbox가 전달되면 hover 확대와 위치 강조를 제공한다.
- Golden 표 헤더의 열 삭제 버튼은 hover 또는 키보드 포커스 시 표시된다. 열 추가·삭제와 행 추가 후 편집 위치를 새 헤더나 행으로 옮기고, 현재 스크롤 위치를 유지한다.
- Raw JSON 탭은 읽기 전용 트리 뷰를 사용한다. 객체와 배열을 접고 펼칠 수 있고, 키·값을 검색하며 선택한 원문을 복사한다. JSON이 아닌 응답은 원문 텍스트로 표시한다.
- 비교 상태 배지, 점수 범례와 필터에 상태의 의미를 설명하는 hover 도움말을 제공한다.

## 검증

- `dummy2` ZIP 업로드에서 14문서 모두 오류가 없고, 1,431개 비교 행 중 680개에 실제 bbox가 연결됐다. 14문서 모두 bbox가 있는 항목을 포함했다.
- 1920×1080 Chromium에서 실제 비교 행 hover 시 강조 영역 표시와 이미지 확대, hover 종료 후 화면 위치 복원을 확인했다. 표 열 추가·삭제와 행 추가 후 포커스, Raw JSON 검색과 비교 상태 도움말도 확인했다.
- Python 테스트 26개와 JavaScript 구문 검사, `git diff --check`를 통과했다.

## 관련

- [번들 기반 Golden Set 관리 Web App](2026-09-28-bundle-golden-viewer.md)
- [README](../README.md)
