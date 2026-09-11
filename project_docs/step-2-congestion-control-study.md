# Step 2: Picoquic congestion-control study

## Congestion-control architecture

Picoquic maintains congestion control per path. The algorithm interface is
`picoquic_congestion_algorithm_t` in `picoquic/picoquic.h`. Each algorithm
provides callbacks to initialize state, process notifications, delete state,
and expose values for logging.

Important data structures are:

- `picoquic_cnx_t`: connection state and selected congestion algorithm.
- `picoquic_path_t`: per-path `cwin`, `bytes_in_transit`, MTU, pacing, RTT,
  and sender-limited timestamps.
- `picoquic_per_ack_state_t`: ACK information, newly acknowledged/lost bytes,
  prior flight size, and application/cwin-limited flags.

The default algorithm is NewReno. Built-in algorithms are registered in
`picoquic/register_all_cc_algorithms.c` and include NewReno, CUBIC, DCUBIC,
FastCC, BBR variants, Prague, and C4.

## CUBIC implementation

The main implementation is `picoquic/cubic.c`. Its private CUBIC state tracks:

- slow start, recovery, or congestion-avoidance phase;
- recovery sequence and epoch timestamps;
- `ssthresh`;
- `K`, `W_max`, and `W_last_max`;
- the Reno-friendly estimate `W_reno`; and
- RTT-filter state used by HyStart.

`cubic_reset()` initializes the path congestion window to
`PICOQUIC_CWIN_INITIAL`. `cubic_notify()` implements the main state machine.
In congestion avoidance it computes the time-based CUBIC window and a
Reno-friendly window, then selects the larger value.

## Current sender-limited behavior

CUBIC currently guards slow-start and congestion-avoidance growth using:

```c
path_x->last_time_acked_data_frame_sent >
    path_x->last_sender_limited_time
```

When the condition is false, congestion-window growth is skipped. This is the
older conservative behavior that the rate-limited increase project needs to
replace with controlled, bounded growth.

`picoquic/sender.c` is also important:

- `picoquic_queue_for_retransmit()` increases `bytes_in_transit`.
- packet finalization records prior flight size and limited-state flags.
- packet preparation updates `last_sender_limited_time`.
- ACK/loss processing decreases bytes in transit and notifies the selected
  congestion algorithm.

## Mapping the IETF draft to picoquic

The draft introduces `maxFS`, the largest flight size observed since startup
or the last congestion-window reduction:

```text
initialization:             maxFS = initial_cwnd
when FlightSize changes:    maxFS = max(maxFS, FlightSize)
after any cwnd reduction:   maxFS = 0
```

Likely CUBIC implementation changes are:

1. Add rate-limited tracking state per path or to the CUBIC state.
2. Initialize it in `cubic_reset()`.
3. Update it where `sender.c` increases `bytes_in_transit`; observing only at
   ACK time can miss the peak flight size.
4. Reset it whenever loss, timeout, ECN, or another event reduces `cwin`.
5. Replace the current all-or-nothing sender-limited gate with candidate CUBIC
   growth followed by the draft's limit.
6. Keep internal `W_reno` and CUBIC epoch state consistent with a capped cwin
   so the sender cannot jump suddenly after leaving a limited period.
7. Log or expose `maxFS` so tests can verify the limit directly.

The exact CUBIC interpretation of `limit(maxFS)` must be fixed in the design
before coding. The draft defines it in terms of the increase produced by ACKs
for one `maxFS` flight; its `maxFS + SMSS` equation is the ordinary
congestion-avoidance example, while CUBIC itself is time-based.

## Relevant source files

- `picoquic/cubic.c`: CUBIC state machine and cwin calculation.
- `picoquic/cc_common.c` and `.h`: slow-start and HyStart helpers.
- `picoquic/sender.c`: in-flight accounting and limited-state detection.
- `picoquic/picoquic_internal.h`: internal path/connection state.
- `picoquic/loss_recovery.c` and `sacks.c`: ACK/loss processing.
- `picoquictest/congestion_test.c`: congestion-control tests.
- `picoquictest/app_limited.c`: application-limited tests.
- `loglib/csv.c` and `memory_log.c`: cwin and bytes-in-transit logging.

The existing congestion-control CSV includes time, cwin, blocked/limited
flags, congestion-control state, and bytes in transit. These fields will be
used for the Step 4 baseline graphs.

## Tests needed for the future implementation

- `maxFS` initialization and peak-flight tracking.
- Slow-start and congestion-avoidance caps.
- Reset after every type of cwin reduction.
- Normal behavior when the sender fully utilizes cwin.
- Repeated application-limited bursts.
- Independent state on multiple paths.
- Overflow-safe arithmetic.
- Full existing picoquic regression suite.

## References

- <https://datatracker.ietf.org/doc/draft-ietf-ccwg-ratelimited-increase/>
- <https://www.rfc-editor.org/rfc/rfc9002>
- <https://www.rfc-editor.org/rfc/rfc9438>
