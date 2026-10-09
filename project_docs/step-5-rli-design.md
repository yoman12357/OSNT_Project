# Step 5: Rate-Limited Increase design for picoquic CUBIC

## Source requirements

This design follows
[`draft-ietf-ccwg-ratelimited-increase-11`](https://datatracker.ietf.org/doc/html/draft-ietf-ccwg-ratelimited-increase-11),
published 6 September 2026. The draft replaces CUBIC's conservative
"do not grow while application limited" rule with bounded growth.

For every CUBIC path, the required behavior is:

1. initialize `maxFS` to the initial congestion window;
2. update `maxFS = max(maxFS, FlightSize)` whenever FlightSize changes;
3. reset `maxFS` to zero after any congestion-window reduction;
4. cap slow-start growth at `2 * maxFS`; and
5. cap congestion-avoidance growth at `maxFS + SMSS`.

All additions and multiplications used for a cap must saturate at
`UINT64_MAX` rather than wrap.

## Existing picoquic behavior

`picoquic/cubic.c` currently suppresses growth when its sender-limited
timestamps indicate that the application did not fill the window. Slow start
has a second gate in `picoquic_cc_slow_start_increase()` through
`cnx->cwin_blocked`. Removing only the timestamp condition is therefore not
enough: RLI slow start must calculate its normal ACK-driven candidate before
applying the cap.

## State and update locations

The RLI measurements are per `picoquic_path_t`, because both
`bytes_in_transit` (FlightSize) and the CUBIC instance are per path.

| Draft rule | State/function | Location |
|---|---|---|
| Enable A/B behavior | `is_rli_enabled`; CUBIC option `rli=on` | `picoquic/cubic.c` |
| Store `maxFS` | `rli_max_flight_size` | `picoquic/picoquic_internal.h` |
| Initialize to initcwnd | `cubic_reset()` | `picoquic/cubic.c` |
| Observe every FlightSize change | `picoquic_update_max_flight_size()` after enqueue and dequeue accounting | `picoquic/sender.c` |
| Reset after a decrease | `cubic_rli_reset_after_reduction()` from `cubic_enter_recovery()` | `picoquic/cubic.c` |
| Bound slow-start growth | `cubic_rli_apply_limit()` with `2 * maxFS` | `picoquic/cubic.c` |
| Bound CA growth | `cubic_rli_apply_limit()` with `maxFS + send_mtu` | `picoquic/cubic.c` |
| Explain behavior in results | qlog fields for `maxFS`, limit, and cap state | `picoquic/logwriter.c`, `loglib/qlog*.c` |

Updating at send time is essential: sampling only on an ACK can miss a peak
FlightSize that has already fallen. Updating after dequeue is also necessary
after a cwnd reduction reset, because the first new FlightSize measurement
can be the remaining in-flight data decreasing, not a new transmission.

## Growth behavior

RLI is an opt-in CUBIC option during experimental validation:

```text
-G cubic -H rli=off    existing behavior
-G cubic -H rli=on     bounded rate-limited growth
```

When enabled, CUBIC calculates the same growth candidate it normally would,
but the result cannot grow beyond the phase-specific RLI limit. The cap never
reduces an already larger cwnd; reduction of an underused window is the job of
Congestion Window Validation, not this draft.

If the cap clips CUBIC's result, its Reno-friendly shadow window (`W_reno`) is
also clipped. This prevents a later ACK from restoring growth that RLI just
disallowed. The CUBIC epoch and curve parameters otherwise retain their normal
behavior.

## Reduction and spurious-loss behavior

Loss, timeout, ECN, and HyStart congestion responses converge on
`cubic_enter_recovery()`, which performs the reduction and then resets
`maxFS`. If a loss is later classified as spurious, CUBIC's old cwnd and epoch can be
restored, but the pre-reduction `maxFS` is not restored. Draft version 11 says
that a reduction for any reason starts a new `maxFS` observation interval.

## CUBIC Congestion Avoidance interpretation

Section 3 explicitly gives `limit(maxFS) = maxFS + SMSS` for Congestion
Avoidance, and Section 4.5 applies the Section 3 rules to CUBIC without giving
a different expression. The implementation therefore computes both the
CUBIC and Reno-friendly candidates required by RFC 9438 and caps the larger
candidate at `maxFS + send_mtu`.

There is a specification wording question worth confirming with the draft
authors: the general definition describes `limit()` as what the congestion
control algorithm would yield for one successfully acknowledged `maxFS`
flight, while the displayed CA derivation references RFC 5681. The current
choice follows the only explicit CA formula in version 11 and is conservative;
the project does not invent a separate time-dependent CUBIC limit.

DCUBIC shares helper code with CUBIC, so it has a separate initializer that
always leaves RLI disabled. This avoids changing an algorithm outside the
project scope.

## Validation design

The focused `cubic_rli` test covers option parsing, initialization, live
FlightSize accounting, post-reduction reinitialization, repeated bursts,
slow-start cap, Reno-friendly and cubic-dominant CA behavior, epoch exclusion,
loss/ECN/timeout/spurious recovery, and legacy/off behavior. Linux validation must additionally
run the full picoquic suite and repeat the netns experiment at least three
times for both a rate-limited quicperf workload and a continuously backlogged
bulk workload.
