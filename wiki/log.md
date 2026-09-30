---
okf_version: "0.2"
type: log
title: label_veiwer 지식 문서 변경 기록
description: 저장소 wiki 문서의 생성과 수정 이력
tags: [wiki, log]
status: active
---

날짜: 2026-09-28
브랜치: `fix/ao-upload-raw`
워크트리: `.worktrees/ao-upload-fix`

## 2026-09-29

### Creation

- [한글·공백·괄호 파일명 문서 400 오류 수정과 표본 205건 업로드](2026-09-29-unicode-doc-id.md): 문서 ID 검사 완화, 205건 번들 변환·업로드 기록.

### Update

- [Label Viewer Docker Compose·AWS 배포](2026-09-29-docker-aws-deploy.md): Golden 초안 수정 반영 AWS 재배포 결과 추가.
- [Label Viewer Docker Compose·AWS 배포](2026-09-29-docker-aws-deploy.md): dev `c0a9f11` AWS 재배포 결과 추가.
- [Label Viewer 양식 불일치 표시와 문서 분류 판정 검토](2026-09-29-doc-type-mismatch.md): 검수자 문서 종류 확정·7종 양식 템플릿, 분류 채점과 오분류 필드 집계 제외 구현 내용 추가.
- [Label Viewer 양식 불일치 표시·문서 종류 확정·분류 채점](2026-09-29-doc-type-mismatch.md): 상세 화면이 열리지 않던 배지 배열 렌더링 오류 수정과 브라우저 확인 결과 추가.
- [Label Viewer 양식 불일치 표시·문서 종류 확정·분류 채점](2026-09-29-doc-type-mismatch.md): 정적 파일 `Cache-Control: no-cache` 적용 기록.
- [Label Viewer 양식 불일치 표시·문서 종류 확정·분류 채점](2026-09-29-doc-type-mismatch.md): AO 문서 코드를 이름과 함께 표시하는 내용 추가.
- [Label Viewer 양식 불일치 표시·문서 종류 확정·분류 채점](2026-09-29-doc-type-mismatch.md): 비교 탭 문서 유형 행 추가.

### Creation

- [Label Viewer 폐쇄망 k8s 반입 번들](2026-09-29-k8s-offline-bundle.md): 독립 반입 번들(이미지 tar·kustomize·install/remove) 추가와 kind 검증 기록.
- [실행 응답 형식 하네스·AO JSON Golden 초안 수정](2026-09-29-run-result-golden-draft.md): 최상위 `result` 형식 정규화로 빈 초안 문제 해결.
- [Label Viewer 창 크기 반응형 레이아웃](2026-09-29-responsive-layout.md): 재구성 보기·이미지 분할 비율화, 상단바·도구 모음 줄바꿈, 가로 스크롤 제거, 비교 표 배지 줄바꿈 기록.
- [Label Viewer 양식 불일치 표시와 문서 분류 판정 검토](2026-09-29-doc-type-mismatch.md): Harness 재분류 기반 양식 불일치 배지, AO 기반 Golden 생성 경고, AO JSON만으로 분류 판정 가능성 검증(e2e 205건)과 후속 제안 기록.
- [Label Viewer Docker Compose·AWS 배포](2026-09-29-docker-aws-deploy.md): docker-compose.yml과 deploy/aws 스크립트 추가 기록.
- [Label Viewer 비교 탭 사용성 개선](2026-09-29-compare-tab-usability.md): 비교 탭 점검 결과와 채택 흐름·개수 기준·Golden 없음 수정, 기본 불일치 필터, 셀 채택, 두 탭 공용 상태 색, 근거 팝오버, 표 행 묶기, 소스 필터·검색, 키보드 조작 기록.
- [Label Viewer 편집 탭 버그 수정·사용성 개선](2026-09-29-edit-tab-usability.md): 편집 탭 점검 결과, 버그 4건 수정, 필드 행·표 셀 상태 표시, 재구성 패널 접기, 불일치 개수 기준 통일과 편집 탭 안 이동 기록.
- [Label Viewer 상세 화면 레이아웃·그리드·스크롤 개선](2026-09-29-label-viewer-layout-grid.md): 패널 접기, 이미지 동적 재조정, 편집·재구성 그리드, 비교 근거 스크롤, 추가 시 스크롤 유지 기록.

