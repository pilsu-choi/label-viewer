---
type: verification
title: Agentic OCR UI response 수집 현황
description: e2e 콘솔 응답 수집 스크립트와 기존 JSON 파일 확인 결과
tags: [agentic-ocr, e2e, ui-response]
status: active
---

날짜: 2026-09-27  
브랜치: 해당 없음 — 루트와 e2e는 Git 저장소가 아님  
워크트리: 해당 없음 — 기존 파일 읽기 확인 및 루트 wiki 기록

## 확인 결과

- 수집 스크립트: [collect_ao_ui.py](../../e2e/collect_ao_ui.py).
- 기존 외부 API 결과의 transaction_id와 workflow_id로 콘솔 extract 단계 응답을 조회하고 documents에 저장한다.
- 기본 저장 위치: `e2e/표본결과/{문서종류}/{원본파일명}.aiocr.ui.json`.
- 외부 API 결과 205건 중 UI 응답 파일은 7건이다. 진료비영수증 1건, 진료비세부산정내역서 6건이며 나머지 198건의 대응 UI 파일은 없다.
- 7건 모두 JSON 파싱이 가능하고 token_bbox가 포함되어 있다(파일당 20~222개).
- 파일 수정 시각은 로컬 시간 기준 2026-09-27 16:29~16:37이다. 수정 시각만으로 최초 생성 시각을 확정하지 않는다.
- 저장 구조는 스크립트 출력과 일치한다. 이번 확인에서는 수집 스크립트를 실행하거나 API를 호출하지 않았다.

## 근거 및 범위

- [콘솔 수집 안내](../../e2e/AO_CONSOLE_BBOX.md).
- e2e 전체의 `*.aiocr.ui.json` 파일 검색 결과도 7건이다.
- 로컬 파일 확인 결과이며 NAS 또는 고객사 배포 현황은 확인하지 않았다.
