---
okf_version: "0.2"
type: implementation
title: 전체 묶음 ZIP 내보내기
description: 번들·문서 내보내기를 Golden JSON만에서 원본·전처리 이미지와 AO·Harness·Golden JSON 전체 묶음 ZIP으로 바꾼 기록
tags: [label-viewer, export, zip]
status: active
---

날짜: 2026-09-30
브랜치: `feat/bundle-export`
워크트리: `label_veiwer/.worktrees/bundle-export`

## 배경

번들 상세(목록) 화면 내보내기는 `golden/*.json`만, 문서 상세 화면은 편집 중인 Golden JSON 한 파일만 받을 수 있었다. 검수 결과를 넘길 때 원본·전처리 이미지와 AO·Harness 결과를 함께 받아야 한다.

## 변경

| 위치 | 내용 |
|---|---|
| `backend/export.py` | `export_golden_zip` → `export_bundle_zip(data_dir, bundle_id, doc_id=None)`. `original`·`preprocessed`·`ao_extract`·`harness`·`golden`·`ao_ui` 폴더를 저장 구조 그대로 묶고, `doc_id`가 있으면 파일 stem이 같은 것만 넣는다 |
| `backend/app.py` | `GET /export/golden.zip` → `GET /export/bundle.zip[?doc=]`. 파일명 `<번들>.zip`·`<번들>-<문서>.zip`, 한글 문서 ID를 위해 `filename*=UTF-8''` |
| `frontend/js/list.js` | 내보내기 메뉴 `Golden ZIP` → `전체 묶음 ZIP` |
| `frontend/js/detail.js` | 클라이언트 Golden JSON 다운로드 → 이 문서의 `전체 묶음 ZIP`. 저장하지 않은 Golden 변경이 있으면 막고 안내 |
| `API.md`, `README.md` | 엔드포인트·흐름 갱신 |

## 결정

- **폴더 구조 유지**: ZIP 안 폴더명이 업로드 분류 키와 같아 받은 ZIP을 그대로 다시 업로드할 수 있다.
- **Golden JSON 단독 다운로드 제거**: 같은 파일이 묶음에 들어 있어 기능이 겹친다. 서버 파일 기준이라 미저장 편집은 저장 후 내보내게 한다.
- `_state.json`(검수 상태)은 넣지 않는다. 검수 상태는 Excel `요약` 시트에 있다.

## 검증

- `pytest` 40개 통과(`test_export_zip`에 전체·문서 단위 검사 추가).
- 실제 번들 `20260929-1124-82d6`: 전체 61파일, 문서 `2025010109444002` → `original/.tif`·`preprocessed/.png`·`ao_extract`·`harness` 4파일(Golden 없음).
