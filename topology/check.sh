#!/usr/bin/env bash
set -euo pipefail

if [[ ${EUID} -ne 0 ]]; then
    echo "Run this script as root: sudo $0" >&2
    exit 1
fi

expected=(rls-client rls-r1 rls-r2 rls-server)
for namespace in "${expected[@]}"; do
    if ! ip netns list | awk '{print $1}' | grep -Fxq "$namespace"; then
        echo "Missing namespace: $namespace" >&2
        exit 1
    fi
done

echo "Namespaces: OK"
ip netns exec rls-client ping -c 3 -W 2 10.10.2.2

check_qdisc() {
    local namespace=$1 device=$2 delay=$3 rate=$4 output
    output=$(ip netns exec "$namespace" tc qdisc show dev "$device")
    echo "$namespace/$device: $output"
    if ! [[ $output =~ netem && $output =~ delay\ $delay && $output =~ rate\ $rate && $output =~ limit\ 1000 ]]; then
        echo "FAIL: unexpected qdisc on $namespace/$device" >&2
        return 1
    fi
}
check_qdisc rls-client eth0 5ms '(1Gbit|1000Mbit)'
check_qdisc rls-r1 veth-r1-client 5ms '(1Gbit|1000Mbit)'
check_qdisc rls-r2 veth-r2-server 5ms '(1Gbit|1000Mbit)'
check_qdisc rls-server eth0 5ms '(1Gbit|1000Mbit)'
check_qdisc rls-r1 veth-r1-core 25ms 20Mbit
check_qdisc rls-r2 veth-r2-core 25ms 20Mbit
echo "Topology connectivity and qdiscs: OK"
