---
okf_version: "0.2"
type: implementation
title: Label Viewer 양식 불일치 표시·문서 종류 확정·분류 채점
description: Harness 재분류 기반 양식 불일치 표시, 검수자 문서 종류 확정과 7종 양식 템플릿, 분류 채점과 오분류 필드 집계 제외, AO JSON만으로 분류를 판정할 수 있는지 e2e 205건 검증 결과
tags: [label-viewer, doc-type, reclassification, golden, harness, grading, template]
status: active
---

날짜: 2026-09-29
브랜치: `feat/doc-type-mismatch`, `feat/doc-type-grading`
워크트리: `label_veiwer/.worktrees/doc-type-mismatch`, `label_veiwer/.worktrees/doc-type-grading`

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

## 문서 종류 확정과 분류 채점 (`feat/doc-type-grading`)

검증 결과에 따라 분류 판정은 Harness 재분류와 검수자 확정에 맡기고, 키 템플릿은 양식 교체용으로만 쓴다.

| 위치 | 내용 |
|---|---|
| `backend/doctype.py` | 표준 7종 `DOC_TYPES`, AO 코드·표기 별칭(`약제영수증`→`약제비영수증`, `입원확인서`→`입퇴원확인서` 등)을 표준명으로 바꾸는 `canon()`, `classified()`, `apply_template()` |
| `scripts/make_doc_templates.py` → `backend/doc_templates.json` | e2e 정답지 210건에서 종류별로 50% 이상 나오는 필드·그룹·표 머리글로 빈 양식 생성 |
| `create_golden(..., doc_type)` | 고른 종류가 소스의 종류와 다르면 템플릿 뼈대로 바꾸고 같은 key 값(표는 같은 표의 행)을 옮긴다. 같으면 이름만 표준화 |
| Golden 생성 카드 | "문서 종류" 선택. 기본값은 Harness 재분류 제목 → AO → Harness 순(`doc_type_suggest`) |
| Golden 편집 | 문서 유형 입력칸을 7종 select로 교체(이름만 바꾸고 템플릿은 바꾸지 않음) |
| 분류 채점 | `classification = {ao, harness}`: Golden `doc_type`과 각 소스 `doc_type`의 표준명 일치 여부(모르면 None). 번들 요약에 분류 정확도, 분류 오답 문서는 해당 소스 필드 집계와 Excel 합계에서 제외. 문서별 점수는 그대로 |
| 화면·Excel | 목록 점수 카드 아래 "분류 n/m", 목록·상세에 "AO 분류 오답"/"H 분류 오답" 배지, Excel 요약에 `AO 분류`·`H 분류`(O/X) 열 |

참고: 진단서·입퇴원확인서·소견서는 정답지 스키마가 같아 템플릿도 같다. 이 셋 사이의 오분류(예: 소견서→진단서)는 템플릿 교체로는 달라지지 않고 분류 채점으로만 드러난다.

dummy2 확인: D2-DET-001은 기본 종류가 세부내역서로 잡히고, AO로 생성하면 세부내역서 템플릿이 되며 `classification.ao = False`로 AO 필드 집계에서 빠진다.

## 브라우저 확인과 수정 (`fix/class-badges`)

브라우저로 확인하니 분류 오답 배지 추가 뒤 상세 화면이 `appendChild ... not of type 'Node'` 오류로 열리지 않았다. `classBadges()`가 배지 배열을 돌려주는데 `el()`이 자식 배열을 한 단계만 펼쳤기 때문이다. `el()`이 `[children].flat(Infinity)`로 중첩 배열을 펼치게 고쳤고, 문서 유형 select가 입력칸처럼 줄 폭을 채우도록 CSS를 맞췄다. 수정 뒤 목록(분류 요약·배지)과 상세(헤더 배지, 문서 유형 select 기본값 세부내역서)가 정상 표시됨을 확인했다.

수정 뒤에도 사용자 브라우저에서 선택칸이 보이지 않았다. 정적 파일에 `Cache-Control`이 없어 브라우저가 예전 JS 모듈을 재검증 없이 쓴 것으로 보고, `/`와 `/static`에 `Cache-Control: no-cache`를 붙였다(`fix/static-no-cache`, ETag 기반 304 재검증은 유지).

## AO 문서 코드 표시 (`feat/doc-type-label`)

문서 유형이 AO 코드(`AC02922011` 등)로만 보이던 것을 `doctype.label()`로 "진료비영수증 (AC02922011)"처럼 이름과 코드를 함께 표시한다. 번들 목록·문서 사이드바·상세 헤더·Excel 요약의 `doc_type` 값에 적용했고, 상세 헤더는 Golden이 없어도 AO/Harness 유형을 보여 준다. 코드는 AO가 그렇게 분류했다는 뜻일 뿐 실제 문서 종류의 근거는 아니다.

## 비교 탭 문서 유형 행 (`feat/compare-doc-type`)

비교 탭 표 맨 위에 "문서 유형" 행을 둔다. `doc_detail.doc_type_by_source`(Golden·AO·Harness 각 `label()` 값)를 나란히 보이고, `classification` 값을 일치/불일치 배지로 표시한다. 기존 필터 규칙(`matchesFilter`)을 그대로 따라 불일치가 있으면 기본 필터에서 보이고, 모두 일치하면 "전체" 필터에서만 보인다. 필드 점수에는 들어가지 않으며 값 변경은 편집 탭 문서 유형 select에서 한다.

## 남은 과제

- Harness 재분류가 제목을 못 읽은 오분류(`kept`)는 검수자가 문서 종류를 고쳐야 드러난다.
- 올바른 양식의 Golden이 있을 때 Golden–AO 키 겹침률 보조 지표는 아직 넣지 않았다.
