---
type: implementation
title: AO–Harness Golden Set 검수 Viewer
description: 표본결과 7종 210건의 정답지·AO·하네스 값을 칸 단위로 비교하고, 이미지 위치·하네스 근거를 한 화면에서 보며 정답지를 고쳐 저장하고 Excel로 내보내는 검수 도구
tags: [label-viewer, golden-set, review, harness, evidence, bbox, excel]
status: active
---

날짜: 2026-09-28
브랜치: `feat/golden-viewer` (`dev` 기반) → `dev`·`main` 병합
워크트리: `label_veiwer/.worktrees/golden-viewer`

## 목적

작업 흐름은 AO 실행 → 하네스 검증 → 사람 검수·수정 → 정답지(Golden Set) 확정 → 결과 다운로드이다. 검수자가 원본 이미지, AO 결과, 하네스 결과, 하네스 근거를 따로 찾아다니지 않고 한 화면에서 정답을 판단해 저장할 수 있게 하는 것이 목표다.

## 사전 분석 결과

| 항목 | 실제 구조 |
|---|---|
| 문서 집합 | `e2e/표본결과/{문서종류}/` 7종 × 30 = 210건. 결과가 없는 문서가 5건 있다(세부산정내역서 4건, 약제비영수증 1건). |
| 연결 키 | 원본 이미지 파일명(확장자 포함)에 접미사를 붙인다: `.answer.json`, `.aiocr.json`, `.harness.json`, `.grade.json` |
| 정답지 | 사람이 편집하는 원본은 `_draft/{종류}/{파일}.draft.json`이고, 빌드본 `.answer.json`은 `build_answers.convert()`로 만든다. |
| AO 응답 | `.aiocr.json`(외부 API)에는 bbox가 없다. bbox는 콘솔 UI 응답 `out/ao-ui-205-*/…aiocr.ui.json`의 `token_bbox`에 있으며, 전처리 이미지 기준 정규화 좌표 `[x,y,w,h]`이다. 키 형식은 `그룹.필드`, `표[i].열`이다. |
| 하네스 근거 | 칸마다 `harness` 블록에 `tier`, `final_value`, `ao_value`, `correction_basis`, `decision_rule_no`, `evidence.rule[]`/`reread`/`master`가 있다. 페이지·bbox 정보는 없다. |
| 비교 로직 | `grade_samples.grade_file()`이 정답 행과 결과 행을 짝지어 칸마다 AO·하네스 판정을 낸다. 이미 `.grade.json`으로 저장돼 있다. |
| 전처리(크롭) 이미지 | 로컬에 없다. 기존 배치 뷰어는 API의 `/aiocr/pre-image/{key}`로 받아 왔다. |
| 기존 뷰어 | `past-data-aiocr-batch` dev의 `static/viewer`: 원본·전처리 전환, 확대·축소, 셀 hover 시 bbox 표시, 원문 JSON 패널이 있다. 정답 비교 기능은 없다. |

새 데이터 포맷은 만들지 않았다. 비교는 `grade_file()`, 정답지 빌드는 `convert()`를 그대로 불러 쓴다. 검수 상태와 수정 이력만 draft의 `review` 키에 추가했고, 빌드본의 `meta.review`에도 같은 내용이 복사된다.

## 구현

- `app.py`: FastAPI 백엔드. API 계약은 `API.md`에 있다.
  - 문서 목록·상세 조회, 이미지 반환(TIFF는 PNG로 변환해 캐시), 원문 JSON 6종 조회
  - 저장: draft 수정 → 정답지 재빌드 → 재채점 → `.grade.json` 갱신 순으로 처리한다. 첫 저장 때 draft를 `_draft/_backup/`에 한 번 백업한다.
  - 통계, Excel 내보내기(시트: 요약·문서별·검수결과·RawJSON)
