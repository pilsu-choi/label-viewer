---
type: implementation
title: 번들 화면 문서 요약 DB 저장과 LRU 캐시
description: 재시작·다른 워커에서도 번들 화면이 JSON을 다시 읽지 않도록 문서별 요약을 PostgreSQL에 저장하고, 가득 차면 통째로 비우던 프로세스 캐시를 LRU로 바꾼 기록
tags: [performance, cache, postgresql, bundle-view]
status: active
---

날짜: 2026-10-06 · 브랜치: fix/bundle-view-cache → dev · 워크트리: .worktrees/bundle-view-cache

## 배경

[성능 점검](2026-10-03-bundle-list-performance.md) 이후 남은 문제 두 가지를 고쳤다.

1. 번들 화면(`bundle_view`)의 문서별 요약(비교·채점·분류)은 프로세스 메모리에만 있었다. 재시작·배포 직후, 그리고 워커 2개가 각자 처음 열 때 모든 JSON을 다시 읽고 비교했다.
2. `_memo`는 4,096개가 차면 캐시를 통째로 비웠다. 수천 건 번들을 조회하거나 내보내면 디렉터리 목록·파싱 결과가 함께 사라져 적중률이 0에 가까워졌다.

## 변경

| 위치 | 내용 |
|---|---|
| `backend/db.py` | `doc_summaries(namespace, bundle_id, doc_id, fingerprint, summary JSONB)` 테이블 추가(`CREATE TABLE IF NOT EXISTS`). 번들 삭제 시 FK cascade로 함께 지운다. `get_doc_summaries`·`save_doc_summaries` |
| `backend/bundle.py` `_doc_summaries` | 프로세스 캐시 → DB 저장본 → 새 계산 순서. DB 조회는 캐시에 없는 문서만 번들당 1회, 새로 계산한 문서만 한 번에 저장한다 |
| fingerprint | 문서 파일(이름, dev·inode·mtime·ctime·크기·mode) 시그니처 + 코드 버전 해시. 코드 버전은 `backend/*.py`·`*.json` 내용 해시라 비교·채점 규칙이 바뀐 배포 뒤에는 저장본을 쓰지 않고 다시 계산한다 |
| 검수 상태 | 요약에서 `review`를 빼고 화면 응답에서 얹는다. 검수 상태만 바뀌면 요약을 다시 계산하지 않는다 |
| `_memo` | `OrderedDict` LRU. 적중 시 최근으로 올리고, 넘치면 가장 오래 안 쓴 항목만 버린다. 저장소 조작은 잠금 안, 계산은 잠금 밖 |

파일 모드(PostgreSQL 없음)는 DB 저장 없이 LRU 프로세스 캐시만 쓴다. 저장본은 원본 파일에서 다시 만들 수 있는 캐시이며 원본·Golden·검수 상태를 바꾸지 않는다.

## 검증

- 전체 회귀(로컬 PostgreSQL 포함) **194 passed**. 실패 1건 `test_upload_hardening`은 기존과 같은 macOS 한글 긴 파일명 제한 차이다.
- 추가 테스트: LRU 축출 순서, 검수 상태 변경 시 요약 재계산 없음, 캐시를 비운 뒤(재시작 상황) JSON 파싱 0회·응답 동일, 바뀐 문서만 재파싱·저장본 갱신, 코드 버전 변경 시 재계산, 번들 삭제 시 저장본 삭제.
- 실측(로컬 PostgreSQL, `make_dummy_bundle` 6건을 584배 복제한 번들, 문서 8,760건, 3회):

| 상황 | dev `913a0a1` | 개선 |
|---|---:|---:|
| 재시작 후 첫 조회(프로세스 캐시 없음) | 0.70~0.74초 | 0.45~0.48초 |
| 캐시 적중 | 0.30~0.34초 | 0.32~0.34초 |

더미 JSON은 작아서 파싱 비용이 실데이터보다 훨씬 적다. 실제 번들(JSON 평균 수십 KB)에서는 재시작 후 첫 조회의 차이가 더 커진다. 개선판의 첫 조회 남은 시간은 파일 stat·DB 저장본 조회 비용이다. 실제 데이터는 개인정보가 있어 이번 측정에 쓰지 않았다.

## 배포·데이터 보존

- 새 테이블은 앱 시작 시 `CREATE TABLE IF NOT EXISTS`로 추가만 한다. 기존 테이블·번들 파일을 바꾸거나 지우지 않는다.
- k8s `install.sh` 재설치는 기존 앱·PostgreSQL PVC를 그대로 쓰므로 번들이 유지된다. `remove.sh --purge`만 PVC를 지운다.
- 배포 직후 각 번들의 첫 조회는 저장본을 만드느라 이전과 같은 시간이 걸리고, 이후 재시작부터 빨라진다.

## 패치

`~/Desktop/mirae/label-viewer-20261006.patch` — dev `913a0a1` 기준 `git diff`(코드·테스트·wiki).
