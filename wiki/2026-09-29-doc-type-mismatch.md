---
okf_version: "0.2"
type: implementation
title: Label Viewer 양식 불일치 표시와 문서 분류 판정 검토
description: Harness 재분류 결과로 AO 오분류(양식 불일치)를 표시하고 AO 기반 Golden 생성 시 경고하는 기능, AO JSON만으로 분류를 판정할 수 있는지 e2e 205건으로 검증한 결과와 후속 제안
tags: [label-viewer, doc-type, reclassification, golden, harness, grading]
status: active
---

날짜: 2026-09-29
브랜치: `feat/doc-type-mismatch`
워크트리: `label_veiwer/.worktrees/doc-type-mismatch`

## 배경

dummy2 비교 화면에서 세부내역서(D2-DET-001·002)에 `환자성명`과 `환자정보-성명`이 같은 값으로 두 줄 나왔다.
AO가 세부내역서를 진료비영수증(`AC02922011`)으로 분류해 영수증 스키마로 추출했고, Golden과 Harness는 세부내역서 스키마를 쓴다.
키 경로가 달라 비교 행이 갈라진 것이며, Harness는 `harness.reclassification`에 제목 OCR 기반 재분류(`reextracted`)를 기록해 두었다.

## 구현

| 위치 | 내용 |
|---|---|
| `backend/bundle.py` `doc_type_mismatch()` | `harness.reclassification.documents` 중 `action`이 `reextracted`/`detected`이고 `ao_doc_type ≠ title_doc_type`인 첫 문서를 `{ao, title, title_line, reason}`로 반환. `doc_detail`, `bundle_view` 문서 항목에 `doc_type_mismatch`로 포함 |
| `frontend/js/util.js` `mismatchBadge()` | "양식 불일치" 경고 배지, 툴팁 `AO: … → 제목: … (제목줄)` |
| `list.js`, `detail.js` | 문서 목록(카드·행)과 상세 헤더에 배지 표시 |
| `goldenEditor.js` | 불일치 문서에서 Harness 옵션에 "권장" 표시, AO로 생성 시 확인창 |
| `tests/test_app.py` | `test_doc_type_mismatch`: reextracted(다름)·kept·reextracted(같음) 세 경우 검증 |

## 검증: AO JSON만으로 분류 판정이 가능한가

e2e `표본결과` 7종 중 AO 결과가 있는 205건. 폴더명을 정답 분류로 봤다. AO 오분류 8건(세부내역서→진료비영수증 6, 소견서→진단서 2).

| 방법 | 결과 |
|---|---|
| 7종 키 템플릿과 Jaccard 비교 | 오분류 8건 중 7건이 AO가 고른 양식으로, 0건이 실제 양식으로 판정. AO는 자기가 고른 양식의 스키마로 추출하므로 키 비교는 AO 판단을 되풀이할 뿐이다 |
| 채움률·신뢰도 이상치 | 오분류가 오히려 높다(채움률 중앙값 0.92 vs 정분류 0.78, 신뢰도 0.90 vs 0.79) |
| OCR 원문 | AO JSON에 OCR 원문이 없다 |
| Harness 재분류(제목 OCR) | 오분류 8건 중 7건 탐지(`reextracted` 6, `detected` 1), 놓침 1(`kept`), 오탐 1 |

결론: AO JSON만으로는 분류 정답 여부를 판정할 수 없다. 이미지나 사람처럼 AO와 독립된 근거가 필요하다.

## 후속 제안 (미구현)

1. Golden 생성 시 검수자가 문서 종류(7종)를 확정한다. 기본값은 AO 분류이고, 다르게 고르면 e2e 정답지 키로 만든 해당 양식의 빈 템플릿으로 뼈대를 바꾼다.
2. 채점에서 분류를 먼저 본다. Golden `doc_type`과 AO `doc_type`(코드→이름 매핑)을 비교해 분류 정오를 따로 집계하고, 오분류 문서는 필드 채점에서 제외하거나 별도로 집계한다.
3. 올바른 양식의 Golden이 있으면 Golden–AO 키 겹침률을 보조 지표로 쓴다. 이때는 순환 문제가 없다.
