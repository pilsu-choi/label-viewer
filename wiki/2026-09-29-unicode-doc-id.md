---
okf_version: "0.2"
type: fix
title: 한글·공백·괄호 파일명 문서의 상세 화면 400 오류 수정과 표본 205건 업로드
description: 문서 ID 검사를 경로 구분자·제어문자 차단으로 바꿔 고객사 파일명 문서를 열리게 하고, 표본 205건을 out_label_viewer 양식으로 변환해 올린 기록
tags: [label-viewer, doc-id, bugfix, golden, e2e]
status: active
---

날짜: 2026-09-29
브랜치: `fix/doc-id-unicode`
워크트리: `label_veiwer/.worktrees/doc-id-unicode`

## 증상

표본 205건 번들을 올리자 107건의 상세 화면이 `400 invalid doc_id`로 열리지 않았다. `16.소견서 1`, `[꾸미기]진단서01[꾸미기]`, `CLAIMS_1 진단서 2`, `... (1)`처럼 한글·공백·괄호·대괄호가 든 파일명이다.

## 원인과 수정

`backend/bundle.py`의 `_ID_RE`가 `[A-Za-z0-9_\-.~]`만 허용했다. 문서 ID는 업로드 파일명에서 오므로 고객사 파일명을 그대로 받아야 한다.

- `_ID_RE`를 `^[^/\\\x00-\x1f]+$`로 바꿨다. 경로 구분자(`/`, `\`)와 제어문자만 막고, `..` 차단은 그대로 둔다.
- 프런트엔드는 이미 `encodeURIComponent`/`decodeURIComponent`로 ID를 다뤄 수정이 필요 없었다.
- 테스트 `test_unicode_doc_id` 추가. 기존 경로 탐색 차단 테스트를 포함해 40건 통과.

## 표본 205건 번들

`e2e/make_label_viewer_bundle.py`로 `out_label_viewer.zip`과 같은 구조를 만든다.

| 폴더 | 원천 | 변환 |
|---|---|---|
| `original/` | `e2e/표본결과/{종류}/{원본}` | 없음 |
| `ao_extract/` | `e2e/out/ao-ui-205-20260927-204626` UI 응답 | `{"documents":[stage]}` envelope를 벗겨 stage만 저장. 참고 양식과 key 구성 동일 |
| `harness/` | `e2e/표본결과/*.harness.json`(2026-09-24, API 입력으로 돌린 결과) | API 형식(`documents[].extracted_*`)을 UI stage 양식(`result.fields/groups/tables` + `result.harness` + 최상위 `harness`)으로 옮김 |
| `golden/` | `e2e/표본결과/*.answer.json` | 없음(AI 초안, 검수 전) |

하네스 변환 방식:

- UI AO stage를 뼈대로 쓰고, 같은 자리 셀에 하네스 `harness` 블록을 붙인다. UI key 접두어(`그룹.key`, `표[i].key`)를 떼고 맞춘다.
- AO UI에서 최상위 `그룹.key`로 온 필드를 하네스가 그룹에 넣은 경우(29칸)는 하네스 구조를 따라 그룹으로 옮긴다.
- 하네스가 문서 종류를 재분류해 AO와 구조가 달라진 7건은 하네스 `extracted_*`를 UI key 양식으로 그대로 옮긴다(좌표 없음).
- `result.doc_type`은 참고 양식처럼 하네스 문서 종류 이름이다.

검증: 뷰어 채점기(`compare_bundle`)로 정답지가 있는 11,991칸의 하네스 상태를 변환 전후로 비교해 모두 같았다. 변환 전 채점에만 있던 382칸은 하네스가 넣은 빈 자리표시 필드(정답지에 없음)다.

업로드: 번들 `20260929-1627-2965`(`sample205_label_viewer`), 205건, 누락·오류 0건.

## 남은 일

- 하네스 결과는 API 입력으로 돌린 것이다. UI 응답 입력으로 하네스를 다시 돌리면 좌표 근거가 달라질 수 있다.
- 정답지 검수 전 점수의 EXTRA(AO 6,018칸)는 정답지에 없는 칸이 많아서 생긴다. 검수하면서 정답지 범위를 확정해야 한다.
