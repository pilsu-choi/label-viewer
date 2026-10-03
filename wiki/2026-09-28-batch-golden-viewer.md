---
type: implementation
title: batch 뷰어 정답지(Golden Set) 검수 확장
description: 배치가 이미 보관한 원본·전처리 이미지, AO 결과, 하네스 결과를 batch 원장 뷰어에서 칸 단위로 비교한다. 하네스 결과를 그대로 확정하거나 사본을 고쳐 파일 폴더에 정답지로 저장하고, 통계와 Excel로 내보낸다.
tags: [past-data-aiocr-batch, viewer, golden-set, harness, review, excel, helm]
status: active
---

날짜: 2026-09-28
브랜치: `feat/golden-viewer` (`past-data-aiocr-batch` `dev` 기반, 원격 push 완료 · dev 병합은 PR로 진행 예정)
워크트리: `past-data-aiocr-batch/.worktrees/golden-viewer`

## 배경

[label_veiwer](2026-09-28-golden-set-viewer.md)는 e2e 표본 파일을 읽는 개발용 도구다. 사용자 결정(2026-09-28)에 따라 다음 방식으로 확장했다.

- 배치 인터페이스가 이미 보관한 단계별 산출물을 batch 뷰어에서 바로 보여 준다.
- **하네스 결과에 이상이 없으면 그 자체를 정답지로 쓰고**, 틀리면 사본을 고쳐 정답지로 저장한다.
- 저장 방식은 새 테이블 대신 **파일 폴더**로 정했다.

## 산출물 보관 위치 (조사 결과)

| 산출물 | 위치 |
|---|---|
| 원본 이미지 | `TBCMB8018.IMG_PATH_NM` → batch 파드 이미지 마운트(읽기 전용) |
| 전처리 이미지 | 2026-09-28부터 XVARM에서 받아 api의 `viewer.pre-image.download-path/<elementId>.png`에 저장(덮어씀). 뷰어는 api `/aiocr/pre-image`를 거쳐 받는다. 현재 `transformer_test` 브랜치에만 있다. |
| AO 결과 | `TB_AIOCR_JOB.MRG_RSLT_CONT` (여러 STEP을 합친 콘솔 UI 형식, bbox 포함, 건당 약 300KB) |
| 하네스 결과 | `TB_AIOCR_JOB.HRNS_RSLT_CONT` (입력 사본 + 칸별 `harness` 블록) |

`TB_AIOCR_JOB`은 재처리하면 덮어쓰고, 초기화하면 행이 지워진다. 그래서 정답지는 확정 시점의 사본을 따로 저장한다.

## 설계 요지

설계 원문은 `past-data-aiocr-batch/docs/design/2026-09-28-golden-viewer.md`이다.

- **원본 JSON 선택**: `HRNS_RSLT_CONT`에 결과가 있으면 그것을 쓴다. 하네스 대상이 아닌 서식이거나 실패 보고만 있으면 `MRG_RSLT_CONT`를 쓴다.
- **칸별 값**:

  | 값 | 출처 |
  |---|---|
  | AO 값 | `harness.ao_value`가 있으면 그 값, 없으면 `value` |
  | 하네스 값 | `harness.final_value`가 있으면 그 값, 없으면 `value` |
  | 정답 값 | 정답지 사본의 `value` |

- **칸 식별자**: 하네스 `field_path`와 같은 표기를 쓴다. 정답지 사본과 원본의 경로가 같으므로, 짝짓기 로직 없이 경로별로 바로 비교한다.
- **저장 구조**:

  ```
  {VIEWER_GOLDEN_PATH}/{IMG_BZ_DCD}/{IMG_BZ_KY_NO}/{IMG_ID}/
    golden.json               원본 사본, 각 칸의 value가 정답
    review.json               확정 방식(asis 그대로 확정 / edited 수정 확정 / progress 검수 중),
                              확인한 칸, 수정 이력(from→to, 방식), 원본 해시
    history/golden.<시각>.json
  ```

  - 첫 저장 때 모든 칸의 value를 하네스 값으로 채운다.
  - 저장은 임시 파일에 쓴 뒤 교체하는 방식으로 한다.
  - 원본이 재처리로 바뀌면 화면에 "원본 재처리됨"을 표시한다.
- **상태 분류**: 일치 / 보정성공 / 미검출 / 보정실패 / 악화 / 제외. 누락·오탐은 따로 표시한다. 기준은 label_veiwer와 같다.
- **새 의존성 없음**: 사내 빌드가 폐쇄망에서 오프라인으로 돌기 때문이다. Excel은 JDK zip으로 최소 xlsx를 직접 쓴다(`XlsxWriter`).

## 구현

| 구분 | 내용 |
|---|---|
| Java | `GoldenService`(칸 펼치기·비교·저장·행 추가/삭제·이력·통계·내보내기), `GoldenController`(`/viewer/api/golden/**`), `XlsxWriter`, `ViewerProperties.golden.path` |
| 화면 | `golden.html/js/css`(label_veiwer 검수 화면을 이식), `golden-stats.html`, 목록 화면 "정답지" 열과 "검수" 링크, 원장 상세의 "정답지 검수" 버튼 |
| Helm | `batch.viewer.goldenPath`(컨테이너 경로), `hostPaths.golden`. 뷰어가 켜져 있고 경로가 있을 때만 마운트한다. prod 기본값은 비어 있어 마운트하지 않는다. |
| 개발용 | `src/test/.../GoldenViewerDevServer` + `FakeLedgerViewerRepository`: DB 없이 뷰어만 띄워 화면을 점검한다. 실데이터 fixture는 저장소 밖 경로에서 실행 시에만 읽는다. |

`VIEWER_GOLDEN_PATH`가 비어 있으면 저장 API는 503을 반환한다. 상세 조회는 미리보기로 계속 동작한다.

## 검증

- 테스트: Docker `maven:3.9-eclipse-temurin-21`에서 전체 106건을 통과했다. 신규는 GoldenService 16건, XlsxWriter 4건이다.
- 실제 Java 백엔드(개발 서버와 가짜 저장소, 로컬 하네스로 만든 실구조 fixture)에 브라우저 시나리오를 돌렸다.
  - 목록 → 미리보기 → 근거 hover·bbox → 수정·저장 → 오류 칸 순회 → 다른 문서 asis 확정 → 표 행 추가·삭제 → 원문 서랍 → 통계 → xlsx 검증 순으로 진행했다.
  - 파일 저장과 이력 생성을 확인했고, 콘솔 오류는 0건이었다.

## 한계와 후속

- 전처리 이미지 API는 api `transformer_test`에만 있다. api dev에 병합하기 전에는 원본 위 근사 위치로 표시된다.
- 외부 API 형식(`documents[0].extracted_*`)은 실제 표본이 없어 구현만 하고 테스트는 하지 않았다.
- `hostPaths.golden`의 dev 기본값(`/app/past-data-aiocr/golden`)은 추정값이므로 운영 경로를 확인해야 한다.
- 정답지 삭제 버튼은 화면에 없다(API만 있음). 뷰어에 인증이 없어 수정자는 기록되지 않는다.

## 관련

- [label_veiwer Golden Set 검수 Viewer](2026-09-28-golden-set-viewer.md)
