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

echo "Forward bottleneck qdisc:"
ip netns exec rls-r1 tc qdisc show dev veth-r1-core
echo "Reverse bottleneck qdisc:"
ip netns exec rls-r2 tc qdisc show dev veth-r2-core
echo "Topology connectivity and qdiscs: OK"
