# label_viewer

보험 OCR 결과(AO Extract·Harness)를 검수하고 정답지(Golden Set)를 만들고·고치고·비교·채점하는 독립 Web App이다. DB는 쓰지 않는다. 번들 폴더의 파일이 원본 데이터이고, 정답지도 JSON 파일로 저장한다.

흐름: 번들 업로드(폴더/ZIP) → 파일명 기준 자동 매칭 → 이미지 목록 → 정답지 생성·수정 → Golden/AO/Harness 비교 → 채점 → JSON/Excel 내보내기

## 실행

```bash
pip install -r requirements.txt
python3 -m backend.app --data ./storage --port 8765     # http://127.0.0.1:8765
pip install -r requirements-dev.txt && python3 -m pytest tests -q
```

환경변수: `LABEL_VIEWER_DATA`(데이터 경로, 기본 `./storage`), `LABEL_VIEWER_MAX_UPLOAD_MB`(기본 2048).

## 테스트용 더미 번들

```bash
python3 scripts/make_dummy_bundle.py --out samples/dummy_bundle   # samples/dummy_bundle/ 와 samples/dummy_bundle.zip 생성
```

더미 문서는 6건이다.

| 문서 | 용도 |
|---|---|
| MC001 | 금액 오독(35,000→33,000), 숫자가 아닌 금액(TYPE_MISMATCH)을 Harness가 보정, 추가 표 행, 날짜 표기 차이(일치) |
| DX002 | 병명코드를 Harness가 보정(K128→K123), Harness 때문에 틀려진 값(작성일자), 누락 필드(병명) |
| PH003 | 여러 페이지 TIFF, Harness 없음, 정답지 없음 |
| OP004 | 전처리 이미지 없음 |
| MC005 | 깨진 Harness JSON |
| DX006 | 이미지만 있음 |

## 실전형 더미 번들 (`dummy2`)

`e2e/표본결과`의 실제 문서 14건을 이미지·AO 응답·Harness 응답·정답지로 묶는다(문서 종류별 2건). 기본 `ui` 형식은 UI response를 `ao_extract/`에 넣어 Golden·Compare·bbox 입력으로 정규화하며, JSON 탭에서는 원문을 보여 준다. 파일명은 D2 별칭으로 바뀌고, 원본 파일 바이트와 JSON 내용은 그대로 복사된다. 별칭 덕분에 원본의 환자 식별자가 번들 파일명에 포함되지 않지만, 이미지와 JSON 본문에는 개인정보와 의료 정보가 남아 있다.

```bash
python3 scripts/make_dummy2.py --source-root ../e2e/표본결과 --out samples/dummy2
```

AO UI response 경로는 실행에서 자동 탐색한다. 별도 위치를 쓸 때는 `--ui-root <ao-ui-run-directory>`를 지정한다. 기본 `--ao-format ui`는 `ao_extract/`에 `.aiocr.ui.json`을 만들며, `--ao-format classic`은 `.aiocr.json` AO Extract와 선택적 `ao_ui/` sidecar를 별도 폴더에 만든다.

classic 형식은 기본 UI 번들을 덮어쓰지 않도록 별도 출력 경로를 사용한다.

```bash
python3 scripts/make_dummy2.py --source-root ../e2e/표본결과 --out samples/dummy2-classic --ao-format classic
```

기본 경로는 형제 디렉터리 `../e2e/표본결과`, AO UI response의 `../e2e/out/ao-ui-205-20260927-204626`, 출력 `samples/dummy2`이다. 다른 AO UI 실행 결과를 쓰려면 `--ui-root`를 지정한다. 기본 UI 형식 출력은 `original/`, `ao_extract/`, `harness/`, `golden/` 4개 자료 폴더다. classic 형식은 여기에 선택적 `ao_ui/` sidecar 폴더를 추가한다. 전처리 이미지는 이 표본에 없으므로 뷰어의 전처리 버튼은 비활성화된다. classic AO 파일은 변환된 Harness 입력(`.aiocr.adapted.json`)이 아니라 원본 `.aiocr.json`이고, 정답지는 원본 `.answer.json`이다. 원본 경로와 SHA-256은 `provenance.local.json`에 기록하며 ZIP에는 넣지 않는다.

이 세트는 로컬 검수용이다. 공유하거나 배포하기 전에는 이미지, AO/Harness JSON, 정답지의 식별 정보와 민감 정보를 함께 비식별화해야 한다. 상세한 샘플 목록과 생성 규칙은 [실전형 dummy2 샘플 번들](wiki/2026-09-28-realistic-dummy2.md)을 참고한다.

## 번들 구조

