# Grok 1.0.30 strict sandbox compatibility on macOS

Two independent startup failures affect subscription seats with an isolated
`GROK_HOME`.

## Docker compatibility socket

Grok 1.0.30 refuses to apply its sandbox when `/var/run/docker.sock` is a symlink.
The runtime-socket deny resolver reports `endpoint is a symlink`; changing the
profile to an unrestricted one would discard the benchmark's isolation.

On this host, the alias pointed to an inactive
`/Users/ray/.docker/run/docker.sock`. The configured `desktop-linux` Docker
context also pointed directly to that user socket. With macOS administrator
authorization, only the global alias was moved to
`/private/var/run/docker.sock.agentbga-backup-20260913`. The real socket was left
unchanged. This is a host repair, not an automatic modification performed by the
harness. Docker may recreate the alias when its default socket integration is
reenabled; an upstream Grok resolver fix is the durable vendor solution.

To undo the host repair, first stop affected Grok runs and verify that no new
`/private/var/run/docker.sock` exists, then move the saved symlink back with
administrator privileges. Never overwrite a newly created socket.

## Shared subscription authentication

`GROK_AUTH_PATH` points to the native shared credential file outside the isolated
seat `GROK_HOME`. Strict mode otherwise denies access to it, making a logged-in
user appear signed out. Grok custom read grants accept directories only, so
adding the file itself fails with `Expected a directory but got a file`.

The compatibility profile grants its parent read-only and adds deny rules for
**every other basename**, including exact shorter prefixes and longer suffixes.
On macOS these become runtime Seatbelt rules, so new siblings are denied too.
Only the exact auth file remains readable; global config, sessions, hooks, the
auth lock and other files remain denied. The parent is never writable. Credentials
are neither copied into seat workspaces nor read/parsed by AgentBGA code.

This workaround is deliberately macOS-only: Linux's launch-time glob expansion
does not provide the same future-file guarantee, so the harness fails explicitly
there instead of silently broadening access. Names containing unsupported glob
syntax also fail explicitly.

Credential refresh writes stay with the user's native host Grok login outside
the seat sandbox. If native Grok needs to renew credentials, refresh/sign in on
the host, then resume the existing match. The seat profile does not grant global
credential-directory writes just to permit background refresh.
