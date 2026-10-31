# SILK Navigation 2.0 — v0.5.0 (experimental)

Public release: https://github.com/noxedelweis/SILK-Game-Agent/releases/tag/v0.5.0

## What it actually does
- Existing v0.3 OpenMW log observer and v0.4.12 micro-route are preserved.
- New operator-approved **Navigation 2.0** reads `SILK_OBS_V03` game coordinates, calibrates W and D, and follows 1-3 relative waypoints with a hard 12-pulse input cap **including** calibration.
- Input format: `35,15; 65,15; 65,-20`. All targets are relative to the initial position; waypoint segment length is 15-130 engine units.
- Every step is followed by an in-engine sample; focus loss, ESC, stale telemetry, cell changes, direction mismatch and blocked progress terminate the session. No quest, door opening or camera turning logic.
- Optional `SILK_ENV_V050` read-only Lua player script reports position, yaw, nearby door record IDs and nearby actor record IDs. It is NOT installed or enabled automatically. Installation via an explicit button backs up `openmw.cfg` and requires OpenMW to be closed and restarted.
- `Осмотреть местность` requires fresh environment telemetry and never injects controls.

## Validation
- 85 passed Python unit tests, 1 Windows-specific test skipped under Linux.
- Windows x64 PE launcher built successfully; SHA-256 of EXE and bundled agent validated by a passing GitHub Actions release job.
- **Not validated in the user's live Windows/OpenMW yet.** Real multi-waypoint and the optional Lua script are experimental.

## Near-term next step
1. Update the running app to v0.5.0.
2. In a safe flat area test two waypoints: `35,15;65,15`.
3. Report the complete outcome. If successful, close OpenMW and explicitly install optional read-only environment probe via the button, then restart and press `Осмотреть местность`.
4. Do not claim free navigation or named-location quests before path/target grounding and obstacle control are tested.

## References
- OpenMW 0.51 Lua overview: https://openmw.readthedocs.io/en/stable/reference/lua-scripting/overview.html
- OpenMW 0.51 API self and rotation: https://openmw.readthedocs.io/en/openmw-0.51.0/reference/lua-scripting/openmw_core.html
- Nearby door and actor lists: https://openmw.readthedocs.io/en/latest/reference/lua-scripting/openmw_nearby.html
