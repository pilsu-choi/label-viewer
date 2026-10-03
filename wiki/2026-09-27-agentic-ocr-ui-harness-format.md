---
type: report
title: Agentic OCR UI 응답의 하네스 입력 형식 검증
description: 205건 UI 응답 봉투의 하네스 호환성, 변환과 실제 접수·처리 검증
tags: [agentic-ocr, e2e, harness, ui-response]
status: active
---

날짜: 2026-09-27  
브랜치: 해당 없음 — 루트와 e2e는 Git 저장소가 아님  
워크트리: 해당 없음 — 기존 산출물 폴더에 변환본 추가

## 결론

- [원본 UI 수집 결과](../../e2e/out/ao-ui-205-20260927-204626/)의 `*.aiocr.ui.json`은 하네스에 직접 제출할 수 없다. 최상위 `documents` 배열 때문에 외부 API 형식으로 감지되고, 내부 UI `result.fields/groups/tables`는 평탄화되지 않는다. 실측 한 건에서 필드 0개를 확인했다.
- 하네스는 단일 UI 단계 응답(`run_id`, `file_id`, `result`)을 받는다. AO 7종 코드형 `result.doc_type`도 기존 [어댑터](../../e2e/adapt_aiocr.py)의 한글 이름으로 바꿔야 규칙에 매핑된다.
- [변환 스크립트](../../e2e/prepare_ao_ui_harness.py)를 만들고 [제출용 JSON](../../e2e/out/ao-ui-205-20260927-204626/harness-input/) 205건을 생성했다. 원본 이미지 205개는 각 JSON 옆에 심볼릭 링크로 연결했다. 좌표와 추출값은 유지했다.

## 검증

- 205건 모두 하네스의 UI 형식 탐지, 이미지 포함 접수 검증, 문서 1건 평탄화, 문서 유형 매핑을 통과했다. 필드 17,534개가 읽혔다.
- 7개 문서 종류에서 각 1건씩 로컬 하네스 파이프라인을 실행해 결과의 harness 채널 생성을 확인했다.
- 로컬 마스터 DB와 재판독 서비스가 없어 실제 운영 판정의 완전성은 이 검사 범위에 포함되지 않는다.
- 스크립트 재실행 예: `python3 e2e/prepare_ao_ui_harness.py e2e/out/ao-ui-205-20260927-204626 e2e/out/ao-ui-205-20260927-204626/harness-input`.