### Update

- [Label Viewer Docker Compose·AWS 배포](2026-09-29-docker-aws-deploy.md): AWS 실배포 결과와 0.0.0.0 외부 노출 주의 추가.
- [README](../README.md): 배포 절을 Docker Compose·AWS 개발 서버·Kubernetes로 나누고 구조에 deploy/aws 추가.
- [wiki/index.md](index.md): Docker·AWS 배포 문서 링크 추가.
- [README](../README.md): 비교 탭 기본 불일치 필터·소스 필터·검색·셀 채택·저장 대기·상태 색·행 묶기·근거 위치와 비교 탭 키보드(`↑/↓`, `A`/`H`, `Enter`) 안내 반영.
- [Label Viewer 편집 탭 버그 수정·사용성 개선](2026-09-29-edit-tab-usability.md): 남은 과제였던 상태 색 의미 재정의가 비교 탭 작업에서 반영됐음을 기록.
- [wiki/index.md](index.md): 비교 탭 사용성 개선 문서 링크 추가.
- [README](../README.md): 편집 탭 요약·불일치 이동(`M`/`Shift+M`), 재구성 패널 접기, key 더블클릭 편집, 표 셀 채택 안내 반영.
- [wiki/index.md](index.md): 편집 탭 사용성 개선 문서 링크 추가.

- [README](../README.md): `[`·`]` 패널 접기 단축키와 이미지 동적 재조정 안내 추가.
- [wiki/index.md](index.md): 레이아웃·그리드 문서 링크 추가.

## 2026-09-28

### Creation

- [AO UI response 정규화와 Raw JSON 원문 선택](2026-09-28-ao-upload-classification.md): AO Extract 경로의 UI response 정규화와 별도 AO UI sidecar, 상세 Raw JSON 원문 선택을 기록.
- [Label Viewer UI 마감 품질 개선](2026-09-28-label-viewer-ui-polish.md): 디자인 토큰·공통 컴포넌트·문구 통일과 전 화면 마감 개선 기록.
- [상세 검수 상호작용 개선](2026-09-28-review-inspection-interactions.md): bbox hover, 표 편집 포커스, JSON 트리 탐색과 비교 상태 설명 개선을 기록.
- [실전형 dummy2 샘플 번들](2026-09-28-realistic-dummy2.md): e2e 실문서 7종의 이미지·원본 AO·Harness·정답 세트를 고르고 재현 및 개인정보 취급을 기록.
- [Label Viewer 상세 검수 Workspace 개편](2026-09-28-label-viewer-review-workspace.md): 문서 레일, 이미지 뷰어, compact Golden 편집, 비교와 재구성 화면의 작업 흐름을 기록.
- [AO–Harness Golden Set 검수 Viewer](2026-09-28-golden-set-viewer.md): 작업 공간 루트 wiki 문서를 저장소로 복사.
- [번들 기반 Golden Set 관리 Web App](2026-09-28-bundle-golden-viewer.md): PRD 기반 새 앱 구현 기록.

### Update