```text
bundle/
├── original/      document_001.png | .jpg | .tif
├── preprocessed/  document_001.png
├── ao_extract/    document_001.json | document_001.aiocr.json | document_001.aiocr.ui.json
├── ao_ui/         document_001.aiocr.ui.json (선택: 별도 UI bbox sidecar)
├── harness/       document_001.json       (또는 .harness.json)
└── golden/        document_001.json       (또는 .answer.json)
```

- **AO 추출 입력**은 `ao_extract/`에 둔다. `.aiocr.json`은 기존 AO 추출 JSON이고, `.aiocr.ui.json`은 UI response JSON(`documents[].result`)이다. UI response는 Golden·Compare·bbox에 사용할 수 있도록 AO 구조로 정규화하며, JSON 탭은 업로드 원문을 보여 준다.
- **별도 AO UI sidecar**는 선택 사항이며 `ao_ui/` 또는 `aiocr_ui/`에 둔다. stem이 같은 문서의 bbox 근거로 쓰인다. `ao_ui/`만 있는 업로드는 문서 입력으로 간주하지 않는다. `ao_extract/`의 `.aiocr.ui.json`은 유효한 AO 입력이다.
- 폴더 이름은 조금 달라도 인식한다(`원본`, `전처리`, `aiocr`, `정답` 등). 번들 파일은 stem이 같으면 같은 문서로 묶인다.
- 확장자와 알려진 접미사를 뗀 파일명(stem)이 같으면 같은 문서로 묶는다. 빠진 파일이 있어도 번들 전체가 실패하지 않고, 해당 문서에 Missing이나 오류로만 표시된다.
- 업로드한 번들은 `storage/bundles/{id}/`에 저장된다. AO와 Harness JSON은 읽기만 하고, 수정하는 것은 `golden/`뿐이다.

## 정답지 형식

정답지는 **AO 추출 결과(`ao_extract`)와 같은 형식**이다(`documents[].extracted_fields / extracted_groups / extracted_tables`). 새 정답지는 AO 복사, Harness 복사(`harness.final_value`로 값을 바꾸고 `harness` 블록은 뺌), 빈 정답지 중 하나로 만든다. 자세한 형식, 비교 규칙, API는 [API.md](API.md)에 있다.

## 비교·채점

셀 단위로 `MATCH`·`MISMATCH`·`MISSING`·`EXTRA`·`TYPE_MISMATCH`를 판정한다. 비교 전에 값을 정규화한다.

- 숫자: `35,000` = `35000`
- 날짜: `2026-09-01` = `20260901`
- 공백·전각 문자와 빈 값 표기(`-`, `null` 등)의 차이는 무시한다.

표 행은 행 서명으로 짝짓는다. 채점은 문서 단위와 번들 전체 단위로 모두 볼 수 있다.

## 상세 검수 화면

상세 화면은 문서 목록, 이미지 뷰어, Golden Set 검수 영역을 하나의 작업 공간에 배치한다. 왼쪽 목록에서 ID·유형을 검색하고 검수 상태로 거를 수 있다. 중앙에서 원본과 전처리 이미지를 확인하며, 우측의 Golden 편집 행에서 AO·Harness 값을 비교하고 바로 채택할 수 있다. 편집 행이나 비교 항목에 마우스를 올리면 비교값·상태·근거가 나타난다. 비교 데이터에 bbox가 연결돼 있으면 강조 테두리로 이미지 위치를 표시한다. 이미지 툴바의 "자동 확대"/"위치만 표시" 세그먼트(단축키 `Z`)로 hover 시 동작을 고를 수 있다. 자동 확대는 bbox 주변으로 확대하고 hover가 끝나면 이전 확대·이동 상태를 복원하며, 위치만 표시는 배율을 바꾸지 않고 강조 테두리만 그리되 bbox가 화면 밖이면 살짝 이동만 한다. 선택은 브라우저에 저장돼 다음 방문에도 유지된다. 이미지가 화면 전체를 벗어나 확대·이동된 상태면 우측 하단에 미니맵이 나타나 전체 페이지에서의 bbox 위치와 현재 보이는 영역을 보여 주며, 미니맵을 클릭·드래그하면 그 지점으로 이동한다.

