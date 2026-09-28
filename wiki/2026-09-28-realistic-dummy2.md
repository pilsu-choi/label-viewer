---
okf_version: "0.2"
type: dataset
title: 실전형 dummy2 샘플 번들
description: e2e 표본결과에서 문서 종류별 실제 이미지와 AO·Harness·정답 JSON 2건씩을 골라 기본 UI response 형식 또는 classic AO와 bbox sidecar 형식의 로컬 검수용 번들을 만드는 규칙과 개인정보 취급을 기록한다.
tags: [label-viewer, dummy-data, e2e, ao, harness, bbox, privacy]
status: active
---

날짜: 2026-09-28
브랜치: `fix/bbox-hover`
워크트리: `.worktrees/bbox-hover`

업데이트: 2026-09-28 · `fix/ao-upload-raw` · `.worktrees/ao-upload-fix`

## 목적

기존 `make_dummy_bundle.py`는 OCR 화면 흐름과 값 교정 상태를 보여 주는 합성 문서를 생성한다. `dummy2`는 실제 E2E 문서의 이미지와 AO·Harness·정답 데이터를 사용해 화면의 실제 JSON 구조와 스캔 이미지를 살펴보는 로컬 검수 자료다.

## 샘플 구성

소스는 `../e2e/표본결과/<문서 종류>/`이며 실제 AO UI response는 별도 run 디렉터리에서 가져온다. 기본 `ui` 형식은 `.aiocr.ui.json`의 `documents[].result`를 `ao_extract/`에 저장하고, 앱이 AO 비교 구조로 정규화한다. `classic` 형식은 원본 `.aiocr.json`을 `ao_extract/`에 두고 UI response를 선택적 `ao_ui/` bbox sidecar로 둔다. 두 형식 모두 Harness 요청을 위해 변환된 `.aiocr.adapted.json`은 사용하지 않는다. 아래 파일명은 원본 위치를 다시 찾을 수 있도록 기록한다.

| 문서 종류 | 샘플 A | 샘플 B | 다양성 |
|---|---|---|---|
| 진료비영수증 | `20230127_202555.jpg` | `SA2019123048574_301912301635140g.tif` | JPEG와 작은 TIFF, Harness 불확정 사례와 pass 사례 포함 |
| 진료비세부산정내역서 | `3022030712433802-1.png` | `SA2020010683597_3020010610592200.tif` | 표 중심 대용량 JSON과 소형 TIFF; AO/Harness 비교에서 테이블 차이가 크게 나타나는 사례 포함 |
| 진단서 | `[꾸미기]진단서07[꾸미기].jpg` | `20230228095647474003.tif` | 사진 JPEG와 TIFF, Harness 보정과 미해결 케이스의 비교 |
| 소견서 | `20230228172033976130.tif` | `신한life_test_220316_소견서4.png` | 서로 다른 입력 세트의 TIFF/PNG 및 AO/Harness 값 차이 |
| 수술확인서 | `신한life_test_220316_수술확인서20.png` | `20230621_130741.jpg` | PNG와 카메라 JPEG, AO/Harness 교정 차이를 비교하기 위한 조합 |
| 입퇴원확인서 | `20230621_140539.jpg` | `20230228155325819098.tif` | JPEG와 TIFF 및 Harness 보정/미해결 케이스 비교 |
| 약제비영수증 | `image_47.tif` | `1546586316234823.jpg` | TIFF와 JPEG, 필드 비교가 일치하는 정상 대조군 포함 |

샘플은 모두 이미지·AO·Harness·정답 파일이 실제 존재하는 것을 확인했다. 파일명에 환자 이름이 직접 드러나는 사례는 피했지만 파일명 별칭만으로 비식별 처리되지는 않는다.

## 생성 결과와 재현

```bash
python3 scripts/make_dummy2.py --source-root ../e2e/표본결과 --out samples/dummy2
```

생성기는 `e2e/out/ao-ui-205-20260927-204626`을 기본 AO UI response 위치로 탐색한다. 경로를 바꾸려면 `--ui-root <ao-ui-run-directory>`를 지정한다. 기본 생성은 `--ao-format ui`이며, 기존 AO JSON과 분리 sidecar가 필요하면 `--ao-format classic`을 사용한다.

기본 UI 형식의 생성 폴더에는 `original/`, `ao_extract/`, `harness/`, `golden/`이 있고 ZIP은 `samples/dummy2.zip`이다. `classic` 형식은 UI response가 있을 때 `ao_ui/`를 추가한다. 원본 내용은 수정하거나 재인코딩하지 않고 바이트 단위로 복사한다. `D2-<문서종류코드>-<순번>` 별칭을 사용하며 파일 확장자와 데이터 종류 접미사를 보존해 이미지와 JSON이 stem으로 묶인다. 원본의 상대 경로와 각 파일 SHA-256은 로컬의 `provenance.local.json`에만 기록하고 번들 ZIP에서는 제외한다.

E2E 표본에는 전처리 이미지가 없어 이 번들은 원본 이미지 보기만 제공한다.

## UI 형식 검증

- 기본 생성 ZIP에는 14문서의 이미지·AO UI response·Harness·정답 56개 파일이 있다. 로컬 생성 폴더의 각 파일은 ZIP과 바이트 단위로 일치한다.
- 업로드 결과 14문서 모두 원본·AO·Harness·Golden으로 묶였고 오류는 없다. 비교 행 1,433개 중 682개에 실제 bbox가 연결됐다.
- 1920×1080 Chromium에서 AO Extract Raw JSON에 업로드 원문의 `result`가 표시되고, 비교 행 hover 시 bbox 강조·확대·복원이 동작했다.
- Python 테스트 31개, JavaScript 구문 검사, `git diff --check`를 통과했다.

## 개인정보 취급

샘플은 실제 의료 이미지다. 이미지 픽셀과 AO·Harness·정답 JSON에는 환자 이름, 생년월일, 의료기관, 진료 내용, 금액 등 민감 정보가 포함될 수 있고, JSON에는 거래·문서·감사 ID도 있다. `value`와 `predicted_value`가 모두 가려진다고 보장할 수 없다.

따라서 이 번들은 로컬 개발 및 권한이 있는 내부 검수에만 사용한다. 외부 공유나 제품 배포 전에는 이미지와 세 JSON을 함께 비식별화하고, 거래·문서 식별자와 로컬 provenance도 제거하거나 새로 생성한다. 별칭은 파일명 노출을 줄이는 조치일 뿐 익명화가 아니다.

## 관련 자료

- [README의 dummy2 안내](../README.md#실전형-더미-번들-dummy2)
- [기존 합성 dummy 번들 구현 기록](2026-09-28-bundle-golden-viewer.md)
