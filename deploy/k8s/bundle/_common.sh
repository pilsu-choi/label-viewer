# shellcheck shell=bash
# _common.sh — install.sh·remove.sh 공용(source). 직접 실행하지 않는다.

# root(sudo) 로 실행하면 kubeconfig 가 없는 경우가 있다. 흔한 위치를 차례로 본다.
ensure_kube() {
  command -v kubectl >/dev/null 2>&1 || { echo "kubectl 이 필요합니다" >&2; exit 2; }
  local kc
  for kc in "" "${SUDO_USER:+/home/$SUDO_USER/.kube/config}" /etc/kubernetes/admin.conf /etc/rancher/k3s/k3s.yaml /etc/rancher/rke2/rke2.yaml; do
    if [ -z "$kc" ]; then kubectl version --request-timeout=5s >/dev/null 2>&1 && return 0; continue; fi
    [ -r "$kc" ] || continue
    if KUBECONFIG="$kc" kubectl version --request-timeout=5s >/dev/null 2>&1; then
      export KUBECONFIG="$kc"; echo "▶ kubeconfig: $kc"; return 0
    fi
  done
  echo "클러스터에 접속하지 못했습니다 — KUBECONFIG 를 지정하거나 kubectl 이 되는 계정으로 실행하십시오" >&2; exit 2
}

# root 가 아니면 sudo 로 스스로를 다시 실행한다.
need_root() {
  [ "$(id -u)" = 0 ] && return 0
  command -v sudo >/dev/null 2>&1 || { echo "root 로 실행하십시오 (sudo $0)" >&2; exit 2; }
  exec sudo -E "$0" "$@"
}

LOCAL_SC=label-viewer-local
pv_name() { echo "label-viewer-local-$1"; }   # pv_name <네임스페이스> — PV 는 클러스터 범위라 네임스페이스별로 이름을 가른다
