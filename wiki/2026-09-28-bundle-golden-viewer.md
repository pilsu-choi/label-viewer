---
type: implementation
title: 번들 기반 Golden Set 관리 Web App
description: 번들(폴더/ZIP)을 업로드하면 파일명으로 문서를 자동 매칭하고, AO 추출 결과 형식의 정답지를 만들고·고치고·비교·채점하는 독립 앱. DB 없이 파일 시스템만 쓰고 K8s PVC로 배포한다.
tags: [label-viewer, golden-set, bundle, compare, scoring, k8s, dummy-data]
status: active
---

날짜: 2026-09-28
브랜치: `feat/bundle-viewer` (`dev` 기반) → `dev` 병합
워크트리: `label_veiwer/.worktrees/bundle-viewer`

## 배경

`PRD.md` 요구사항에 맞춰 만든 앱이다. 이전 뷰어([2026-09-28-golden-set-viewer](2026-09-28-golden-set-viewer.md))는 `e2e/표본결과`의 폴더 구조와 `grade_samples.py`에 묶여 있었다. 그래서 다른 번들을 올리면 쓸 수 없었다. PRD는 번들 업로드, stem 매칭, 독립 실행, K8s 배포를 요구하므로 기존 코드(`app.py`, `static/`, `test_app.py`)를 지우고 새로 구현했다.

## 결정 사항

| 항목 | 결정 | 이유 |
|---|---|---|
| 정답지 형식 | AO 추출 결과와 같은 형식(`documents[].extracted_fields/groups/tables`) | 사용자 요구. 형식을 하나로 맞춰 AO·Harness 복사로 바로 초안을 만들 수 있다 |
| Harness 값 | 셀 `harness.final_value`, 없으면 `value` | 실제 하네스 출력에서 `value`는 AO 원래 값이다 |
| 근거(Evidence) | 하네스 셀의 `harness` 블록(tier, correction_basis, evidence.rule/reread/master)을 그대로 보여 준다 | 스키마를 지어내지 않는다. bbox는 셀에 `bbox`가 있을 때만 쓴다 |
| 검수 상태 | `_state.json`에 따로 저장 | 정답지 JSON에는 AO 형식 외의 키를 넣지 않는다 |
| 비교 규칙 | 앱 안의 `compare.py`로 따로 구현(숫자·날짜·공백 정규화, difflib 행 정렬) | 독립 앱이어야 하므로 `e2e/grade_samples.py`를 불러오지 않고 아이디어만 가져왔다 |
| 추가 행·필드 | AO와 Harness의 k번째 추가 행, 같은 key의 추가 필드를 한 줄로 묶는다 | 같은 항목이 두 줄로 나뉘면 검수가 느려진다 |
| 프런트 | 빌드 도구·CDN 없는 vanilla JS 모듈, `innerHTML` 사용 안 함 | 폐쇄망 배포, XSS 방지 |

## 구현

- `backend/`: FastAPI. 업로드 분류와 stem 매칭, 정답지 생성·저장·삭제(원자적 rename), TIFF→PNG 변환 캐시, 비교·채점, golden.zip과 Excel(요약·필드·표·비교 시트) 내보내기. 계약은 `API.md`에 있다.
- `frontend/`: 업로드 화면, 이미지 목록(필터·검색·번들 채점), 상세 화면. 상세 화면 구성은 다음과 같다.
  - 이미지: 원본·전처리 전환, 확대·맞춤·이동
  - 정답지 편집: 필드·그룹·표 CRUD, Raw JSON, 자동 저장
  - 비교: 상태 필터, 글자 단위 diff, 근거 팝오버, AO·Harness 값 채택
  - Reconstructed View: HTML·Markdown으로 보기, Golden·AO·Harness 전환
- `scripts/make_dummy_bundle.py`: 테스트용 더미 번들 6건. 목록은 README에 있다. 이미지에는 정답 값을 그리고, AO와 Harness 결과에 오류를 일부러 넣었다.
- `Dockerfile`, `deploy/k8s/`(PVC·Deployment Recreate·Service·kustomization).

## UI 개편 (`feat/ui-refresh`)

사용자 피드백("UI가 허접하다")을 받고 `frontend-design` 스킬로 시각 체계를 다시 잡았다.

- 콘셉트는 교정지 검수대다. 종이와 잉크 같은 슬레이트 중립 톤을 바탕에 깔고, 형광펜 노랑(`--hl`) 한 가지만 "지금 봐야 할 곳"에 쓴다. 대상은 hover한 칸, 이미지 bbox, `M`으로 이동한 칸, 드롭 중인 영역, 검수 완료 표시다.
- 이미지 영역은 어두운 라이트테이블 배경이라 스캔본이 도드라진다.
- 서체는 Pretendard이고 한글 음절과 Latin 부분 집합 woff2 3종을 `frontend/fonts/`에 넣었다. 폐쇄망이라 CDN을 쓰지 않는다.
- 업로드 화면은 번들 구조 도식으로 stem 매칭 규칙을 보여 준다.
- 목록 화면은 검수 진행률, AO와 Harness 정확도, Harness 보정 효과(정확도 차이 p)를 한 줄에 둔다.
- 비교표는 틀린 행 왼쪽에 빨간 선을 긋고, 채택 버튼은 hover할 때만 보인다.
- `list.js`와 `compare.js`에 중복돼 있던 `scoreCard`·상태 색, 두 화면의 내보내기 메뉴를 `util.js`의 `scoreCard`·`statusBadge`·`menuButton`·`icon`으로 합쳤다.
- 밝은 화면, 어두운 화면, 모바일(390px)에서 콘솔 오류 없이 표시되는 것을 확인했다.

## 검증

- `pytest tests` 24건 통과.
  - 업로드: ZIP, 폴더, zip slip 거부
  - 매칭과 상태: stem 매칭, 누락·깨진 JSON
  - 정답지: 세 가지 초안 생성, 409, 저장 유지, 422
  - AO·Harness 파일은 바뀌지 않음(해시 비교)
  - 비교 5개 상태와 검수 상태
  - 내보내기: xlsx 시트, zip
  - 이미지: TIFF 여러 페이지
  - 경로 조작 거부
- 실제 서버(`backend.app`)에 더미 ZIP을 올리고 헤드리스 Chromium으로 확인했다.
  - 흐름: 업로드 → 목록 → DX002 비교 → PH003 정답지 생성(AO) → 값 수정 → Ctrl+S → MC005(깨진 JSON) → MC001에서 `M`으로 불일치 칸 이동
  - 결과: 콘솔 오류 0건. 저장한 정답지 파일에 수정이 반영됐고, AO 원본 해시는 바뀌지 않았다.

## 한계

- 정답지 편집 폼은 `documents[0]`만 다룬다. 문서가 여러 개면 나머지는 Raw JSON 모드에서 편집한다.
- 실제 AO와 하네스 출력에는 bbox가 없어서 이미지 하이라이트는 셀에 `bbox`가 있을 때만 동작한다.
- K8s 매니페스트는 `kubectl kustomize`로 렌더링되는 것만 확인했다. 실제 클러스터 배포와 Docker 빌드는 하지 않았다.
- 정규화는 일반 규칙만 적용한다. 문서 종류별 규칙(병명코드 검표, 개인정보 마스킹 등, `e2e/grade_samples.py`의 canon)은 옮기지 않았다.

## 관련

- [2026-09-28 AO–Harness Golden Set 검수 Viewer](2026-09-28-golden-set-viewer.md) (deprecated)
