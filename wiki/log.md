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

## 2026-09-28

### Creation

- [AO UI response 정규화와 Raw JSON 원문 선택](2026-09-28-ao-upload-classification.md): AO Extract 경로의 UI response 정규화와 별도 AO UI sidecar, 상세 Raw JSON 원문 선택을 기록.
- [상세 검수 상호작용 개선](2026-09-28-review-inspection-interactions.md): bbox hover, 표 편집 포커스, JSON 트리 탐색과 비교 상태 설명 개선을 기록.
- [실전형 dummy2 샘플 번들](2026-09-28-realistic-dummy2.md): e2e 실문서 7종의 이미지·원본 AO·Harness·정답 세트를 고르고 재현 및 개인정보 취급을 기록.
- [Label Viewer 상세 검수 Workspace 개편](2026-09-28-label-viewer-review-workspace.md): 문서 레일, 이미지 뷰어, compact Golden 편집, 비교와 재구성 화면의 작업 흐름을 기록.
- [AO–Harness Golden Set 검수 Viewer](2026-09-28-golden-set-viewer.md): 작업 공간 루트 wiki 문서를 저장소로 복사.
- [번들 기반 Golden Set 관리 Web App](2026-09-28-bundle-golden-viewer.md): PRD 기반 새 앱 구현 기록.

### Update

- [README](../README.md): `.aiocr.json` AO 추출 입력, `.aiocr.ui.json` UI response, `ao_ui/` 별도 sidecar의 위치별 역할과 Raw JSON 안내를 정리.
- [wiki/index.md](index.md): AO UI response 정규화 문서 링크 추가.
- [실전형 dummy2 샘플 번들](2026-09-28-realistic-dummy2.md): 기본 UI response 출력과 classic AO + sidecar 출력 형식, 새 생성물 검증 결과를 설명.
- [README](../README.md): bbox 위치 확대, Raw JSON 트리, 표 편집과 상태 설명을 상세 화면 안내에 추가하고 선택적 AO UI sidecar 형식을 기록.
- [wiki/index.md](index.md): 상세 검수 상호작용 문서 링크 추가.
- [README](../README.md): 실제 E2E quartet에서 로컬용 `dummy2` 번들을 생성하는 방법과 민감정보 유의사항 추가.
- [wiki/index.md](index.md): 실전형 dummy2 문서 링크 추가.
- [README](../README.md): 상세 검수 Workspace 구성과 기존 키보드 단축키 안내를 최신 UI에 맞게 갱신.
- [wiki/index.md](index.md): 상세 검수 Workspace 문서 링크 추가.
- [AO–Harness Golden Set 검수 Viewer](2026-09-28-golden-set-viewer.md): 새 앱으로 대체되어 `status: deprecated` 로 표시.
- [번들 기반 Golden Set 관리 Web App](2026-09-28-bundle-golden-viewer.md): UI 개편(교정지 검수대 콘셉트, Pretendard 내장, 공용 UI 조각 통합) 내용 추가.
