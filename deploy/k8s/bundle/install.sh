#!/usr/bin/env bash
# install.sh — label-viewer 를 폐쇄망 k8s 에 설치·업그레이드한다(다시 실행해도 안전, 새 태그면 파드가 교체된다).
#
#   sudo ./install.sh [-n 네임스페이스(label-viewer)] [--node <노드>] [--local-pv <디렉토리>] [--no-import]
#     --node      파드를 이 노드에 고정하고 이미지를 이 노드에 적재한다(이 스크립트를 이 노드에서 실행)
#     --local-pv  동적 StorageClass 가 없을 때: 이 디렉토리를 local PV 로 쓴다(--node 필수)
#     --no-import 이미지 적재를 건너뛴다(이미 노드에 있을 때)
set -euo pipefail
BUNDLE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=_common.sh
source "${BUNDLE_DIR}/_common.sh"

NS=label-viewer; NODE=""; LOCAL_PV=""; IMPORT=1; ARGS=("$@")
while [ $# -gt 0 ]; do
  case "$1" in
    -n)          NS="${2:?네임스페이스를 주십시오}"; shift 2 ;;
    --node)      NODE="${2:?노드 이름을 주십시오}"; shift 2 ;;
    --local-pv)  LOCAL_PV="${2:?디렉토리를 주십시오}"; shift 2 ;;
    --no-import) IMPORT=0; shift ;;
    *) echo "알 수 없는 인자: $1" >&2; exit 2 ;;
  esac
done
[ -z "$LOCAL_PV" ] || [ -n "$NODE" ] || { echo "--local-pv 는 --node 와 함께 써야 합니다" >&2; exit 2; }
need_root ${ARGS[@]+"${ARGS[@]}"}

TAG="$(sed -n 's/^ *newTag: *//p' "${BUNDLE_DIR}/k8s/kustomization.yaml")"
IMG="label-viewer:${TAG}"

echo "▶ 무결성 확인 (SHA256SUMS)"
( cd "$BUNDLE_DIR" && sha256sum -c --quiet SHA256SUMS )

# ── 이미지 적재(노드 containerd 의 k8s.io 네임스페이스) ──────────────────
find_bin() {  # sudo secure_path 가 /usr/local/bin 을 빼므로 흔한 위치를 직접 본다
  local d; command -v "$1" 2>/dev/null && return 0
  for d in /usr/local/bin /usr/local/sbin /usr/bin /usr/sbin /opt/containerd/bin /var/lib/rancher/rke2/bin; do
    [ -x "$d/$1" ] && { echo "$d/$1"; return 0; }
  done; return 1
}
import_image() {
  local tar sock c ctr nerd imp=(images import)
  tar="$(ls "${BUNDLE_DIR}"/images/label-viewer_*.tar)"
  for sock in "${CONTAINERD_SOCK:-}" /run/containerd/containerd.sock /run/k3s/containerd/containerd.sock; do
    [ -n "$sock" ] && [ -S "$sock" ] && break; sock=""
  done
  ctr="${CTR:-$(find_bin ctr || true)}"
  if [ -S /run/k3s/containerd/containerd.sock ] && command -v k3s >/dev/null 2>&1; then
    c=(k3s ctr -n k8s.io)
  elif [ -n "$ctr" ] && [ -n "$sock" ]; then
    c=("$ctr" --address "$sock" -n k8s.io)   # kubelet 은 k8s.io 네임스페이스만 본다
  elif nerd="$(find_bin nerdctl)"; then
    c=("$nerd" -n k8s.io); imp=(load -i)
  else
    echo "✘ containerd 의 ctr 을 찾지 못했습니다 (docker 명령이 Podman 이면 kubelet 이 이미지를 못 봅니다)." >&2
    echo "  sudo CTR=/경로/ctr CONTAINERD_SOCK=/경로/containerd.sock ./install.sh ..." >&2; exit 2
  fi
  if "${c[@]}" images ls 2>/dev/null | grep -qE "label-viewer[: ]+${TAG}( |$)"; then
    echo "  이미 있음: ${IMG}"; return 0
  fi
  echo "▶ 이미지 적재: ${IMG}"
  "${c[@]}" "${imp[@]}" "$tar"
}
[ "$IMPORT" = 0 ] || import_image

