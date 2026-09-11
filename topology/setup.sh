#!/usr/bin/env bash
set -euo pipefail

# rls-client -- rls-r1 == shaped bottleneck == rls-r2 -- rls-server
CLIENT_NS=rls-client
LEFT_NS=rls-r1
RIGHT_NS=rls-r2
SERVER_NS=rls-server
NAMESPACES=("$CLIENT_NS" "$LEFT_NS" "$RIGHT_NS" "$SERVER_NS")

if [[ ${EUID} -ne 0 ]]; then
    echo "Run this script as root: sudo $0" >&2
    exit 1
fi

for command_name in ip tc; do
    if ! command -v "$command_name" >/dev/null 2>&1; then
        echo "Required command not found: $command_name" >&2
        exit 1
    fi
done

cleanup() {
    for namespace in "${NAMESPACES[@]}"; do
        if ip netns list | awk '{print $1}' | grep -Fxq "$namespace"; then
            ip netns delete "$namespace"
        fi
    done
}

on_error() {
    echo "Topology setup failed; removing partially created namespaces." >&2
    cleanup
}
trap on_error ERR

cleanup

for namespace in "${NAMESPACES[@]}"; do
    ip netns add "$namespace"
    ip -n "$namespace" link set lo up
done

ip link add veth-client type veth peer name veth-r1-client
ip link add veth-r1-core type veth peer name veth-r2-core
ip link add veth-r2-server type veth peer name veth-server

ip link set veth-client netns "$CLIENT_NS"
ip link set veth-r1-client netns "$LEFT_NS"
ip link set veth-r1-core netns "$LEFT_NS"
ip link set veth-r2-core netns "$RIGHT_NS"
ip link set veth-r2-server netns "$RIGHT_NS"
ip link set veth-server netns "$SERVER_NS"

ip -n "$CLIENT_NS" link set veth-client name eth0
ip -n "$SERVER_NS" link set veth-server name eth0

ip -n "$CLIENT_NS" addr add 10.10.1.2/24 dev eth0
ip -n "$LEFT_NS" addr add 10.10.1.1/24 dev veth-r1-client
ip -n "$LEFT_NS" addr add 10.10.12.1/30 dev veth-r1-core
ip -n "$RIGHT_NS" addr add 10.10.12.2/30 dev veth-r2-core
ip -n "$RIGHT_NS" addr add 10.10.2.1/24 dev veth-r2-server
ip -n "$SERVER_NS" addr add 10.10.2.2/24 dev eth0

ip -n "$CLIENT_NS" link set eth0 up
ip -n "$LEFT_NS" link set veth-r1-client up
ip -n "$LEFT_NS" link set veth-r1-core up
ip -n "$RIGHT_NS" link set veth-r2-core up
ip -n "$RIGHT_NS" link set veth-r2-server up
ip -n "$SERVER_NS" link set eth0 up

ip -n "$CLIENT_NS" route add default via 10.10.1.1
ip -n "$SERVER_NS" route add default via 10.10.2.1
ip -n "$LEFT_NS" route add 10.10.2.0/24 via 10.10.12.2
ip -n "$RIGHT_NS" route add 10.10.1.0/24 via 10.10.12.1

ip netns exec "$LEFT_NS" sysctl -q -w net.ipv4.ip_forward=1
ip netns exec "$RIGHT_NS" sysctl -q -w net.ipv4.ip_forward=1

ip netns exec "$LEFT_NS" tc qdisc replace dev veth-r1-core root \
    netem delay 25ms rate 20mbit limit 1000
ip netns exec "$RIGHT_NS" tc qdisc replace dev veth-r2-core root \
    netem delay 25ms rate 20mbit limit 1000

trap - ERR

echo "Dumbbell topology created."
echo "client: 10.10.1.2   server: 10.10.2.2"
echo "bottleneck: 20 Mbit/s each direction, about 50 ms base RTT"
echo "Verify with: $(dirname "$0")/check.sh"
