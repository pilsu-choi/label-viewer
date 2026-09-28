#!/usr/bin/env bash
# deploy/aws/down.sh — 원격 정지. 데이터 볼륨(번들·정답지)은 남긴다.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/_common.sh"
remote_compose "down"
