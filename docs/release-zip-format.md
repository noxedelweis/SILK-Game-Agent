# ZIP format invariant for SILK updater

The installed updater has intentionally strict archive member validation: each ZIP
entry must be a regular file or directory. Entries with permission bits such as
\`0o600\` but without the \`stat.S_IFREG\` file type are rejected as special files.

The v0.5.1 agent ZIP accidentally contained 34 such members; user update failed
on \`start_without_ai.bat\` and the existing installation was left unchanged.
Fixed in v0.5.2 by rebuilding those members with explicit file type.

## Required packaging snippet

\`\`\`python
import stat
import zipfile

member = zipfile.ZipInfo("SILK_Game_Agent_v0.5.2/start_without_ai.bat")
member.create_system = 3
member.external_attr = (stat.S_IFREG | 0o644) << 16
member.compress_type = zipfile.ZIP_DEFLATED

with zipfile.ZipFile("release.zip", "w") as archive:
    archive.writestr(member, b"contents")
\`\`\`

Never remove or weaken \`updater._valid_member\` to accommodate an invalid release.
On every new version, assert all regular files pass \`stat.S_ISREG(info.external_attr >> 16)\`
and perform a full \`safe_extract(zip_path, temp_folder, expected_version_dir)\`
with the *previously released* updater. Test extraction, 50 agent tests,
and GitHub's release-asset SHA-256 before making the release public.

GitHub Actions \`.github/workflows/publish-v052.yml\` enforces the ZIP member
type and hashes for the v0.5.2 release. Keep these checks in all future
release workflows.

The Windows EXE must include the same exact ZIP and its matching pinned SHA-256.
Keep OpenMW settings, saves, old versions, and the local wiki intact.