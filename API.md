# API 계약

서버: `python3 -m backend.app --data ./storage --port 8765` (FastAPI + uvicorn). `/` 는 `frontend/index.html`, `/static/*` 는 `frontend/` 를 서빙한다.
`LABEL_VIEWER_DATABASE_URL` 이 설정되면 번들 상태, 문서 검수 상태, Golden 변경 기록, 내보내기 작업 메타데이터를 PostgreSQL 에 저장한다. 이미지·AO·Harness·Golden 원본 파일과 업로드 데이터는 계속 `DATA_DIR`(기본 `./storage`, 환경변수 `LABEL_VIEWER_DATA`) 아래 둔다. DB 모드가 아니면 기존 파일 상태와 테스트 동작을 유지한다.

기존 데이터 디렉터리를 DB 모드로 전환할 때는 앱을 멈춘 다음 `scripts/migrate_postgres.py --data <DATA_DIR> --dry-run` 으로 점검하고 `LABEL_VIEWER_DATABASE_URL=... python scripts/migrate_postgres.py --data <DATA_DIR> --configure-local` 로 가져온다. `--configure-local` 은 다음 일반 실행이 사용할 DSN 과 namespace 를 `<DATA_DIR>/_database.json` 에 권한 `0600` 으로 저장한다. 마이그레이션은 기존 파일을 제거하지 않고, 이미 DB 에 있는 행을 덮어쓰지 않으므로 재실행해도 안전하다. `--export-files` 는 앱을 중단한 상태에서 DB 메타데이터를 파일로 되돌린다. DB 에서 계속 운영한 뒤 파일 모드로 돌아갈 때는 먼저 이 명령을 완료하고 `LABEL_VIEWER_DATABASE_URL` 과 `_database.json` 을 제거한다.

