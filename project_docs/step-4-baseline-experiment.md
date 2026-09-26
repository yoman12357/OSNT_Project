# Step 4: Baseline CUBIC experiment and cwnd plot

## Objective

Run a baseline CUBIC transfer over the network-namespace dumbbell topology
created in Step 3, and produce a congestion-window plot from the resulting
qlog. This baseline is later compared against the rate-limited increase
implementation (Step 8).

## Environment

- Topology: `rls-client` — `rls-r1` == 20 Mbit/s, 25 ms each way ==
  `rls-r2` — `rls-server`. About 50 ms base RTT.
- Bottleneck queue: `netem limit 1000` packets (large, buffer-fill loss).
- Picoquic congestion control: CUBIC.
- Test file: 20 MB random binary (`file_20M.bin`), regenerated per run.
- Time: simulated as real wall-time inside the namespaces.

## How the experiment was run

### 1. Bring up the topology

    cd topology
    sudo ./setup.sh
    sudo ./check.sh

### 2. Start the server inside `rls-server`

    cd ~/OSNT_Project
    rm -f /tmp/qlog_baseline/*.qlog
    mkdir -p /tmp/qlog_baseline

    sudo ip netns exec rls-server \
        ./build/picoquicdemo -1 -p 4443 \
        -c certs/cert.pem -k certs/key.pem \
        -w "$PWD" -G cubic \
        -q /tmp/qlog_baseline -L

### 3. Run the client inside `rls-client`

    sudo ip netns exec rls-client \
        ./build/picoquicdemo -D -G cubic \
        -t certs/test-ca.crt -n test.example.com \
        -q /tmp/qlog_baseline -L \
        10.10.2.2 4443 /file_20M.bin

### 4. Capture the qlog

Picoquic writes two qlog files, one per side of the connection, named after
the Initial CID:

    e6f8eac3ee8923d1.b11c.server.qlog    (7.4 MB)
    e6f8eac3ee8923d1.client.qlog         (6.1 MB)

The **server** qlog is used for the cwnd plot, because the server is the
sender of the 20 MB payload.

### 5. Plot the cwnd

`plot_cwnd.py` extracts every `metrics_updated` event from the server qlog
and plots `cwnd` versus time. The qlog preamble declares
`"time_units": "us"`; the script reads that and divides accordingly.

    python3 plot_cwnd.py experiments/baseline/e6f8eac3ee8923d1.b11c.server.qlog \
                       experiments/baseline/cubic_cwnd_baseline.png

## Result

Client summary:

    Received 20971587 bytes in 9.185032 seconds, 18.265880 Mbps.

- **Transfer time:** 9.19 seconds
- **Throughput:** 18.27 Mbit/s = 91.4% of the 20 Mbit/s link
- **cwnd range:** 15.0 KB min, 442.2 KB max, 226.1 KB average
- **Sample count:** 676 cwnd samples over 9.01 s

## Interpretation

The plot shows the expected CUBIC behaviour on a large-queue dumbbell:

1. **Slow start** from 15 KB (initial cwnd) to about 440 KB in 0.7 s.
2. **One buffer-fill loss** at 3.5× the path BDP (path BDP ≈ 125 KB for
   20 Mbit/s × 50 ms). The sharp drop to about 200 KB is CUBIC's
   multiplicative decrease (β = 0.7) applied once, then a second loss
   bringing cwnd down further.
3. **Congestion avoidance** in the concave portion of the cubic curve for
   about 1.5 s, then a convex climb toward the end of the transfer.

Peak cwnd / BDP ≈ 3.5, consistent with a bottleneck queue large enough to
hold about 315 KB before overflowing. That is the expected behaviour for a
`netem` `limit 1000` queue.

This baseline is what the rate-limited increase implementation will be
compared against in Step 8.

## Files produced

    experiments/baseline/
        e6f8eac3ee8923d1.b11c.server.qlog    (source data, git-ignored)
        e6f8eac3ee8923d1.client.qlog         (source data, git-ignored)
        cubic_cwnd_baseline.png              (plot, tracked)

The qlog files are not committed because they are large binary artifacts
that can be regenerated from the commands above. The PNG plot is committed
because it is the deliverable of this step.
