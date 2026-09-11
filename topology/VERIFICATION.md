# Step 3 verification result

The topology scripts were executed and verified on 2026-09-11.

Checks performed:

- all four namespaces were created;
- all six ends of the three veth pairs were brought up;
- client and server default routes were installed;
- both routers had forwarding and opposite-LAN routes;
- both bottleneck directions had the requested netem qdisc;
- the client successfully reached the server through both routers; and
- cleanup deleted all four project namespaces.

Observed result:

```text
Namespaces: OK
3 packets transmitted, 3 received, 0% packet loss
Steady ping RTT: about 50.2 ms
Forward qdisc: netem, delay 25 ms, rate 20 Mbit/s, limit 1000
Reverse qdisc: netem, delay 25 ms, rate 20 Mbit/s, limit 1000
Cleanup: PASS
```

The verification used a temporary user/mount namespace so it could exercise
the real `ip netns`, routing, forwarding, traffic-control, and ping commands
without changing the host network. Normal persistent activation uses:

```bash
cd topology
sudo ./setup.sh
sudo ./check.sh
```

Run `sudo ./cleanup.sh` after an experiment.
