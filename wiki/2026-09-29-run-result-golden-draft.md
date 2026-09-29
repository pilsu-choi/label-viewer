---
okf_version: "0.2"
type: fix
title: 실행 응답 형식 하네스·AO JSON에서 Golden 초안이 비던 문제 수정
description: documents 없이 result.fields/groups/tables만 있는 하네스·AO 출력을 canonical extracted_* 스키마로 정규화해 Golden 초안·비교·분류가 동작하게 한 기록
tags: [label-viewer, golden, harness, ao, bugfix]
status: active
---

날짜: 2026-09-29
브랜치: `fix/run-result-format`
워크트리: `label_veiwer/.worktrees/run-result-format`

## 증상

`out_label_viewer.zip`(14건, original·preprocessed·ao_extract·harness)을 올리고 하네스 기준 Golden 초안을 만들면 빈 초안이 나왔다. 문서 종류·분류·점수도 모두 비어 있었다.

## 원인

새 하네스·AO 출력은 실행 응답 형식이다.

```json
{"stage": "extract", "run_id": "...", "harness": {...}, "result": {"doc_type": "...", "fields": [], "groups": [], "tables": []}}
```

뷰어는 `{"documents": [{"extracted_fields": ...}]}`와 `{"documents": [{"result": ...}]}`(AO UI 응답)만 읽었다. 최상위 `result`는 인식하지 못했고, 하네스 JSON은 정규화 자체를 거치지 않았다. zip의 `__MACOSX`·`._*` 항목은 이미 무시되고 있어 원인이 아니었다.

## 조치

- `canonical_ao` → `canonical_doc`: 최상위 `result`가 있고 `documents`가 없으면 `documents: [{"result": ...}]`로 감싼 뒤 기존 변환을 탄다. 문서 단위 `result.harness`는 보존한다.
- `load_ao_extract` → `load_doc_json`: ao_extract·harness·golden 모두 같은 로더를 쓴다. 업로드 원본 파일은 바꾸지 않는다.
- 회귀 테스트 `test_run_result_harness_without_documents_creates_golden_draft` 추가.

## 검증

- 업로드 zip 14건 전부 하네스·AO 초안 생성: 문서 종류 `진료비영수증`, fields 5·groups 3·tables 1, 초안에 `harness` 블록 없음. 하네스가 보정한 셀 때문에 일부 문서는 AO 정확도 0.99대.
- `pytest` 39건 통과.
