# Security policy

## Reporting a vulnerability

Please do not open a public issue for security problems. Use GitHub's "Report a vulnerability" (private security advisory) on this repository.

## What the tool does to stay safe

- Uploaded ZIPs are read in memory. Code is parsed with `ast`, never imported, installed, or executed.
- Archives with path traversal (`../`), absolute paths, drive letters, symbolic links, or suspicious compression ratios are rejected.
- File-count and size limits apply to every input.
- Repository content is sent to the model as untrusted data; the system instruction tells the model never to follow instructions found in it, and every model citation is checked against the real files.
- Test execution is opt-in, local Git repositories only, and runs in a temporary worktree with secret-looking environment variables removed. It is **not** a sandbox.
- Reports never contain settings, environment variables, or API keys.

See `docs/SECURITY.md` for the full threat model.