우측의 비교 탭은 mismatch·missing·extra를 필터링하고 상태별 설명을 hover로 확인한다. JSON 탭은 Golden·AO Extract·Harness 원문을 접고 펼칠 수 있는 트리로 보여 주며, 별도 `ao_ui/` sidecar가 있으면 AO UI 원문 선택지도 표시한다. `ao_extract/`의 UI response는 AO Extract 원문 선택에서 정규화 전 입력 그대로 확인할 수 있다. 처음에는 사용 가능한 첫 원본을 선택하고, 키·값 검색(일치 강조), 모두 펼치기·접기, 경로 표시·복사를 지원한다. Golden 표 편집에서는 열 삭제와 행·열 추가 뒤 새 편집 위치로 포커스를 옮긴다. 재구성 보기는 Golden·AO·Harness 데이터를 HTML 또는 Markdown으로 보여 준다. 문서 목록과 이미지, 이미지와 검수 패널, 검수 패널과 재구성 뷰 사이의 경계를 끌어 크기를 조절할 수 있다. Golden 편집은 기본적으로 1.5초 뒤 자동 저장되며, JSON 보기와 Golden 삭제는 편집 패널 상단의 `⋯` 메뉴에 있다. 편집 패널 상단에는 `불일치 N · 빈 값 M` 요약과 이전/다음 불일치 버튼이 있다. 행 좌측 바는 불일치(빨강)와 Golden 빈 값(주황)을 구분하고, 빈 값 입력칸은 점선으로 표시한다. 항목 이름(key)과 그룹 이름은 실수로 바뀌지 않도록 더블클릭하거나 Enter를 눌러야 편집된다. Golden 표 셀도 불일치·빈 값을 색으로 표시하며, 셀을 선택하면 표 위 채택 바에서 AO·Harness 값을 채택할 수 있다. 표 머리글과 행 번호는 스크롤해도 고정된다. 재구성 보기 패널은 툴바의 접기 버튼으로 접을 수 있고, 접힘 상태와 높이는 브라우저에 저장된다. 사이드바·비교 탭 배지·편집 요약의 불일치 수는 모두 "AO·Harness 중 한쪽이라도 다른 항목 수"로 같은 기준이다.

문서 목록 패널 헤더와 검수 패널 탭 바에는 각각 접기 버튼이 있어(단축키 `[` `]`) 36px 세로 스트립으로 접었다가 다시 펼칠 수 있으며, 선택 상태는 브라우저에 저장돼 다음 방문에도 유지되고 접기 전 폭도 그대로 복원된다. 스플리터를 끌거나 창 크기가 바뀌거나 패널을 접고 펼칠 때 중앙 이미지는 배율(전체 보기/너비 맞춤/수동 확대) 모드에 맞춰 자동으로, 부드럽게 다시 맞춰진다.

## 단축키 (상세 화면)

| 키 | 동작 |
|---|---|
| `←` / `→` | 이전 / 다음 문서 |
| `Ctrl+S` | 저장 (자동 저장은 기본 켜짐, 1.5초) |
| `+` / `Delete` | 필드 추가 / 삭제 |
| `M` / `Shift+M` | 다음 / 이전 불일치 (편집 탭에서는 편집기 안의 필드·표 셀로, 다른 탭에서는 비교 탭 행으로 이동) |
| `O` | 원본 ↔ 전처리 이미지 |
| `Z` | bbox hover 확대 방식 전환 (자동 확대 ↔ 위치만 표시) |
| `1` `2` `3` | 재구성 보기 원본을 Golden / AO / Harness로 전환 |
| `[` | 문서 목록 패널 접기/펼치기 |
| `]` | 검수 패널 접기/펼치기 |
| `?` | 도움말 |

입력창에서 편집하는 중에는 `Ctrl+S`만 동작한다.

## 배포 (Kubernetes)

```bash
docker build -t label-viewer:latest .
kubectl apply -k deploy/k8s          # PVC(/data) + Deployment(Recreate) + Service(80→8765)
```

번들과 정답지는 PVC(`/data`)에 저장되므로 Pod가 재시작돼도 남는다. 외부 CDN을 쓰지 않으므로 폐쇄망에서도 동작한다.

## 구조

```text
backend/   app.py(라우트) · bundle.py(업로드·매칭·저장) · compare.py(정규화·비교·채점) · export.py(ZIP·Excel)
frontend/  index.html · app.css · app.js · js/(upload·list·documentRail·detail·goldenEditor·compare·imageViewer·jsonViewer·reconstruct)
scripts/   make_dummy_bundle.py(합성 자료) · make_dummy2.py(실제 E2E 자료)
tests/     test_app.py
deploy/k8s pvc · deployment · service · kustomization
```

## 보안

- 화면은 값을 `textContent`로만 넣고 `innerHTML`은 쓰지 않는다. 그래서 업로드한 값 안의 HTML·스크립트는 실행되지 않는다.
- 재구성 보기의 HTML·Markdown 렌더러도 JSON을 바탕으로 DOM을 직접 만든다.
- 업로드 경로는 검사한다. `..`, 절대 경로, zip slip은 거부한다.
