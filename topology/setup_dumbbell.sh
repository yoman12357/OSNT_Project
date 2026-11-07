#!/usr/bin/env bash
set -euo pipefail
# Two endpoint pairs share the same shaped inter-router link.
DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
if [[ ${EUID} -ne 0 ]]; then echo "Run with sudo or inside a root-mapped user namespace." >&2; exit 1; fi
for namespace in rls-client2 rls-server2; do
    if ip netns list | awk '{print $1}' | grep -Fxq "${namespace}"; then ip netns delete "${namespace}"; fi
done
bash "${DIR}/setup.sh"
trap 'bash "${DIR}/cleanup.sh"' ERR
ip netns add rls-client2
ip netns add rls-server2
ip link add veth-c2 type veth peer name veth-r1-c2
ip link add veth-s2 type veth peer name veth-r2-s2
ip link set veth-c2 netns rls-client2
ip link set veth-r1-c2 netns rls-r1
ip link set veth-s2 netns rls-server2
ip link set veth-r2-s2 netns rls-r2
ip -n rls-client2 link set veth-c2 name eth0
ip -n rls-server2 link set veth-s2 name eth0
ip -n rls-client2 link set lo up
ip -n rls-server2 link set lo up
ip -n rls-client2 addr add 10.10.3.2/24 dev eth0
ip -n rls-r1 addr add 10.10.3.1/24 dev veth-r1-c2
ip -n rls-server2 addr add 10.10.4.2/24 dev eth0
ip -n rls-r2 addr add 10.10.4.1/24 dev veth-r2-s2
ip -n rls-client2 link set eth0 up
ip -n rls-server2 link set eth0 up
ip -n rls-r1 link set veth-r1-c2 up
ip -n rls-r2 link set veth-r2-s2 up
ip -n rls-client2 route add default via 10.10.3.1
ip -n rls-server2 route add default via 10.10.4.1
ip -n rls-r1 route add 10.10.4.0/24 via 10.10.12.2
ip -n rls-r2 route add 10.10.3.0/24 via 10.10.12.1
trap - ERR
echo 'Six-namespace dumbbell ready: two client/server pairs share the 20 Mbit/s bottleneck.'