- `static/`: 빌드 도구와 외부 CDN 없이 동작하는 단일 페이지. 고객사 폐쇄망에서도 쓸 수 있다.
  - 왼쪽: 이미지. 원본·전처리 전환(`o`), 페이지 이동, 휠 확대·끌어 이동, bbox 표시
  - 오른쪽: 필드 | Golden | AO | Harness | 상태 비교표. 정답과 다른 글자를 강조하고, AO 신뢰도가 낮은 칸을 표시한다.
  - hover만으로 근거 패널과 이미지 위치가 함께 바뀐다. 클릭하면 고정된다.
  - 편집: AO 채택(`1`), 하네스 채택(`2`), 직접 입력(`e`), 빈 칸 지정(`0`), 칸 검수 확인(Space), 문서 검수 완료(`c`), 저장(`s`)
  - 오류 칸 순회는 `n`/`p`이며, 문서 끝에 닿으면 오류가 있는 다음 문서로 넘어간다. 필터는 오류만·보정됨·미검수·수정됨을 제공한다.
  - 원문 JSON 서랍(`r`), 통계 화면(`#/stats`)

### 상태 분류

| 상태 | 뜻 |
|---|---|
| 일치 | AO와 하네스가 모두 정답과 같다 |
| 보정성공 | AO는 틀렸고 하네스가 맞게 고쳤다 |
| 미검출 | AO가 틀렸는데 하네스가 값을 바꾸지 않았다 |
| 보정실패 | 하네스가 값을 바꿨지만 여전히 틀리다 |
| 악화 | AO는 맞았는데 하네스가 틀리게 바꿨다 |
| 제외 | 정답지에 없는 칸이거나 개인정보 마스킹 칸이다 |

`누락`(정답은 있는데 결과가 비어 있음)과 `오탐`(정답은 빈칸인데 결과에 값이 있음)은 따로 작은 표시를 붙인다.

## 실행

```bash
cd label_veiwer
python3 app.py                  # e2e 폴더를 자동으로 찾음. http://127.0.0.1:8765
python3 app.py --e2e /path/e2e --pre-dir /path/pre-images --port 8765
python3 -m pytest test_app.py -q
```

전처리 이미지는 `--pre-dir/{문서종류}/{파일}.png`(여러 페이지면 `.p{n}.png`)에 두면 표시된다. 없으면 원본을 보여 주고, bbox는 원본 위의 근사 위치로 그린다.

## 검증

- 단위 테스트 16건 통과. 저장 테스트는 임시 복사본에서 실행하고, 실제 정답지가 바뀌지 않았는지도 확인한다.
- 완료 기준 시나리오를 실제 데이터의 임시 복사본(scratchpad)에서 브라우저로 실행했다: 문서 선택 → 전처리↔원본 전환 → `n`으로 오류 칸 이동(오류가 없는 문서는 다음 문서로 넘어감) → hover로 근거·bbox 확인 → 직접 입력 → 검수 완료 → 저장(PUT 200). draft·빌드본·`.grade.json`이 모두 갱신되고 백업이 생성됐다. 이어서 다음 오류 칸으로 이동하고 Excel을 내려받았다(검수결과 18,694행). 페이지 오류는 0건이었다.
- 전처리 이미지는 가짜 파일 한 장으로 표시와 대체 헤더(`X-Image-Fell-Back`)를 확인했다.

## 한계와 후속

- **전처리(크롭) 이미지가 로컬에 없다.** AO API의 전처리 이미지를 `--pre-dir`로 받아 두는 수집 절차가 필요하다. 그 전까지 bbox는 원본 위 근사 위치다.
- **재분류 문서 7건(835칸)**: `grade_samples`가 AO 판정을 `제외`로 두기 때문에, 이 칸들은 보정성공·보정실패로 분류된다.
- 여러 페이지 문서가 표본에 없어 페이지 이동은 실제 데이터로 검증하지 못했다.
- 대상은 `표본결과` 205→210건 세트이며, 초기 60건 세트(`정답지/*_merged.json`)는 지원하지 않는다.

## 관련

- batch 뷰어 정답지 검수 확장 (`past-data-aiocr-batch` wiki `2026-09-28-batch-golden-viewer.md`): 운영 데이터(DB·마운트) 기반 검수는 여기로 이어졌다
- AO UI response 205건 수집 (작업 공간 루트 wiki `2026-09-27-agentic-ocr-ui-response-205.md`)
- AO UI 응답의 하네스 입력 형식 (작업 공간 루트 wiki `2026-09-27-agentic-ocr-ui-harness-format.md`)
