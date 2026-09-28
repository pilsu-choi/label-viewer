# API 계약

서버: `python3 app.py [--e2e ../e2e] [--port 8765]` (FastAPI + uvicorn). `/`는 `static/index.html`을 서빙한다.

데이터 루트는 `E2E = e2e/`이고 문서 집합은 `E2E/표본결과`(7종 205건)이다. 문서는 `(folder, file)`로 식별한다. `folder`는 `진단서`·`진료비세부산정내역서` 같은 표본결과 하위 폴더이고, `file`은 확장자를 포함한 원본 이미지 파일명이다.

| 데이터 | 경로 |
|---|---|
| 원본 이미지 | `표본결과/{folder}/{file}` (tif/png/jpg, 여러 페이지 TIFF 가능) |
| 정답지 원본(편집 대상) | `표본결과/_draft/{folder}/{file}.draft.json` |
| 정답지 빌드본 | `표본결과/{folder}/{file}.answer.json` (`build_answers.convert(draft)`) |
| AO 응답 | `표본결과/{folder}/{file}.aiocr.json` |
| AO UI 응답(bbox) | `out/ao-ui-205-*/{folder}/{file}.aiocr.ui.json` (가장 최근 폴더) |
| 하네스 응답 | `표본결과/{folder}/{file}.harness.json` |
| 채점 | `표본결과/{folder}/{file}.grade.json` (`grade_samples.grade_file` 결과) |
| 전처리 이미지 | `PRE_DIR/{folder}/{file}.p{page}.png` 또는 `{file}.png` (기본 `out/ao-pre-image`, 없으면 없음) |

비교 셀은 `grade_samples.grade_file()`의 `Cell`을 그대로 쓴다. `row`가 `DC`로 시작하는 셀(Docraft 전용 행)은 제외한다.
셀 id는 `"{area}|{container}|{row}|{key}"`이다. area는 `필드`·`그룹`·`표`이고, row는 표의 정답 행 번호(1부터), `결과N`(결과에만 있는 행) 또는 `""`이다.

## 상태(status)

`ao_verdict`와 `h_verdict`는 `일치`·`불일치`·`누락`·`오검출`·`제외` 중 하나이며, 이 두 값으로 status를 정한다.

| status | 조건 |
|---|---|
| `제외` | h_verdict == 제외 |
| `일치` | AO 일치, 하네스 일치 |
| `보정성공` | AO 불일치, 하네스 일치 |
| `악화` | AO 일치, 하네스 불일치 |
| `보정실패` | 둘 다 불일치이고 ao ≠ harness (하네스가 값을 바꿨지만 틀림) |
| `미검출` | 둘 다 불일치이고 ao == harness (하네스가 못 잡음) |

`kind`는 h_verdict가 `누락`이면 `누락`, `오검출`이면 `오탐`, 그 밖에는 `""`이다.

## GET /api/docs
문서 목록(grade.json 기반, 빠름).
```json
[{"folder":"진단서","file":"x.tif","doc_type":"진단서","ao_acc":0.90,"h_acc":1.0,
  "counts":{"일치":19,"보정성공":2,"미검출":0,"보정실패":0,"악화":0,"제외":6},
  "errors":0, "review":"done|progress|", "checked":3, "edited":1}]
```
`errors`는 미검출·보정실패·악화 셀의 합이다(보정성공은 제외).

