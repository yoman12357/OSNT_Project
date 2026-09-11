# Linux netns dumbbell topology

The scripts create this isolated topology:

```text
rls-client              rls-r1                  rls-r2              rls-server
10.10.1.2 --- 10.10.1.1 | 10.10.12.1 === 10.10.12.2 | 10.10.2.1 --- 10.10.2.2
                                  20 Mbit/s, about 50 ms RTT
```

Both directions of the inter-router bottleneck have 25 ms delay, a 20 Mbit/s
rate, and a 1,000-packet netem queue. The host's normal interfaces and routes
are not changed.

Create and verify the topology:

```bash
cd topology
sudo ./setup.sh
sudo ./check.sh
```

Remove it after testing:

```bash
sudo ./cleanup.sh
```

Only `rls-client`, `rls-r1`, `rls-r2`, and `rls-server` are removed by the
scripts.

For the later picoquic experiment, start the server inside `rls-server`, bind
it to `10.10.2.2`, and run the client inside `rls-client` against that address.
Use `../build/picoquicdemo -h` to check the exact CLI options.
