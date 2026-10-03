---
type: report
title: Agentic OCR UI response 205건 별도 수집
description: 기존 OCR 처리 이력 205건의 콘솔 extract 응답을 별도 폴더에 새로 수집하고 검증한 결과
tags: [agentic-ocr, e2e, ui-response]
status: active
---

날짜: 2026-09-27  
브랜치: 해당 없음 — 루트와 e2e는 Git 저장소가 아님  
워크트리: 해당 없음 — 저장소 코드 변경 없이 별도 산출물 폴더 사용

## 결과

- [결과 폴더](../../e2e/out/ao-ui-205-20260927-204626/): UI JSON 205건 새로 수집, 실패 0건.
- 수집 시간: 20:46~20:47 (Asia/Seoul).
- `collect_ao_ui.py`의 Console과 collect를 사용. 기존 transaction_id 재사용, force=True, view=auto. OCR 재제출 없음.
- 대응하는 외부 API JSON 사본 205건과 manifest.csv, summary.json, README.md도 저장.
- 원래 표본결과의 파일은 변경하지 않음.

## 검증

- 입력 205건의 JSON 및 식별자 존재, 트랜잭션 중복 없음은 별도 sub-agent가 읽기 전용으로 확인.
- 새 UI 응답 205건 모두 JSON 파싱, 원본 transaction_id/workflow_id 일치, documents 및 token_bbox 존재 확인.
- 복사한 API JSON은 원본과 바이트 단위 일치.
- 소견서 30, 수술확인서 30, 약제비영수증 29, 입퇴원확인서 30, 진단서 30, 진료비세부산정내역서 26, 진료비영수증 30건.

## 관련 기록

- [수집 전 현황](2026-09-27-agentic-ocr-ui-response-status.md): 기존 폴더에는 UI 응답 7건이 있었음.
- [집계 결과](../../e2e/out/ao-ui-205-20260927-204626/summary.json).
