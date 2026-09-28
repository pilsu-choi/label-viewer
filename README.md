# label_veiwer

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

## 번들 구조

```text
bundle/
├── original/      document_001.png | .jpg | .tif
├── preprocessed/  document_001.png
├── ao_extract/    document_001.json       (또는 document_001.tif.aiocr.json)
├── harness/       document_001.json       (또는 .harness.json)
└── golden/        document_001.json       (또는 .answer.json)
```

- 폴더 이름은 조금 달라도 인식한다(`원본`, `전처리`, `aiocr`, `정답` 등). 폴더로 종류를 정할 수 없으면 파일명 접미사(`.aiocr.json`, `.harness.json`, `.answer.json`)로 정한다.
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

## 단축키 (상세 화면)

| 키 | 동작 |
|---|---|
| `←` / `→` | 이전 / 다음 문서 |
| `Ctrl+S` | 저장 (자동 저장은 기본 켜짐, 1.5초) |
| `+` / `Delete` | 필드 추가 / 삭제 |
| `M` | 다음 불일치 칸으로 이동 |
| `O` | 원본 ↔ 전처리 이미지 |
| `1` `2` `3` | Reconstructed View 원본을 Golden / AO / Harness로 전환 |
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
frontend/  index.html · app.css · app.js · js/(upload·list·detail·goldenEditor·compare·imageViewer·reconstruct)
scripts/   make_dummy_bundle.py
tests/     test_app.py
deploy/k8s pvc · deployment · service · kustomization
```

## 보안

- 화면은 값을 `textContent`로만 넣고 `innerHTML`은 쓰지 않는다. 그래서 업로드한 값 안의 HTML·스크립트는 실행되지 않는다.
- Reconstructed View의 HTML·Markdown 렌더러도 JSON을 바탕으로 DOM을 직접 만든다.
- 업로드 경로는 검사한다. `..`, 절대 경로, zip slip은 거부한다.
