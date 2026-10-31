# SILK Game Agent — Navigation Next (candidate, not a public release)

Stable installed baseline: **v0.5.2**. This branch is an experimental candidate for review and CI; do **not** install over the stable EXE yet.

## Verified against the user's OpenMW log

The log contains `SILK_ENV_V050` with a valid Balmora position, heading, nearby door coordinates, and actor listing. Lines that merely mention `env050.lua` are *not* Lua errors. Lua `onUpdate(dt)` may pause simulation-time progression when OpenMW loses focus.

## Changes

- `env_reader.inspect_environment`: read-only last-known sample with `current`, `stale`, `unknown`, or `missing`; when OpenMW's `[HH:MM:SS.mmm I]` line prefix is available, use *that line time*, not the whole file mtime. Raw un-timestamped values must never be certified current for movement.
- `env_diagnostics`: don't classify routine `env050.lua` mentions as Lua exceptions; only classify explicit severity/error text.
- `object_nav`: preview a detected door and a bounded 1–3 waypoint **straight-line standoff approach**. It does **not** open doors or avoid obstacles. The player must provide distinct consent, return focus to OpenMW, produce *new* environment telemetry, and pass a v0.3 coordinate consistency check before the first command. Existing navigation confirms every pulse and stops on ESC, focus loss, obstacles, changed heading, or missing telemetry.
- `feature_gates`: explicit Stable vs Experimental names. The C GUI gives experiments visibly separate buttons and explicit consent for movement; normal features remain unchanged.

## Test gates and remaining work

Run `PYTHONPATH=desktop python -m unittest discover -s tests -q` on both Windows and Linux (release-archive integration requires an actual staged ZIP). The local development environment passed 112 tests with one platform skip, plus the agent's 50 tests. The Windows EXE was cross-compiled but its GUI **has not been smoke-tested on the user's Windows/OpenMW**. The object approach is still pure straight-line and could meet a wall; it is not a general pathfinder. A later OpenMW navmesh pathfinding probe should avoid that limitation (see OpenMW's `openmw.nearby.findPath` API).

### Do not ship until

1. GitHub Actions both platforms green, including Windows native process/API cases.
2. Test real log with a paused OpenMW game; read-only inspection should show stale information, not fail.
3. Confirm active OpenMW foreground with fresh environment + v0.3 coordinates; short object approach only in a completely clear test area.
4. ZIP metadata passes the *installed* updater's `safe_extract` check; test paired EXE+agent update and rollback before public release.
5. Leave the v0.3 observer probe, 8064-page wiki, user OpenMW config, and saves unchanged.
