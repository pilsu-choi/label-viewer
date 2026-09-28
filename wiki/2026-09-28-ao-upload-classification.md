---
okf_version: "0.2"
type: implementation
title: AO UI response 정규화와 Raw JSON 원문 선택
description: AO Extract 폴더의 UI response를 Golden·Compare·bbox 입력으로 정규화하고 업로드 원문을 Raw JSON에서 확인하도록 개선
tags: [label-viewer, upload, ao, ui-response, sidecar, raw-json]
status: active
---

날짜: 2026-09-28
브랜치: `fix/ao-upload-raw`
워크트리: `.worktrees/ao-upload-fix`

## 입력 경로와 형식

- `ao_extract/*.aiocr.json`은 기존 AO 추출 JSON이다.
- `ao_extract/*.aiocr.ui.json`은 UI response JSON이다. `documents[].result` 데이터를 AO 추출 구조로 정규화한 뒤 Golden·Compare·bbox 흐름에 사용한다.
- 별도 `ao_ui/*.aiocr.ui.json` 또는 `aiocr_ui/*.aiocr.ui.json`은 선택적인 위치 근거 sidecar로 취급한다. 같은 stem의 문서에 bbox 정보를 연결하고 추출 값이나 점수에는 관여하지 않는다.

파일 접미사만으로 `.aiocr.ui.json`을 항상 sidecar로 분류하지 않는다. 상위 `ao_extract/` 경로에서는 AO 추출 입력으로 사용하고, 별도 `ao_ui/`·`aiocr_ui/` 경로에서만 보조 sidecar로 사용한다. `ao_extract/` UI response는 유효한 AO 입력이므로 sidecar 전용 업로드 제한과 혼동하지 않는다.

## Raw JSON 원문 선택

Raw JSON 탭에서 Golden, AO Extract, Harness 원문을 선택할 수 있다. AO Extract 입력이 UI response 형식이면 정규화된 데이터가 아니라 업로드된 `documents[].result` 원문을 표시한다. 별도 `ao_ui/` sidecar가 있으면 AO UI 선택지를 추가한다. 화면을 열 때 사용 가능한 첫 원문을 기본 선택하고, 원문은 기존 JSON 트리 검색·접기·복사 기능으로 확인한다.

## dummy2 형식

`scripts/make_dummy2.py`의 기본 `--ao-format ui`는 `.aiocr.ui.json` 파일을 `ao_extract/`에 배치한다. `--ao-format classic`을 지정하면 기존 `.aiocr.json`을 `ao_extract/`에 두고 UI response를 선택적 `ao_ui/` bbox sidecar로 추가한다. 따라서 기본 출력은 원본·ao_extract·harness·golden 네 자료 폴더이고, classic 형식은 `ao_ui/`를 더해 다섯 폴더가 된다.

## 검증

- UI 형식 `dummy2.zip` 업로드에서 14문서 모두 정상적으로 묶였고 오류가 없었다. 비교 행 1,433개 중 682개에 bbox가 있었다.
- UI response 파일 하나만 `ao_extract/`에 올리면 문서 1건이 생성되고, Raw JSON 탭에서 AO Extract가 자동 선택돼 원문을 탐색할 수 있다.
- 1920×1080 Chromium에서 Raw JSON 원문의 `result` 검색, 비교 행의 bbox 강조·확대·복원을 확인했다.
- Python 테스트 31개와 JavaScript 구문 검사, `git diff --check`를 통과했다.

## 관련

- [README의 번들 구조와 상세 검수 화면](../README.md)
- [상세 검수 상호작용 개선](2026-09-28-review-inspection-interactions.md)
