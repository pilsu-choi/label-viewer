---
okf_version: "0.2"
type: implementation
title: Label Viewer 화면 로드·편집 성능 최적화
description: AWS 원격 사용 시 화면 로드와 Golden 편집이 버벅이던 문제를 서버 캐시·압축·정적 파일 캐시·썸네일과 프론트 재렌더링 절감으로 개선한 기록
tags: [label-viewer, performance, cache, frontend, backend]
status: active
---

날짜: 2026-09-30
브랜치: `feat/perf`
워크트리: `label_veiwer/.worktrees/perf`

## 배경

AWS에 띄운 뷰어를 원격으로 쓰면 화면 로드와 편집이 느렸다. 점검 결과 서버는 캐시 없이 요청마다 모든 JSON을 다시 파싱하고 응답을 압축하지 않았다. 정적 파일은 `no-cache`라 모듈 13개가 매번 재검증 왕복을 했다. 프론트는 키 입력마다 재구성 패널 전체와 요약을 다시 그렸다.

## 변경

### 서버 (`backend/`)

| 항목 | 내용 |
|---|---|
| 압축 | `TextGZip`(GZip, level 6, 1KB 이상). 이미지·내보내기는 이미 압축돼 있어 건너뛴다 |
| 정적 파일 | 시작 시 프론트 파일 경로·mtime·크기 해시로 `/static/<ver>/`를 만들어 `immutable` 1년 캐시. `/`는 index.html의 `"/static/`을 버전 경로로 바꿔 `no-cache`로 준다. 구버전 탭용 `/static`(no-cache)도 유지 |
| 캐시 | `_memo(key, fn)` 하나로 통일. 키에 파일 `(inode, mtime_ns, size)`를 넣어 원자적 교체·다른 워커의 쓰기에도 무효화된다. mtime이 20ms 이내면 매번 새 키를 써서 같은 tick 재기록을 놓치지 않는다 |
| 캐시 대상 | 디렉터리 파일명 집합(`find_kind_file`·`doc_ids`), JSON 파싱+canonical 변환, TIFF 페이지 수, 번들 화면 문서별 요약(비교·채점), 번들 목록 집계 |
| 이미지 | `?w=`(64~1600) JPEG 썸네일을 `.cache`에 저장. 이미지 응답 `Cache-Control: private, max-age=86400`. TIFF·BMP 변환 PNG는 `compress_level=1` |
| 비교 | 추가 항목 그룹 탐색을 셀→그룹 사전으로 바꿔 O(키×그룹)을 없앰 |
| 워커 | `--workers`/`LABEL_VIEWER_WORKERS`(기본 2). 팩토리 `backend.app:app_from_env`로 실행. k8s 메모리 요청 512Mi·한도 2Gi |

캐시된 객체는 호출자가 수정하지 않는다(`create_golden`은 이미 deep copy). `_state.json`은 `set_review`가 수정하므로 캐시하지 않는다.

### 화면 (`frontend/`)

- 편집: 재구성 패널은 입력 후 300ms 디바운스, 접힌 동안은 그리지 않는다. 편집 요약은 150ms 디바운스, 표시 경로 집합은 구조가 바뀔 때만 다시 계산.
- 자동 저장 후 비교 표는 비교 탭이 보일 때만 다시 그리고, 아니면 탭을 열 때 그린다. 스크롤 기준 행은 이진 탐색.
- JSON 탭은 처음 열 때 만든다.
- 문서 이동 시 번들 정보는 캐시를 재사용하고(목록 화면은 새로 받음), 이전·다음 문서 이미지를 미리 받는다.
- 목록 썸네일은 `w=480`, `decoding=async`. 목록·문서 레일 검색 150ms 디바운스.
- 이미지 이동은 프레임당 한 번 그리고, 늦게 도착한 이전 이미지 로드는 무시한다. `will-change`·`translate3d`는 확대 시 흐려질 수 있어 쓰지 않는다.
- JSON 검색 일치 수를 질의별로 캐시. 복제는 `structuredClone`.
- `index.html`에 모든 모듈 `modulepreload`.

## 검증

- `pytest` 45개 통과(썸네일·캐시 헤더, 파일 변경 시 캐시 무효화, 정적 버전·GZip 테스트 추가).
- 서버 180문서 번들, 단일 연결 중앙값: 번들 목록 20.2→4.3ms, 번들 조회 44.1→19.9ms. 번들 JSON 69KB→1.6KB(gzip).
- Playwright(14문서 dummy2): 정적 파일이 `/static/<ver>/`로 17건 로드, 썸네일 `w=480`, 편집 입력 후 자동 저장 PUT 반영, 문서 이동 시 번들 재요청 0건, 콘솔 오류 없음.
- 같은 문서에서 키 30회 입력: dev 510~547ms → 282~299ms.
