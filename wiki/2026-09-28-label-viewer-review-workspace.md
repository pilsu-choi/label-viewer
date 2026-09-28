---
okf_version: "0.2"
type: implementation
title: Label Viewer 상세 검수 Workspace 개편
description: 문서 탐색, 이미지 확인, Golden Set 편집과 비교를 한 화면에 배치해 검수 작업 흐름을 개선한 UI 기록
tags: [label-viewer, ui, review, golden-set, workspace]
status: active
---

날짜: 2026-09-28
브랜치: `feat/label-viewer-saas-ui`
워크트리: `harness-installer/.worktrees/label-viewer-saas-ui` (독립 앱 저장소 worktree)

## 목적

상세 검수 화면을 문서 이동, 원본 확인, Golden Set 수정, AO·Harness 비교가 이어지는 제품형 작업 공간으로 정리한다. 검수자가 화면을 오가거나 값을 찾아다니는 시간을 줄이고, 한 화면에서 더 많은 항목을 훑을 수 있도록 정보 밀도를 높인다.

## 화면 구성

- 좌측 문서 레일은 ID·문서 유형 검색과 상태 필터(미검수·검수 중·검수 완료·오류)를 제공한다. 현재 문서, 검수 상태, 비교 mismatch 수를 표시한다.
- 중앙 이미지 영역은 원본·전처리 보기와 페이지·확대 조작을 제공한다.
- 우측 Golden 편집은 필드·그룹·표를 편집하고, 비교 데이터가 있는 필드 행에는 AO와 Harness 값을 함께 표시한다. 값 버튼을 눌러 Golden 값에 채택할 수 있다.
- 편집 행과 비교 항목에 hover하면 AO·Harness 값과 상태, 근거를 확인할 수 있다. 항목에 bbox가 포함된 경우 이미지에서도 위치를 강조한다.
- 우측 비교 탭은 전체·불일치·누락·추가 상태로 항목을 걸러보고, 비교 값 채택과 근거 확인을 지원한다. Raw JSON은 별도 탭에 둔다.
- 우측 하단 Reconstructed View는 Golden·AO·Harness 중 하나를 HTML 또는 Markdown으로 재구성한다.
- 문서 레일과 이미지, 검수 패널의 폭 및 Reconstructed View의 높이를 경계 드래그로 조절한다.

색은 중립 톤을 기본으로 하고 상태 차이는 작은 라벨과 행 강조로 표현한다. Golden 편집은 기존 자동 저장을 유지하며 기본 대기 시간은 1.5초다.

## 단축키

| 키 | 동작 |
|---|---|
| `←` / `→` | 이전 / 다음 문서 |
| `Ctrl+S` | 저장 |
| `+` / `Delete` | 필드 추가 / 포커스된 필드 삭제 |
| `M` | 다음 mismatch 항목으로 이동 |
| `O` | 원본 / 전처리 이미지 전환 |
| `1` / `2` / `3` | Reconstructed View를 Golden / AO / Harness로 전환 |
| `?` | 단축키 도움말 |

입력 요소를 편집하는 중에는 저장 외의 전역 단축키를 처리하지 않는다.

## 검증

- 백엔드 통합 테스트 24개 통과. 샌드박스의 로컬 소켓 제한 때문에 테스트는 승인된 실행 환경에서 진행했다.
- `frontend/js/*.js` 전체 구문 검사와 `git diff --check` 통과.
- 1920×1080 Chromium에서 더미 문서 6건을 열고 문서 검색·이동, 레일 폭 조절, AO/Harness 값 채택과 저장, `M` 단축키를 확인했다. 브라우저 페이지 오류는 없었다.

## 관련

- [번들 기반 Golden Set 관리 Web App](2026-09-28-bundle-golden-viewer.md)
- [README](../README.md)