ensure_kube
K=(kubectl -n "$NS")
kubectl get ns "$NS" >/dev/null 2>&1 || kubectl create ns "$NS"

# ── 저장소 ──────────────────────────────────────────────────────────────
# kustomize 는 절대 경로 리소스를 막아 오버레이를 번들 안에 둔다
OVERLAY="$(mktemp -d -p "$BUNDLE_DIR" .overlay.XXXXXX)"; trap 'rm -rf "$OVERLAY"' EXIT
{
  echo "apiVersion: kustomize.config.k8s.io/v1beta1"; echo "kind: Kustomization"
  echo "namespace: ${NS}"; echo "resources: [../k8s]"; echo "patches:"
} > "${OVERLAY}/kustomization.yaml"
add_patch() {  # add_patch <kind> <name> <JSON patch(op 목록)>
  printf '  - target: {kind: %s, name: %s}\n    patch: |-\n      %s\n' "$1" "$2" "$3" >> "${OVERLAY}/kustomization.yaml"
}
if [ -n "$LOCAL_PV" ]; then
  echo "▶ local PV: ${NODE}:${LOCAL_PV}"
  mkdir -p "$LOCAL_PV"; chown 10001:10001 "$LOCAL_PV"
  command -v chcon >/dev/null 2>&1 && chcon -R -t container_file_t "$LOCAL_PV" 2>/dev/null || true   # SELinux
  kubectl apply -f - <<PV
apiVersion: v1
kind: PersistentVolume
metadata:
  name: $(pv_name "$NS")
  labels: {app: label-viewer}
spec:
  capacity: {storage: 20Gi}
  accessModes: [ReadWriteOnce]
  persistentVolumeReclaimPolicy: Retain
  storageClassName: ${LOCAL_SC}
  local: {path: ${LOCAL_PV}}
  nodeAffinity:
    required:
      nodeSelectorTerms:
        - matchExpressions:
            - {key: kubernetes.io/hostname, operator: In, values: [${NODE}]}
PV
  SC="$LOCAL_SC"
elif SC="$("${K[@]}" get pvc label-viewer-data -o jsonpath='{.spec.storageClassName}' 2>/dev/null)"; then
  :   # 기존 PVC 의 클래스를 그대로 둔다(PVC spec 은 바꿀 수 없다)
elif ! kubectl get sc -o json | grep -q 'is-default-class": *"true"'; then
  echo "✘ 기본 StorageClass 가 없어 PVC 를 만들 수 없습니다 — --node <노드> --local-pv <디렉토리> 로 다시 실행하십시오." >&2; exit 1
fi
[ -z "${SC:-}" ] || add_patch PersistentVolumeClaim label-viewer-data "[{\"op\":\"add\",\"path\":\"/spec/storageClassName\",\"value\":\"${SC}\"}]"
[ -z "$NODE" ] || add_patch Deployment label-viewer "[{\"op\":\"add\",\"path\":\"/spec/template/spec/nodeSelector\",\"value\":{\"kubernetes.io/hostname\":\"${NODE}\"}}]"

echo "▶ 배포 (${NS}, ${IMG})"
kubectl apply -k "$OVERLAY"
"${K[@]}" rollout status deploy/label-viewer --timeout=5m

IP="$([ -z "$NODE" ] || kubectl get node "$NODE" -o jsonpath='{.status.addresses[?(@.type=="InternalIP")].address}')"
[ -n "$IP" ] || IP="$("${K[@]}" get pod -l app=label-viewer -o jsonpath='{.items[0].status.hostIP}')"
echo
echo "✔ 설치 완료 — http://${IP}:30920  (인증 없음: 내부망에서만 접근 가능해야 합니다)"
