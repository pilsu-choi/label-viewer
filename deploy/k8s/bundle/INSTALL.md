# label-viewer 폐쇄망 k8s 설치

## 준비

- 대상: Rocky/RHEL 9 + containerd + kubectl 이 되는 서버(단일 노드 가능). 인터넷·레지스트리는 필요 없다.
- 이미지는 노드 containerd 의 `k8s.io` 네임스페이스에 직접 적재한다 — **파드가 뜰 노드에서** 실행한다.
- 저장소: 기본 StorageClass 가 있으면 PVC(20Gi)가 자동으로 잡힌다. 없으면 `--local-pv` 를 쓴다.
- 앱 파일과 PostgreSQL 데이터는 별도 PVC 에 저장한다. local PV 를 쓸 때 PostgreSQL 파일은 지정 경로의 `postgres/` 하위에 둔다.

## 설치

번들 디렉토리를 서버로 복사(NAS·scp 등)한 뒤:

```bash
cd label-viewer-k8s-<태그>
sudo ./install.sh --node <노드이름> --local-pv /opt/label-viewer/data   # 기본 StorageClass 가 없을 때
sudo ./install.sh --node <노드이름>                                     # 기본 StorageClass 가 있을 때
```

- `-n <ns>` 네임스페이스(기본 `label-viewer`), `--no-import` 이미지 적재 생략.
- 노드 이름은 `kubectl get nodes` 로 확인한다.
- 끝나면 `http://<노드IP>:30920` 을 알려 준다.
- 최초 설치 시 installer 는 임의 DB 비밀번호를 만들고 `label-viewer-postgres` Secret 에 저장한다. Secret 은 업그레이드에서 유지되며 설치 출력에 값이 나타나지 않는다. `kubectl apply -k` 를 직접 쓸 때는 README 의 Secret 설명대로 두 key 를 먼저 생성해야 한다.

## 업그레이드

새 번들에서 같은 명령을 다시 실행한다. 앱과 PostgreSQL 이미지가 노드에 적재되고 앱 파드가 갱신된다. PVC 와 생성된 Secret 은 유지된다.

## 삭제

```bash
sudo ./remove.sh            # 데이터(PVC·PV)와 DB Secret 은 남긴다
sudo ./remove.sh --purge    # PVC·PV 및 DB Secret 삭제(local PV 디렉토리 파일은 직접 삭제)
```

## 주의

label-viewer 에는 **인증이 없다.** NodePort(30920)로 내부망 전체에 노출되므로 접근 가능한 네트워크를 제한한다.
