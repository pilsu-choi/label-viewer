#!/usr/bin/env bash
# remove.sh — label-viewer 를 삭제한다. 데이터(PVC·PV)는 --purge 가 없으면 남긴다.
#   sudo ./remove.sh [-n 네임스페이스(label-viewer)] [--purge]
set -euo pipefail
BUNDLE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=_common.sh
source "${BUNDLE_DIR}/_common.sh"

NS=label-viewer; PURGE=0; ARGS=("$@")
while [ $# -gt 0 ]; do
  case "$1" in
    -n)      NS="${2:?네임스페이스를 주십시오}"; shift 2 ;;
    --purge) PURGE=1; shift ;;
    *) echo "알 수 없는 인자: $1" >&2; exit 2 ;;
  esac
done
need_root ${ARGS[@]+"${ARGS[@]}"}
ensure_kube

kubectl -n "$NS" delete deploy,svc -l app=label-viewer --ignore-not-found
if [ "$PURGE" = 1 ]; then
  kubectl -n "$NS" delete pvc -l app=label-viewer --ignore-not-found
  kubectl delete pv "$(pv_name "$NS")" --ignore-not-found
  echo "✔ 삭제 완료 (PVC·PV 포함). local PV 디렉토리의 파일은 남아 있으니 필요하면 직접 지우십시오."
else
  echo "✔ 삭제 완료 — 데이터(PVC·PV)는 남겼습니다. 지우려면 --purge."
fi
