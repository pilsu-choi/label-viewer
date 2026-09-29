---
okf_version: "0.2"
type: implementation
title: Label Viewer 폐쇄망 k8s 반입 번들
description: 개발계(운영계 전환 예정, L40S×4) k8s에 label-viewer를 반입하기 위한 독립 번들(이미지 tar·kustomize·설치 스크립트)과 kind 검증 기록
tags: [label-viewer, deploy, k8s, air-gapped]
status: active
---

날짜: 2026-09-29
브랜치: `feat/k8s-bundle`
워크트리: `label_veiwer/.worktrees/k8s-bundle`

## 배경

label-viewer도 개발계(운영계 전환 예정 서버, L40S×4) k8s에 올려야 한다. 폐쇄망이므로 인터넷·레지스트리 없이 설치되는 빌드 산출물이 필요하다.
harness-installer 우산 차트에 넣는 대신 **독립 번들**로 만들었다 — 저장소에 원격이 없고, 우산 번들의 빌드·패치 스크립트가 harness·docraft 두 앱 전제로 짜여 있어 변경 범위가 크다.

## 구성

| 파일 | 역할 |
|---|---|
| `VERSION` | 번들 버전(semver) |
| `deploy/k8s/*.yaml` | kustomize. Service NodePort `30920`, `runAsUser/fsGroup 10001`, 이미지 태그는 `kustomization.yaml` `images.newTag` |
| `deploy/k8s/build-bundle.sh` | 작업 PC에서 `linux/amd64` 이미지 빌드 → `docker save` → `dist/label-viewer-k8s-<태그>/`(SHA256SUMS). `--tar` 로 단일 tar |
| `deploy/k8s/bundle/install.sh` | 무결성 확인 → 노드 containerd(`k8s.io`)에 적재 → 임시 오버레이(namespace·nodeSelector·storageClass) → `kubectl apply -k` → rollout 대기 |
| `deploy/k8s/bundle/remove.sh` | Deployment·Service 삭제, `--purge` 면 PVC·PV까지 |
| `deploy/k8s/bundle/INSTALL.md` | 반입지 설치 안내 |

이미지 태그: `<VERSION>-<YYYYMMDD>-<커밋>`(미커밋 변경 시 `-dirty<시각>`). 태그가 번들마다 달라 재설치하면 파드가 교체된다.

## 설치(반입지)

```bash
sudo ./install.sh --node <노드> --local-pv /opt/label-viewer/data   # 동적 StorageClass 가 없을 때
sudo ./install.sh --node <노드>                                     # 기본 StorageClass 가 있을 때
```

접속: `http://<노드 IP>:30920`. **인증이 없다** — 내부망에서만 접근되어야 한다.

## 결정

- 우산 차트 통합 대신 독립 번들(사용자 선택). helm 없이 `kubectl apply -k` 만 쓴다.
- 재설치 시 기존 PVC 의 storageClassName 을 읽어 그대로 패치한다 — PVC spec 은 바꿀 수 없어 옵션 없이 다시 실행하면 적용이 실패하던 문제를 막는다.
- local PV 디렉토리는 `chown 10001` + SELinux `container_file_t` 라벨을 맞춘다(Rocky 9).

## 검증

kind(v1.3x) 노드 컨테이너 안에서 번들 `0.1.0-20260929-e24e876` 설치:

- `--node --local-pv`: ctr 적재 → PV/PVC Bound → rollout 성공, `/api/health` `{"ok":true}`, 파드 uid 10001로 `/data` 쓰기 확인
- 옵션 없이 재실행: 기존 PVC 클래스 유지, 성공
- 기본 StorageClass 경로(`-n lv2 --no-import`) 설치·재실행 성공
- `remove.sh`(PVC·PV 유지), `remove.sh --purge`(모두 삭제) 확인

## 남은 일

- 실제 개발계 노드(RHEL9 containerd)에서 설치 확인.