- [Label Viewer UI 마감 품질 개선](2026-09-28-label-viewer-ui-polish.md): JSON 뷰어 개편과 bbox 보기 방식 선택·미니맵 내용 추가.
- [README](../README.md): JSON 탭 명칭, 검색·경로 복사, bbox 보기 방식(`Z`)과 미니맵 안내 반영.
- [README](../README.md): `.aiocr.json` AO 추출 입력, `.aiocr.ui.json` UI response, `ao_ui/` 별도 sidecar의 위치별 역할과 Raw JSON 안내를 정리.
- [wiki/index.md](index.md): AO UI response 정규화 문서 링크 추가.
- [실전형 dummy2 샘플 번들](2026-09-28-realistic-dummy2.md): 기본 UI response 출력과 classic AO + sidecar 출력 형식, 새 생성물 검증 결과를 설명.
- [README](../README.md): bbox 위치 확대, Raw JSON 트리, 표 편집과 상태 설명을 상세 화면 안내에 추가하고 선택적 AO UI sidecar 형식을 기록.
- [README](../README.md): 재구성 보기 명칭과 편집 패널 `⋯` 메뉴(JSON 보기, Golden 삭제) 안내 반영.
- [wiki/index.md](index.md): UI 마감 품질 개선 문서 링크 추가.
- [wiki/index.md](index.md): 상세 검수 상호작용 문서 링크 추가.
- [README](../README.md): 실제 E2E quartet에서 로컬용 `dummy2` 번들을 생성하는 방법과 민감정보 유의사항 추가.
- [wiki/index.md](index.md): 실전형 dummy2 문서 링크 추가.
- [README](../README.md): 상세 검수 Workspace 구성과 기존 키보드 단축키 안내를 최신 UI에 맞게 갱신.
- [wiki/index.md](index.md): 상세 검수 Workspace 문서 링크 추가.
- [AO–Harness Golden Set 검수 Viewer](2026-09-28-golden-set-viewer.md): 새 앱으로 대체되어 `status: deprecated` 로 표시.
- [번들 기반 Golden Set 관리 Web App](2026-09-28-bundle-golden-viewer.md): UI 개편(교정지 검수대 콘셉트, Pretendard 내장, 공용 UI 조각 통합) 내용 추가.
- [wiki/index.md](index.md), [wiki/log.md](log.md): dev의 bbox 연결·JSON 탐색 개선과 UI 마감 브랜치를 병합하며 두 브랜치의 문서 기록을 합침.

## 2026-09-29

### Creation
- [편집 탭 불일치 강조와 Golden에 없는 키 ghost 행](2026-09-29-editor-mismatch-viz.md): 불일치 칸 테두리 강조, AO·Harness에만 있는 키를 채택 가능한 ghost 행으로 표시.

### Update
- [편집 탭 불일치 강조와 Golden에 없는 키 ghost 행](2026-09-29-editor-mismatch-viz.md): 표 셀 강조가 절반만 칠해지던 문제 수정 내용 추가.

### Creation
- [문서 유형 필터와 편집 탭 표 다중 셀 일괄 입력](2026-09-29-doctype-filter-multicell.md): 목록 문서 유형 select 필터, 표 드래그·Shift+클릭 범위 선택 후 같은 값 일괄 입력, 채택 바 상시 표시로 표 밀림 제거.

### Update
- [문서 유형 필터와 편집 탭 표 다중 셀 일괄 입력](2026-09-29-doctype-filter-multicell.md): 상세 화면 문서 목록 유형 필터, 목록 화면과 선택 공유, 문서 이동 시 필터 유지 추가.

### Update
- [Label Viewer 폐쇄망 k8s 반입 번들](2026-09-29-k8s-offline-bundle.md): dev `d5aba7e` 기준 번들 `0.1.0-20260930-d5aba7e` 재빌드, 반입 이력 표 추가.

## 2026-09-30

### Creation
- [전체 묶음 ZIP 내보내기](2026-09-30-bundle-export-zip.md): 목록·상세 화면 내보내기를 원본·전처리 이미지와 AO·Harness·Golden JSON 전체 묶음 ZIP으로 변경.

### Update
- [Label Viewer Docker Compose·AWS 배포](2026-09-29-docker-aws-deploy.md): dev `33fce14` 재배포(전체 묶음 ZIP 내보내기) 이력 추가.

### Creation
- [한글 파일명 ZIP 인식과 업로드·조회 오류 전수 점검](2026-09-30-korean-filename-upload-hardening.md): CP949·NFD 파일명 인식, JSON 인코딩·형식 오류 격리, 1000개 초과 업로드, 잡파일·긴 파일명·손상 입력 500 수정.

### Update
- [Label Viewer Docker Compose·AWS 배포](2026-09-29-docker-aws-deploy.md): dev `dc1f0f4` 재배포(한글 파일명·업로드 오류 수정) 이력 추가.

### Update
- [Label Viewer 폐쇄망 k8s 반입 번들](2026-09-29-k8s-offline-bundle.md): dev `a047041` 기준 번들 `0.1.0-20260930-a047041` 재빌드, 이전 번들 `d5aba7e` 삭제.