## GET /api/doc/{folder}/{file}
```json
{"folder":"","file":"","doc_type":"","pages":2,"processed":false,
 "notes":"정답지 메모","uncertain":["..."],
 "summary":{"채점칸":21,"AO정확도":0.9,"하네스정확도":1.0,"개선":2,"악화":0},
 "harness_doc":{"tier":"repaired","summary":{},"rule_results_summary":{},"review_paths":[]},
 "review":{"status":"done|progress|","checked":["<id>"],"edited":{"<id>":{"from":"","to":"","by":"ao|harness|manual","at":""}},"at":""},
 "cells":[{"id":"","area":"표","container":"병명내역","row":"1","label":"M751 / ...","key":"병명",
   "answer":"", "ao":"", "harness":"", "ao_verdict":"불일치","h_verdict":"일치",
   "status":"보정성공","kind":"","effect":"개선","source":"rule_derived","tier":"repaired",
   "masked":false,"uncertain":false,"editable":true,
   "confidence":0.99,
   "bbox":[{"page":1,"box":[0.87,0.18,0.03,0.008]}],
   "evidence":{"tier":"","correction_basis":"","decision_rule_no":"","ao_value":"","final_value":"",
               "rule":[{"rule_id":"","category":"","severity":"","result":"pass|fail|warn|not_applicable","detail":""}],
               "reread":{"status":"","value":"","engine_id":"","detail":""},"master":{"status":""}} ,
   "path":"groups[환자정보].fields[이름]"}]}
```
- `bbox`는 AO UI `token_bbox`에서 가져온 정규화 좌표 `[x,y,w,h]`이며 **전처리 이미지 좌표계** 기준이다. 원본 이미지에 겹치면 근사치다. bbox가 없으면 `[]`이다.
- `evidence`는 하네스 셀의 `harness` 블록이다. 없으면 `null`이다.
- `editable`은 정답지 draft에 해당 칸이 있으면 true이다(`결과N` 행은 false).

## GET /api/image/{folder}/{file}?view=original|processed&page=1
PNG를 반환한다(TIFF는 변환해 `.cache/`에 저장). 응답 헤더 `X-Image-View`는 실제로 반환한 종류다. processed가 없으면 original을 주고 `X-Image-Fell-Back: true`를 붙인다.

## GET /api/raw/{folder}/{file}/{kind}
`kind`는 `answer`·`draft`·`ao`·`ao_ui`·`harness`·`grade` 중 하나이며, 해당 JSON을 그대로 반환한다. 파일이 없으면 404이다.

## PUT /api/doc/{folder}/{file}
```json
{"edits":[{"id":"<cell id>","value":"새 값 또는 null","by":"ao|harness|manual"}],
 "add_rows":[{"container":"항목내역","row":"결과3","by":"ao|harness"}],
 "review":{"status":"done|progress|","checked":["<id>"]}}
```
처리 순서는 다음과 같다.
1. draft를 수정한다. `add_rows`는 결과 행의 값을 headers 순서로 모아 정답 표 끝에 붙인다.
2. 정답지 빌드본을 `convert`로 다시 쓴다. `meta.review`를 포함한다.
3. `grade_file`로 다시 채점하고 grade.json을 갱신한다.
4. 갱신된 `GET /api/doc` 응답을 반환한다.

수정 이력은 draft의 `review.edited`에 남는다. 처음 저장할 때 원본 draft를 `_draft/_backup/`에 한 번 복사한다.

## GET /api/stats?folder=
문서종류별과 전체 집계를 반환한다: 문서 수, 채점칸, AO정확도, 하네스정확도, 보정성공, 보정실패, 악화, 미검출, 누락, 오탐, 하네스 수정 칸 수(ao ≠ harness), 검수완료 문서 수.

## GET /api/export.xlsx?folder=
openpyxl로 만든 Excel을 반환한다. 시트 구성은 다음과 같다.
- `요약`: /api/stats와 같은 내용
- `문서별`: 파일별 정확도, 상태 카운트, 검수 상태
- `검수결과`: 셀 단위. 문서종류, 파일, 구역, 그룹/표, 행, 행라벨, 필드, Golden, AO, Harness, AO↔Golden, Harness↔Golden, 상태, 유형, 수정여부, 수정출처, 검수확인, Evidence(요약 문자열)
- `RawJSON`: 파일, 종류(answer/ao/harness), JSON(32,000자 단위로 열을 나눔)
