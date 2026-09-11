# Step 1: Picoquic installation and verification

## Environment

- Ubuntu 26.04 LTS on native Linux
- Linux kernel 7.0.0-29-generic, x86-64
- GCC 15.2.0
- CMake 4.2.3
- Ninja 1.13.2
- OpenSSL 3.5.5
- Picoquic commit `b69cc111827450e94f78c76314b81d17ce662ee1`

## Normal installation commands

Install the build and networking dependencies:

```bash
sudo apt update
sudo apt install -y build-essential cmake ninja-build git libssl-dev \
    iproute2 iputils-ping
```

Clone this fork and configure it. `PICOQUIC_FETCH_PTLS=Y` asks CMake to fetch
the compatible Picotls revision automatically.

```bash
git clone https://github.com/yoman12357/OSNT_Project.git
cd OSNT_Project
cmake -S . -B build -G Ninja \
    -DPICOQUIC_FETCH_PTLS=Y \
    -DWITH_OPENSSL=ON \
    -DCMAKE_BUILD_TYPE=RelWithDebInfo
cmake --build build --parallel "$(nproc)"
```

Run the upstream verification suites:

```bash
ctest --test-dir build --output-on-failure
```

## Verification performed on this checkout

The host had the OpenSSL runtime but did not have the development headers
installed system-wide. Since sudo required an interactive password, the
matching Ubuntu `libssl-dev` package was unpacked in a separate local work
area and passed to CMake. This does not change picoquic source code or add
machine-specific dependency files to the repository.

Results recorded on 2026-09-11:

```text
Full picoquic and Picotls build: PASS
picoquic_ct: PASS (29.53 seconds)
picohttp_ct: PASS (4.71 seconds)
CTest result: 100% passed, 0 failed
```

The following important build outputs were produced:

```text
build/picoquicdemo
build/picoquic_ct
build/picohttp_ct
build/picolog_t
build/libpicoquic-core.a
build/libpicoquic-log.a
```

The generated `build/` directory is intentionally ignored by Git. Every team
member can reproduce it using the commands above.

## CUBIC smoke-test commands

Start a one-connection server from the repository root:

```bash
./build/picoquicdemo -1 -p 4443 \
    -c certs/cert.pem -k certs/key.pem -w . -G cubic
```

In another terminal, run the client:

```bash
./build/picoquicdemo -D -G cubic \
    -t certs/test-ca.crt -n test.example.com \
    127.0.0.1 4443 /README.md
```

A successful run must show that the QUIC connection is established, the
certificate is verified, the requested file is received, and both processes
exit with code zero.

This smoke test was run on the fork after the fresh build. It negotiated HTTP/3
with CUBIC, verified the certificate, received the 10,042-byte `README.md`
stream, and both client and server exited with code zero.
