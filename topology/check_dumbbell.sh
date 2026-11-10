#!/usr/bin/env bash
set -euo pipefail
DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
bash "${DIR}/check.sh"
for namespace in rls-client2 rls-server2; do
    ip netns list | awk '{print $1}' | grep -Fxq "${namespace}"
done
ip netns exec rls-client2 ping -c 3 -W 2 10.10.4.2
ip netns exec rls-client ping -c 1 -W 2 10.10.4.2
echo 'PASS: both endpoint pairs and cross-pair routing work.'
