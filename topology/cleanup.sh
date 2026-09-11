#!/usr/bin/env bash
set -euo pipefail

if [[ ${EUID} -ne 0 ]]; then
    echo "Run this script as root: sudo $0" >&2
    exit 1
fi

for namespace in rls-client rls-r1 rls-r2 rls-server; do
    if ip netns list | awk '{print $1}' | grep -Fxq "$namespace"; then
        ip netns delete "$namespace"
        echo "Deleted $namespace"
    fi
done
