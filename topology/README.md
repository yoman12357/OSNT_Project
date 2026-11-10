# Linux netns dumbbell topology

The scripts create this isolated topology:

```text
rls-client              rls-r1                  rls-r2              rls-server
10.10.1.2 --- 10.10.1.1 | 10.10.12.1 === 10.10.12.2 | 10.10.2.1 --- 10.10.2.2
                                  20 Mbit/s, 25 ms one-way
```

Both directions of each outer access link have a 1000 Mbit/s rate and 5 ms delay.
Both directions of the inter-router bottleneck have a 20 Mbit/s rate and 25 ms delay.
Each shaped interface has a 1000-packet queue limit.
The nominal base RTT is 2 * (5 + 25 + 5) = 70 ms, excluding processing and queueing.
The host's normal interfaces and routes are not changed.

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

`setup_dumbbell.sh` adds `rls-client2` and `rls-server2` for two competing flows.
Their access links use the same 1000 Mbit/s and 5 ms settings in both directions.
Run `check_dumbbell.sh` to verify both pairs and all shaped interfaces.
The cleanup script removes only the six named `rls-*` project namespaces when present.

For the later picoquic experiment, start the server inside `rls-server`, bind
it to `10.10.2.2`, and run the client inside `rls-client` against that address.
Use `../build/picoquicdemo -h` to check the exact CLI options.
