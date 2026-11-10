#!/usr/bin/env bash
set -euo pipefail
DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
bash "${DIR}/check.sh"
for namespace in rls-client2 rls-server2; do
    ip netns list | awk '{print $1}' | grep -Fxq "${namespace}"
done
ip netns exec rls-client2 ping -c 3 -W 2 10.10.4.2
ip netns exec rls-client ping -c 1 -W 2 10.10.4.2
for pair in 'rls-client2 eth0' 'rls-r1 veth-r1-c2' 'rls-r2 veth-r2-s2' 'rls-server2 eth0'; do
    read -r namespace device <<< "$pair"
    output=$(ip netns exec "$namespace" tc qdisc show dev "$device")
    echo "$namespace/$device: $output"
    if ! [[ $output =~ netem && $output =~ delay\ 5ms && $output =~ rate\ (1Gbit|1000Mbit) && $output =~ limit\ 1000 ]]; then
        echo "FAIL: unexpected access qdisc on $namespace/$device" >&2
        exit 1
    fi
done
echo 'PASS: both endpoint pairs and cross-pair routing work.'
