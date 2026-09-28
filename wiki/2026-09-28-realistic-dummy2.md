---
okf_version: "0.2"
type: dataset
title: 실전형 dummy2 샘플 번들
description: e2e 표본결과에서 문서 종류별 실제 이미지와 AO·Harness·정답 JSON 2건씩을 골라 AO UI bbox sidecar와 함께 로컬 검수용 번들로 만드는 규칙과 개인정보 취급을 기록한다.
tags: [label-viewer, dummy-data, e2e, ao, harness, bbox, privacy]
status: active
---

날짜: 2026-09-28
브랜치: `fix/bbox-hover`
워크트리: `.worktrees/bbox-hover`

## 목적

기존 `make_dummy_bundle.py`는 OCR 화면 흐름과 값 교정 상태를 보여 주는 합성 문서를 생성한다. `dummy2`는 실제 E2E 문서의 이미지와 AO·Harness·정답 데이터를 사용해 화면의 실제 JSON 구조와 스캔 이미지를 살펴보는 로컬 검수 자료다.

## 샘플 구성

소스는 `../e2e/표본결과/<문서 종류>/`다. 각 항목은 원본 이미지, 같은 stem의 `.aiocr.json`, `.harness.json`, `.answer.json`이 모두 존재하는 quartet이다. AO 자료는 Harness 요청을 위해 변환된 `.aiocr.adapted.json`이 아니라 원본 AO 응답 `.aiocr.json`을 쓴다. 별도 AO UI run 디렉터리의 `.aiocr.ui.json`이 있는 항목은 함께 복사한다. UI sidecar는 셀 bbox를 제공하며 Golden/AO/Harness 비교값이나 점수에 관여하지 않는다. 아래 파일명은 원본 위치를 다시 찾을 수 있도록 기록한다.

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

생성기는 `e2e/out/ao-ui-205-20260927-204626`을 기본 sidecar 위치로 탐색한다. 경로를 바꾸려면 `--ui-root <ao-ui-run-directory>`를 지정한다. sidecar를 제외하려면 빈 디렉터리를 `--ui-root`로 지정한다.

생성 폴더에는 `original/`, `ao_extract/`, `harness/`, `golden/`와 sidecar가 있는 문서의 `ao_ui/`가 있고 ZIP은 `samples/dummy2.zip`이다. 원본 내용은 수정하거나 재인코딩하지 않고 바이트 단위로 복사한다. `D2-<문서종류코드>-<순번>` 별칭을 사용하며 파일 확장자와 데이터 종류 접미사를 보존해 이미지와 JSON이 stem으로 묶인다. 원본의 상대 경로와 각 파일 SHA-256은 로컬의 `provenance.local.json`에만 기록하고 번들 ZIP에서는 제외한다.

E2E 표본에는 전처리 이미지가 없어 이 번들은 원본 이미지 보기만 제공한다.

## 검증

- 7종류 × 2건 = 14문서, 이미지·AO·Harness·답안 56개 파일과 사용 가능한 AO UI sidecar를 생성한다. 출력 파일의 SHA-256은 원본과 같고 로컬 provenance는 ZIP에서 빠진다.
- 생성 ZIP을 앱의 업로드 처리에 넣어 14문서 모두 원본 이미지·AO·Harness·Golden이 짝지어지고 오류가 없음을 확인했다. AO 기준 비교 행 1,431개가 생성됐고 14문서 모두 양쪽 점수가 계산됐다.
- 1920×1080 Chromium에서 실제 이미지, 14건 문서 레일과 `D2-REC-001`의 비교 행 272개를 확인했다. 페이지 오류는 없었다.
- 실제 표본의 긴 비교 목록이 상세 화면 전체 높이를 늘리는 현상이 드러나, 상세 화면 높이를 뷰포트에 고정하고 비교 패널 안에서 스크롤되도록 CSS를 보정했다.

## 개인정보 취급

샘플은 실제 의료 이미지다. 이미지 픽셀과 AO·Harness·정답 JSON에는 환자 이름, 생년월일, 의료기관, 진료 내용, 금액 등 민감 정보가 포함될 수 있고, JSON에는 거래·문서·감사 ID도 있다. `value`와 `predicted_value`가 모두 가려진다고 보장할 수 없다.

따라서 이 번들은 로컬 개발 및 권한이 있는 내부 검수에만 사용한다. 외부 공유나 제품 배포 전에는 이미지와 세 JSON을 함께 비식별화하고, 거래·문서 식별자와 로컬 provenance도 제거하거나 새로 생성한다. 별칭은 파일명 노출을 줄이는 조치일 뿐 익명화가 아니다.

## 관련 자료

- [README의 dummy2 안내](../README.md#실전형-더미-번들-dummy2)
- [기존 합성 dummy 번들 구현 기록](2026-09-28-bundle-golden-viewer.md)
