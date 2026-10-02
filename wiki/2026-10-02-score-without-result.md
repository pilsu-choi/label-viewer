---
type: implementation
title: 결과(AO·Harness)가 없는 쪽은 채점하지 않기
description: 원본+Golden 만 올린 번들에서 결과가 없는데도 정확도(예 34%)와 불일치 수가 표시되던 버그를, 결과 문서가 없는 쪽의 셀 판정을 비우도록 고쳐 해결한 기록
tags: [label-viewer, compare, score, bug]
status: active
---

날짜: 2026-10-02
브랜치: `fix/score-without-result`
워크트리: `.worktrees/score-no-result`

## 증상

진료비세부내역서 테스트셋 200건(원본+Golden 만, 번들 `20261002-2138-3234`)에서 모든 문서에 AO·Harness 정확도와 "불일치 N"이 떴다. 예: `22Sc.의료비세부내역서_…` 129칸 중 Golden 빈칸 44칸이 MATCH, 값 있는 85칸이 MISSING → 정확도 34.11%, 불일치 85.

## 근본 원인

`backend/compare.py` `_row` 가 Golden 셀이 있으면 결과 문서가 있는지 보지 않고 `cell_status` 를 불렀다. 결과가 없으면 값이 None 이므로 "빈칸 = 빈칸" MATCH, "값 ≠ 없음" MISSING 으로 판정됐다.

## 문제 유형과 일반화 범위

"비교 대상 결과가 없는데 빈 결과와 비교해 채점함". 같은 원인을 공유하는 진입 경로:

- 결과 파일 자체가 없음(AO·Harness 둘 다, 또는 한쪽만)
- 결과 파일은 있으나 Golden 보다 문서 수가 적어 `documents[i]` 가 없음

`compare_doc` 이 문서 단위로 결과 유무(`sides`)를 `_row` 에 넘기고, 없는 쪽 status 를 `""`(비교 안 함)로 둔다. 점수(`score`)·목록 불일치 수·상세 비교 탭·편집 탭 표시가 모두 이 status 를 쓰므로 한 곳 수정으로 함께 고쳐진다. 결과 문서는 있는데 칸이 없는 경우는 기존대로 MISSING 이다(실제 누락).

Golden 이 없을 때(반대 방향)는 이미 `score=None`, `compare=[]` 로 처리돼 있었다(`test_doc_detail_without_golden_matches_list_api`).

## 변경

- `backend/compare.py`: `_row(sides=…)`, `compare_doc` 이 `(adoc is not None, hdoc is not None)` 전달
- `frontend/js/util.js`: 점수 없음 안내 "Golden이 있어야 채점됩니다" → "Golden과 결과가 모두 있어야 채점됩니다"
- `API.md` 비교·채점 절에 규칙 추가

## 테스트

- `test_golden_only_is_not_scored`: 결과 둘 다 없음 → 모든 status `""`, 점수 None
- `test_one_side_present_scores_only_that_side`: AO 만 있음 → AO 는 기존 판정(MATCH·MISSING), Harness 는 비채점
- `test_result_missing_later_document_is_not_scored`: Golden 2문서·AO 1문서 → 두 번째 문서는 AO 채점 제외
- `test_golden_only_bundle_has_no_score_or_mismatch`: 원본+Golden 업로드 → 목록·상세 점수 None, 불일치 0

수정 전 코드에서는 4개 모두 실패, 수정 후 전체 59개 통과.
