# Rate-limited CUBIC test result

- Date: 2026-10-10
- Branch: `test/rli-implementation`
- Commit: `d436b16098bb749b7af2cedc696b743182314d33`
- Build: Passed
- `picoquic_ct`: Passed
- `picohttp_ct`: Passed
- Total: 2/2 passed, 0 failed
- Test time: 20.97 seconds
- Dedicated `cubic_rli` test: Passed (`Success`)

This verifies that the new rate-limited CUBIC code compiles, passes the full
regression suite, and passes its focused implementation test.