앱과 PostgreSQL 을 함께 백업한다. `/data` 파일만 또는 DB dump 만 복원하면 메타데이터와 파일이 어긋날 수 있다. Compose 예제와 복구 순서는 README 의 [백업과 복구](README.md#백업과-복구)를 따른다.

## 저장 구조

```text
storage/
├── _database.json  # 선택적 PostgreSQL 로컬 설정(권한 0600)
├── bundles/{bundle_id}/
│   ├── original/      원본 이미지 (png/jpg/jpeg/tif/tiff/bmp/webp)
│   ├── preprocessed/  전처리 이미지
│   ├── ao_extract/    AO 추출 JSON 또는 UI response JSON (읽기 전용)
│   ├── ao_ui/         선택적 bbox sidecar JSON (읽기 전용)
│   ├── harness/       하네스 응답 JSON       (읽기 전용)
│   ├── golden/        정답지 JSON           (유일한 편집 대상)
│   └── _state.json    레거시/파일 모드 번들 이름·생성 시각·검수·비활성 정보
└── .cache/export-jobs/  파일 모드 내보내기 작업 상태
```

PostgreSQL 모드의 핵심 테이블:

| 테이블 | 내용 |
| --- | --- |
| `bundles` | 번들 이름·생성 시각 및 기타 상태 |
| `documents` | 문서별 검수 상태와 활성 여부 |
| `golden_history` | Golden 버전, revision, 생성 시각, 작업 |
| `export_jobs` | 내보내기 작업 상태와 결과 위치 |

파일 자체는 DB 에 넣지 않는다. Golden JSON 현재본은 `golden/` 에 두고, history 는 DB 에 스냅샷과 SHA-256 revision 을 저장한다. `_state.json` 은 DB 모드에서 정본이 아니며 migration/rollback 입력·출력으로 사용한다.

```text
storage/bundles/{bundle_id}/
├── original/      원본 이미지 (png/jpg/jpeg/tif/tiff/bmp/webp)
├── preprocessed/  전처리 이미지
├── ao_extract/    AO 추출 JSON 또는 UI response JSON (읽기 전용)
├── ao_ui/         선택적 bbox sidecar JSON (읽기 전용)
├── harness/       하네스 응답 JSON       (읽기 전용)
├── golden/        정답지 JSON           (유일한 편집 대상)
└── _state.json    {"name": "...", "created_at": "...", "review": {"<doc_id>": "done|progress"}, "disabled": ["<doc_id>", ...]}
```

`bundle_id` 는 업로드 시각 기반 slug(`20260928-2113-ab12`)다. 번들 이름은 업로드한 폴더/ZIP 이름이다.

### 업로드 파일 분류 (폴더명 유연 처리)

업로드된 각 파일의 상대 경로에서 종류(kind)를 정한다. 경로 요소(소문자) 중 하나가 아래에 맞으면 그 kind 다. 맨 먼저 맞는 규칙을 쓴다.

| kind | 폴더명 | 파일명 접미사(폴더로 못 정할 때) |
|---|---|---|
| golden | `golden`, `answer`, `answers`, `정답`, `정답지` | `.answer.json`, `.golden.json` |
| harness | `harness`, `하네스` | `.harness.json` |
| ao_extract | `ao_extract`, `ao`, `aiocr`, `extract` | `.aiocr.json`, `.ao.json` |
| ao_ui | `ao_ui`, `aiocr_ui` | `.aiocr.ui.json` |
| preprocessed | `preprocessed`, `pre`, `processed`, `전처리` | — |
| original | `original`, `origin`, `원본`, `images` | 폴더로 못 정한 이미지 |

분류되지 않은 JSON·그 밖의 파일은 무시한다. `__MACOSX`, `.` 으로 시작하는 파일도 무시한다.
폴더를 우선하므로 `ao_extract/*.aiocr.ui.json`은 AO 입력이고, `ao_ui/*.aiocr.ui.json`은 선택적 위치 sidecar다. sidecar만 있는 업로드는 문서 파일이 없어 400을 반환한다.

### 문서 ID (stem)

`파일명 → 확장자 제거 → 알려진 접미사 제거` 를 반복한다. 제거 대상: 이미지 확장자, `.json`, `.answer`, `.golden`, `.harness`, `.aiocr`, `.ao`, `.ui`, `.draft`, 이미지 뒤 `.p{n}`(페이지).
예: `ABC001.jpg`, `ABC001.png`, `ABC001.json`, `ABC001.tif.aiocr.json` → `ABC001`.
하위 폴더(문서 종류 폴더 등)는 ID 에 넣지 않는다. 같은 kind 에 같은 ID 가 둘 이상이면 뒤의 것을 `ID~2` 로 둔다.
저장 시 파일명은 `{kind}/{doc_id}{원래 확장자}` (JSON 은 `{doc_id}.json`).

## 정답지(Golden Set) 형식

정답지는 `extracted_*` 구조다. 기존 AO 응답은 이 구조를 그대로 쓰고, `documents[].result.fields/groups/tables` UI response는 읽을 때 이 구조로 변환한다. `token_bbox`는 셀의 `bbox`로 옮긴다. 업로드 원문 파일은 바꾸지 않는다.

```json
{"documents": [{
  "doc_type": "진료비영수증",
  "extracted_fields": [{"key": "발행일", "value": "20220228", "dtype": "string"}],
  "extracted_groups": [{"key": "환자정보", "fields": [{"key": "성명", "value": "홍길동", "dtype": "string"}]}],
  "extracted_tables": [{"key": "항목내역", "headers": ["항목", "금액"],
     "rows": [[{"key": "항목", "value": "진찰료", "dtype": "string"}, {"key": "금액", "value": "35000", "dtype": "int"}]]}]
}]}
```

- 셀(cell) = `{"key", "value", "dtype"}` 이 필수이고 AO 가 주는 나머지 키(confidence, masked_value …)는 있으면 보존한다.
- 문서가 여러 개(`documents[i]`)일 수 있다. 비교·편집은 `documents` 전체를 대상으로 하고 경로에 `documents[i]` 를 붙인다(아래).
- **Harness 값**: 하네스 JSON 셀의 `harness.final_value` 가 있으면 그것, 없으면 `value`. (`value` 는 AO 원래 값이다.) 하네스 셀의 `harness` 블록이 근거(evidence)다. 블록에 `master_reference:{system_id,code,name}`·`candidates` 가 있으면 비교 탭 Harness 값 셀 아래에 `원장(<code>) <name>` 보조줄로 상시 표시하고(표시 전용, 채택·채점 무관) 근거 팝오버 '마스터 대조'에도 싣는다. 명칭 셀(`EDI명칭`·`병명`)에는 하네스가 evidence 를 달지 않으므로, 백엔드가 같은 행(표) 또는 같은 문서(필드)의 코드 셀(`EDI코드`·`병명코드`) `master_reference` 를 비교 행의 `code_master_reference` 로 복사하고(`backend/compare.py` `CODE_NAME_PAIRS`), 화면은 명칭 셀 자신의 값이 없을 때 이를 같은 형식으로 보여 준다(표시 전용).
- 초안 생성:
  - `ao` → 기존 AO JSON은 복사하고, UI response는 변환한 구조를 복사.
  - `harness` → 하네스 JSON 복사 후 각 셀 `value` 를 하네스 값으로 바꾸고, 셀·표·문서의 `harness` 키와 최상위 `harness`·`meta` 를 뺀다.
  - `empty` → `{"documents":[{"doc_type":"","extracted_fields":[],"extracted_groups":[],"extracted_tables":[]}]}`
  - 셀 편집 시 없는 `dtype` 은 `"string"`.

### 셀 경로(path)

하네스 fallback 에 쓰인 표기와 같다.
- `documents[0].fields[발행일]`
- `documents[0].groups[환자정보].fields[성명]`
- `documents[0].tables[항목내역].rows[3].cells[금액]` (rows 는 0부터)

## 비교·채점

정답지를 기준으로 AO·Harness 를 셀 단위로 비교한다(`backend/compare.py`).

- 문서는 index 로 짝짓는다(`documents[i]`).
- 필드·그룹 필드: key 로 짝짓는다. 그룹 이름이 다르면 같은 key 를 다른 그룹·최상위 필드에서도 찾는다.
- 표: key 로 짝짓는다. 행은 `difflib.SequenceMatcher` 로 행 서명(정규화한 첫 열 값 + 나머지 열 앞 4글자)을 맞춰 짝짓는다. 정답에 없는 결과 행의 셀은 `EXTRA`, row 는 `+{결과 행 index}`.
- 정규화(`norm`): None→None, 공백 제거·trim, `""/"-"/"null"/"None"/"[]"` → `""`, 전각→반각(NFKC), 숫자형(쉼표·원·공백 제거 후 `-?\d+(\.\d+)?`)은 숫자로 비교(`35,000` = `35000` = `35000.0`), 날짜형(`2026-09-01`, `2026.9.1`, `2026년 9월 1일`, `20260901`)은 `YYYYMMDD` 로 비교.
- 상태:

| status | 조건 |
|---|---|
| `MATCH` | norm(정답) == norm(결과) (둘 다 `""` 포함) |
| `MISSING` | 정답 값 있음, 결과 셀 없음 또는 `""` |
| `EXTRA` | 정답 셀 없음 또는 `""`, 결과 값 있음 |
| `TYPE_MISMATCH` | 정답 dtype 이 `int`/`float`/`number` 인데 결과가 숫자가 아님(비어 있지 않음), 또는 정답은 표인데 결과는 같은 key 의 스칼라 |
| `MISMATCH` | 그 밖의 다름 |

- 결과 문서 자체가 없는 쪽(파일 없음, 또는 `documents[i]` 없음)은 비교하지 않는다: 그 쪽 status 는 `""`, 점수에서 빠진다. 결과 문서는 있는데 칸이 없을 때만 `MISSING`·`MATCH(둘 다 "")` 로 판정한다.
- 정확도 = MATCH / (전체 셀 수). 전체 셀 수 0 이면 null(화면 `—`). 원본+Golden 만 올린 번들은 AO·Harness 모두 null, 불일치 0.

## 엔드포인트

### POST /api/bundles  (multipart)
- `files`: 여러 파일. 파일명은 상대 경로(`webkitRelativePath`)를 그대로 쓴다. ZIP 이 하나면 풀어서 처리한다(zip slip 방지). UTF-8 플래그 없는 ZIP 항목 이름은 UTF-8, 안 되면 CP949로 읽고 모든 경로를 NFC로 맞춘다. 파일 수 제한 100,000개. JSON은 UTF-8(BOM 허용)·CP949를 읽는다. 손상 ZIP·저장 불가 파일명은 400.
- `name`: 선택.
- 응답: `GET /api/bundles/{id}` 와 같음. 201.

### GET /api/bundles
`[{"id","name","created_at","counts":{"docs":0,"golden":0,"reviewed":0,"error":0}}]` 최신순.

### DELETE /api/bundles/{id}
번들 폴더 삭제. 204.

### GET /api/bundles/{id}
```json
{"id":"","name":"","created_at":"",
 "docs":[{"id":"document_001",
   "has":{"original":true,"preprocessed":false,"ao_extract":true,"harness":true,"golden":true},
   "errors":["harness: JSON parse error: ..."],
   "review":"done|progress|",
   "doc_type":"진료비영수증",
   "score":{"ao":{"MATCH":10,"MISMATCH":1,"MISSING":0,"EXTRA":0,"TYPE_MISMATCH":0,"total":11,"accuracy":0.909},
            "harness":{...}},
   "mismatch":1,
   "enabled":true}],
 "summary":{"docs":0,"golden":0,"reviewed":0,"pending":0,"missing":0,"error":0,
            "score":{"ao":{...},"harness":{...}}},
 "summary_by_scope":{"enabled":{...summary 와 같은 형식...},"disabled":{...}}}
```
- `enabled`: 문서 활성 여부. 기본은 활성이며 `_state.json` 의 `disabled` 목록에 있는 문서만 false.
- `summary` 는 전체 문서, `summary_by_scope.enabled|disabled` 는 활성·비활성 문서만의 같은 집계.
- `score` 는 golden 이 있고 대상 JSON 이 있을 때만 계산, 없으면 해당 키 null.
- `mismatch` = compare 행 중 `ao_status` 또는 `harness_status` 가 `MATCH` 가 아닌(빈 문자열 제외) 행 수. 상세 화면의 비교 탭 배지·`M` 이동과 같은 기준.
- `missing` = original·ao_extract·harness·golden 중 하나라도 없는 문서 수. `error` = errors 가 있는 문서 수.
- docs 는 id 오름차순(자연 정렬).

### GET /api/bundles/{id}/docs/{doc_id}
```json
{"id":"","has":{...},"errors":[],"review":"","enabled":true,
 "pages":{"original":1,"preprocessed":0},
 "golden_revision":"SHA-256|missing",
 "golden":{...}|null, "ao":{...}|null, "harness":{...}|null,
 "compare":[{"path":"documents[0].groups[환자정보].fields[성명]","doc":0,"area":"field|group|table",
   "container":"환자정보","row":"","key":"성명","dtype":"string",
   "golden":"홍길동","ao":"홍길동","harness":"홍길동",
   "ao_status":"MATCH","harness_status":"MATCH",
   "evidence":{...harness 블록...}|null, "ao_confidence":0.99|null, "bbox":null}],
 "score":{"ao":{...}|null,"harness":{...}|null},
 "prev":"doc id|null","next":"doc id|null"}
```
- golden 이 없으면 compare 는 AO 셀 기준으로 golden=null, 상태 `""` 로 채워서 보여 준다(값 비교만).
- JSON 파싱 실패 파일은 null 이고 errors 에 기록.
- `ao_extract/`의 UI response는 `token_bbox`를 `[{"page":1,"box":[x,y,w,h]}]` 형식으로 변환한다. 별도 `ao_ui/` sidecar가 있으면 같은 stem·셀의 위치 근거로 사용한다. `has.ao_ui`는 문서 상세 응답에만 추가된다.
- `bbox`: 셀에 `bbox`(`[{"page":1,"box":[x,y,w,h]}]` 정규화 좌표)가 있으면 그대로 전달. 없으면 null. 스키마를 지어내지 않는다.

### GET /api/bundles/{id}/docs/{doc_id}/image?view=original|preprocessed&page=1
이미지 반환. TIFF/BMP 는 PNG 로 변환해 `storage/.cache/` 에 둔다(여러 페이지 TIFF 지원). 없으면 404. 헤더 `X-Pages`.

### GET /api/bundles/{id}/docs/{doc_id}/raw/{kind}
kind = `ao_extract|ao_ui|harness|golden`. 파일 그대로(파싱 실패여도 원문 텍스트). UI response도 변환 전 원문을 반환한다. 없으면 404.

### POST /api/bundles/{id}/docs/{doc_id}/golden  `{"from":"ao|harness|empty"}`
정답지가 이미 있으면 409. 원본이 없으면 404. 생성 후 `GET docs/{doc_id}` 응답.

### PUT /api/bundles/{id}/docs/{doc_id}/golden  `{"golden":{...AO 형식...}}`
형식 검증(`documents` 배열, 각 셀에 key) 실패 시 422. 임시 파일에 쓰고 rename(원자적). 응답: `GET docs/{doc_id}`.

### DELETE /api/bundles/{id}/docs/{doc_id}/golden
204.

### PUT /api/bundles/{id}/docs/{doc_id}/review  `{"review":"done|progress|"}`
`_state.json` 갱신. 204.

### PUT /api/bundles/{id}/enabled  `{"ids":["doc_id",...],"enabled":true|false}`
여러 문서의 활성 여부를 한 번에 바꾼다. 형식 오류 422, 없는 문서가 섞이면 404(아무것도 바꾸지 않음). 응답: `GET /api/bundles/{id}`.
`_state.json` 쓰기는 파일 잠금(`.state.lock`)으로 묶어 검수 상태 변경과 동시에 일어나도 서로 덮어쓰지 않는다.

### GET /api/bundles/{id}/export/bundle.zip[?doc={doc_id}|?scope=enabled|disabled]
`original/`·`preprocessed/`·`ao_extract/`·`harness/`·`golden/`·`ao_ui/` 파일을 저장 폴더 구조 그대로 묶은 ZIP. 그대로 다시 업로드할 수 있다. `doc` 이 있으면 그 문서 파일만(활성 여부 무관), 없으면 `scope`(기본 `enabled`) 문서만. 파일명 `<번들>.zip`·`<번들>-disabled.zip`·`<번들>-<문서>.zip`.
수천 건이면 수 GB가 될 수 있어 `storage/.cache/tmp/` 임시 파일에 쓴 뒤 1MB씩 내려보낸다(응답 후 삭제). PNG·JPEG·WebP 는 다시 압축하지 않는다.

### GET /api/bundles/{id}/export/golden.xlsx[?doc={doc_id}|?scope=enabled|disabled]
`doc` 이 없으면 `scope`(기본 `enabled`) 문서만 담는다.
openpyxl. 시트:
- `요약`: 문서별 id, doc_type, 검수 상태, AO/Harness MATCH·MISMATCH·MISSING·EXTRA·TYPE_MISMATCH·정확도, 마지막 행 합계.
- `필드`: 문서, 문서index, 구역(필드/그룹), 그룹, key, value, dtype.
- `표`: 표마다 헤더 행(문서·표 이름·headers…) 뒤에 행을 펼쳐 쓴다(한 행 = 표의 한 행, 열 = headers). 표 사이에 빈 줄.
- `비교`: compare 셀 전체. 문서, path, 구역, 그룹/표, 행, key, Golden, AO, AO 상태, Harness, Harness 상태.
상태 셀은 색(MATCH 초록, MISMATCH 빨강, MISSING 주황, EXTRA 보라, TYPE_MISMATCH 노랑)을 칠한다.


## 내보내기 작업과 Golden 이력 (2026-10-03)

### POST /api/bundles/{id}/exports

본문: `{"format":"xlsx|zip","scope":"enabled|disabled","ids":["doc_id",...]}`. `ids`는 생략할 수 있으며, 지정하면 활성 여부와 무관하게 그 문서만 자연 순서로 내보낸다. 중복 ID는 제거한다. 빈 선택·형식 오류는 422, 없는 문서는 404, 대기 작업 한도 초과는 429. 기본 범위는 enabled.

202 응답: `{"id":"job_id","state":"queued","completed":0,"total":200,"phase":"queued","message":"대기 중입니다.","filename":"..."}`.

### GET /api/bundles/{id}/exports/{job_id}

동일한 작업 상태를 반환한다. `state`: queued/running/ready/cancelled/failed. `completed/total`은 처리 문서 수이며 `phase=finalizing` 동안 파일을 마무리한다. 문서 처리가 100%여도 ready가 되기 전에는 다운로드할 수 없다. 상태·취소 정보는 서버 워커가 공유한다.

### DELETE /api/bundles/{id}/exports/{job_id}

취소를 요청하고 cancelled 상태를 반환한다. 생성 중 파일과 완료 파일을 삭제한다. XLSX 파일 마무리 단계의 실제 작업 중단은 저장이 반환된 뒤 확인될 수 있으며, 취소된 결과는 다운로드되지 않는다.

### GET /api/bundles/{id}/exports/{job_id}/download

ready 작업의 파일을 attachment로 반환한다. 미완료·취소·실패는 409, 만료된 파일은 410. 생성물은 24시간 뒤 후속 내보내기 요청의 정리 대상이 된다. 동시에 실행하는 작업은 데이터 경로 전체에서 2개, 대기·실행 작업 합계는 20개이다. 기존 동기 ZIP/Excel API도 유지한다.

### Golden 변경 충돌

문서 상세의 `golden_revision`은 읽어 온 Golden 원문 바이트의 SHA-256이며 없으면 `missing`이다. POST 생성·PUT 저장 본문에 `expected_revision`을, DELETE 쿼리에 같은 값을 전달한다. 현재 버전과 다르면 409이며 파일을 덮어쓰거나 삭제하지 않는다. 문서별 잠금으로 여러 워커에서 확인과 쓰기를 함께 처리한다. 기존 API 호출의 호환성을 위해 생략은 허용하지만 새 편집 화면은 항상 전달한다.

### GET /api/bundles/{id}/docs/{doc_id}/golden/history?limit=100&before={cursor}

응답: `{"items":[{"id":"history_id","created_at":"UTC ISO","action":"baseline|create|save|delete|restore","revision":"SHA-256|missing","has_golden":true}],"next_cursor":null,"golden_revision":"..."}`. 최신순이며 `next_cursor`로 이전 기록을 받는다. limit는 1~500으로 제한한다. 첫 변경 전에 기존 Golden 또는 없음 상태를 baseline으로 남긴다.

### GET /api/bundles/{id}/docs/{doc_id}/golden/history/{history_id}

해당 기록의 메타데이터와 `golden` 객체 또는 null을 반환한다. UTF-8 BOM·CP949 원문도 같은 문서 파서로 읽는다. 기록이 없으면 404.

### POST /api/bundles/{id}/docs/{doc_id}/golden/history/{history_id}/restore

본문: `{"expected_revision":"..."}`(필수). 해당 기록의 Golden 또는 삭제 상태로 복원하고 새 restore 기록을 남긴다. 응답은 갱신된 문서 상세. 현재 내용이 달라졌으면 409, 기록이나 문서가 없으면 404, 잘못된 기록은 422. Golden만 있던 문서를 삭제한 뒤에도 이력에서 복원할 수 있다. 번들 자체 삭제 시 이력도 함께 삭제된다.

### DB namespace

`LABEL_VIEWER_DB_NAMESPACE`는 같은 데이터셋을 구분하는 키다. Compose와 Kubernetes 기본값은 `label-viewer`이다. 호스트에서 이관할 때도 같은 값을 설정한다. 서로 다른 데이터셋은 다른 값을 사용한다. 값이 없으면 데이터 디렉터리의 절대 경로를 사용하므로 `./storage`와 컨테이너 `/data`가 다른 namespace가 될 수 있다. 로컬 설정 파일은 namespace도 저장하며 명시적 환경변수가 우선한다.

PostgreSQL 모드의 `/api/health`는 DB 연결을 확인하고 `{"ok":true,"storage":"postgresql"}`을 반환한다. DB 연결 실패 시 API는 503으로 응답하고 파일 상태로 대체하지 않는다. 연결 대기 기본값은 5초이며 `LABEL_VIEWER_DB_CONNECT_TIMEOUT` 또는 DSN의 `connect_timeout`으로 설정한다.
