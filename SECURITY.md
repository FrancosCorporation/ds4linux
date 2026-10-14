# Security Policy

## Supported versions

| Version | Supported |
|---|---|
| 2.1.x | ✅ current development branch |
| 2.0.x | ✅ latest release |
| < 2.0 | ❌ no security fixes (rebase or update) |

## Reporting a vulnerability

Please **do not** open a public issue for security reports. Use GitHub's
private vulnerability reporting:

**https://github.com/FrancosCorporation/ds4linux/security/advisories/new**

If that form is unavailable, open an issue titled `[SECURITY]` asking for a
private channel and do not include exploit details in it.

Include as much of the following as you can:

- DS4Linux version (Help → *Configurações* shows it) and how it was installed
  (`.deb`, `install.sh`, or from source).
- Distribution, kernel version and whether the controller is on USB or
  Bluetooth.
- Impact: what an attacker gains and from what starting point (local user,
  physical access, malicious profile file, …).
- Minimal reproduction steps or a proof of concept.

## Scope

Especially relevant for this project:

- **Privilege escalation**: the installer, `pkexec`/polkit invocation,
  `packaging/deb/postinst`, udev rules shipped in `udev/` and any write to
  `/etc` or `/dev`.
- **Credential handling**: the app must never persist a password. Any
  regression there (see `SEC-03` in `plan.md`) is in scope.
- **Untrusted input**: profile import (`~/.config/ds4linux/profiles/*.json`),
  DSU/UDP traffic on `127.0.0.1:26760`, and any file the GUI parses.
- **Device safety**: writing malformed events to `uinput`/HIDRAW that could
  wedge a device or the session.

Out of scope: crashes that require already having root, physical denial of
service, and game-specific incompatibilities (tracked as regular issues).

## Response

This is a hobby project maintained in spare time, so no SLA is promised — but
reports get an acknowledgement when read, a fix or a documented mitigation
before the next release when accepted, and credit in the `CHANGELOG.md`
unless you prefer otherwise.

There is no bug bounty; gratitude is given in the changelog and the release
notes.
