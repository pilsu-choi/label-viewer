---
type: feature
title: 진단서4종 진단.진료소견 추가와 약제영수증 키 변경 요구사항 반영
description: 1005 요구사항 3건 중 진료소견 추가를 label_veiwer·synthetics에 구현하고 약제 키 변경 2건은 구조 결정 대기로 보류
tags: [synthetics, label-viewer, schema, 진단서, 약제비영수증]
status: active
---

날짜: 2026-10-05  
브랜치: synthetics `feat/clinical-opinion`, label_veiwer dev 병합 완료(`feat/clinical-opinion` 계열)  
워크트리: `synthetics/generator/.worktrees/clinical-opinion`

## 요구사항

출처: `harness-v2/docs/requirements/진단서4종_약제영수증_추출_항목_수정_1005/` (`context.md`, `20261003-2036_진단서4종_추출스키마.json`, `20261003-2036_약제비영수증_추출스키마.json`).

1. 진단 그룹에 `진료소견` 추가.
2. 약제영수증 `소득공제대상 총수납액` → `수납금액`.
3. 약제영수증 `진료비내역 환자수납액` → `비급여`.

## 영향 조사

5개 저장소(harness-v2, Docraft, harness-installer, label_veiwer, synthetics/generator)의 동작 코드에 '총수납액'·'환자수납액'·'진료소견' 문자열은 없다. 코드·테스트·합성·정답지는 구 AO 평탄 키(`소득공제대상액-수납금액`, groups[진료비내역] 평탄 키, groups[진단] 진단일·최종진단·임상적추정)를 쓴다. 첨부 스키마는 신규 그룹/표 구조(`소득공제대상.수납금액`, `진료비내역[i].비급여`, `진단.진료소견`)다. 신규 구조의 실제 AO 출력 샘플은 저장소에 없다.

## 처리

- 1번은 구조와 무관한 추가라 구현 완료(label_veiwer, synthetics).
- 2·3번은 구조 결정(신규 구조 수용 vs 구 AO 키 호환)이 필요해 보류.

## 보류 항목의 영향 위치

- harness-v2: `src/mlife_harness/rulesets/shared/receipt_items.yaml:75-76`(약제 required_keys), `rulesets/shared/schema.yaml:55`, `normalizer/coverage.py:277-286`(`_unfilled` 매칭), `tests/unit/test_schema_declarations.py`.
- Docraft: `backend/doctypes.py:199`, `backend/rulesets/shared/receipt_items.yaml:75-76`, `backend/rulesets/rules.yaml:94`. `_MEDICAL_FIELDS`(`doctypes.py:61-80`)에 진료소견 재판독을 추가할지 결정 필요.
- harness-installer: 서브모듈 포인터 갱신만.
- 정답지 데이터셋(`datasets/약제비영수증_테스트셋/golden`, e2e 표본 결과)도 구 키.
- 진료소견은 채움률 근거가 없어 required_keys에 넣지 않는다.

## label_veiwer

- `backend/doc_templates.json` 4종 진단 그룹에 진료소견 추가.
- `backend/doctype.py` `REQUIRED_FIELDS`: 표본에 없어도 스키마 필드를 양식에 넣는다.
- `scripts/make_doc_templates.py`가 재생성 시 반영.
- `tests/test_doctype.py` 14건, 전체 153 passed.
- 커밋 3ab9808·39733bb → dev 병합 f146d05.

## synthetics

- 근본 원인: profile schema에 키가 없고, 소견 문단이 context(`pii.clinical.paragraphs`)로만 렌더되어 정답 경로·`label_boxes`가 없었다.
- 문제 유형: 인쇄 서술 필드의 정답 경로 미바인딩.
- 변경: `profile/2026-10-03/schema.json`·`profile.json`, `synth/content.py`(문단을 공백 한 칸으로 이어 `groups.진단.진료소견`), `templates/structures/certificate.html.j2`·`opinion.html.j2`, `templates/진단서/sectioned_emr/family.yaml`(path 바인딩).
- 인쇄되는 서식: 진단서 7 family 전부, 소견서 5 family(emr_compact 제외).
- 소견 칸이 없어 `""`: 소견서 emr_compact('내 용'), 수술확인서 6, 입퇴원확인서 6.
- 판단 필요: '향후 치료 의견'·'치료소견'은 소견 칸으로 간주, '내 용' 등은 `""` 처리. 문단 사이 빈 줄은 사라진다.
- 테스트: `tests/test_clinical_opinion.py` 30건. 의도된 변경에 따라 해시 기준값 갱신(`test_content_catalog` 12건은 새 키 제거 시 옛 해시와 일치함을 확인, `composition-parity.json` 12건), `test_certificate_layout` 조정.
- 커밋: `feat/clinical-opinion` 1b70df6. 전체 회귀 결과는 병합 기록에 추가.
