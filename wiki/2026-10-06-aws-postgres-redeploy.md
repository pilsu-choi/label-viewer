---
type: implementation
title: Label Viewer AWS 재배포 — PostgreSQL 전환
description: dev c5d96d5를 AWS 개발 서버에 재배포하면서 파일 상태를 PostgreSQL로 처음 옮긴 기록과 확인 결과
tags: [label-viewer, deploy, aws, postgresql]
status: active
---

날짜: 2026-10-06 · 브랜치: dev(`c5d96d5`) 배포, 기록은 `docs/aws-redeploy-1006` · 워크트리: `label_veiwer/.worktrees/aws-redeploy-1006`

## 배포 대상

- 이전 AWS 배포본: dev `a73c636`(2026-10-01, 파일 저장).
- 이번 반영: PostgreSQL 메타데이터 저장([2026-10-03-postgresql.md](2026-10-03-postgresql.md)), 진단서4종 진료소견 필드, 번들 화면 문서 요약 DB 저장·LRU 캐시([2026-10-06-bundle-view-cache.md](2026-10-06-bundle-view-cache.md)).
- 서버: harness-v2 개발 EC2, `REMOTE_ROOT=/mnt/data/label-viewer`, `deploy/aws/deploy.sh`(amd64 빌드·이미지 반입).

## 절차

1. 서버의 기존 데이터 볼륨 `label-viewer_data`(640MB)를 `/mnt/data/label-viewer/backups/data-20261006-pre-postgres.tgz`(513MB)로 백업했다.
2. 로컬 `deploy/aws/.env.aws`에 `LABEL_VIEWER_DB_PASSWORD`(무작위 64자리 hex)와 `LABEL_VIEWER_DB_NAMESPACE=label-viewer`를 추가했다. 파일은 git 제외·권한 600이다. compose가 비밀번호 없이는 기동하지 않으므로 이후 배포에도 이 값을 유지한다.
3. `deploy.sh` 실행. `postgres:17` 컨테이너와 볼륨 `label-viewer_postgres_data`가 새로 생겼고, 앱은 기동 시 `import_files(only_if_needed=True)`로 기존 파일 상태를 DB에 한 번 이관했다.

## 확인

| 항목 | 결과 |
|---|---|
| 컨테이너 | `label-viewer`·`label-viewer-postgres-1` 모두 `healthy` |
| `/api/health`(외부) | `{"ok":true,"storage":"postgresql"}` |
| 번들 | 볼륨 디렉터리 15개 = DB `bundles` 15건 = `/api/bundles` 15건 |
| DB | 문서 검수 상태 84건, `metadata_imports` 1건(이관 1회) |
| `/` | 200 |

## 롤백

앱을 내리고 백업 tgz를 `label-viewer_data` 볼륨에 풀어 이전 이미지(dev `a73c636`)로 다시 배포한다. DB에서 생긴 이후 변경을 살리려면 먼저 컨테이너 안에서 `python scripts/migrate_postgres.py --data /data --export-files`로 파일에 내보낸다.

## 외부 노출

`.env.aws`의 `LABEL_VIEWER_BIND=0.0.0.0`은 이전 배포와 같다. 앱에 인증이 없으므로 보안그룹 소스 IP 제한을 유지한다.
