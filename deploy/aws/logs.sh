#!/usr/bin/env bash
# deploy/aws/logs.sh — 원격 로그 tail. 추가 인자는 docker compose logs 로 넘긴다.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/_common.sh"
remote_compose "logs --tail 100 -f $*"
