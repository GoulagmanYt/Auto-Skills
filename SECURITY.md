# Security policy

Auto-Skills is alpha software. Security fixes target the latest prerelease; older releases are not maintained.

Report vulnerabilities through the repository's private vulnerability reporting feature when available. If it is unavailable, open an issue requesting a private contact channel without exploit details, credentials or private source code. Maintainers must enable private reporting before announcing the alpha.

Useful reports include the version, operating system, Codex version, affected trust boundary, reproduction with synthetic files and expected behavior. Do not include authentication files, session transcripts or personal filesystem paths.

The threat model and limitations are in [docs/security-model.md](docs/security-model.md). Checksums establish integrity relative to a recorded source; they do not establish that instructions are safe. Remote skill scripts are never run during skill installation. Locally launched tools and native plugins retain their normal permissions.

Release artifacts are built by the release workflow. Review the workflow run and artifact checks before installation. Never treat a passing static filter as a security certification.
