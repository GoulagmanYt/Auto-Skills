# Compatibility

The separate `codex-candidate.yml` workflow tests an exact requested version or the resolved npm `latest` tag on three systems. Its receipts are diagnostic; only a reviewed completed installed-package run can justify updating the supported baseline. Release checks remain pinned to 0.166.0.

Task-aware preparation uses Codex 0.166.0's native lifecycle hooks and probes their exact definitions. A failed probe retains launch selection with an explicit limitation. See [covered clients and fallback behavior](automatic-skills.md); other clients bypassing the CLI wrapper are not automatically covered.

Completed agent work and sustained per-task guide consultation are observed on Windows with native Codex 0.166.0. The hosted matrix passed unit checks on Linux/macOS/Windows with Python 3.11 and 3.13, plus installed wheel/sdist and native catalog/preparation checks on all three systems. See [actual hosted outcomes, including failed attempts](https://github.com/GoulagmanYt/Auto-Skills/blob/801b1e037448123553ad1301736df93c46a3025d/reports/automatic-skills-hosted-ci.json). Hosted checks do not claim model obedience or completed agent tasks on Linux/macOS.

| Component | Initial alpha contract |
|---|---|
| Python | 3.11+; CI matrix 3.11 and 3.13 |
| Codex CLI | 0.166.0 is the pinned native test baseline |
| Platforms | Windows, Linux and macOS: hosted unit and installed native checks; see reports/automatic-skills-hosted-ci.json (historical baseline: reports/hosted-ci.json) |
| Git | Required for repository provisioning and scoped refresh |
| Runtime Python packages | None outside the standard library |
| Node | Optional; required for Repomix or npm-distributed competitors |

The project does not claim every future Codex version is compatible. Native profile loading and skill catalog discovery can change. A version becomes supported after its packaged native checks pass. The presence of a workflow is not evidence that hosted CI has run.

The standalone Codex executable bypasses Auto-Skills. Workspace isolation described here applies to launches through the wrapper. The launch profile configures the native catalog. Native prompt hooks refresh validated task instructions when targets change; newly selected guides can be read by verified path without assuming a live catalog rewrite. If hooks are unavailable, use the manager task command or a new scoped launch.

Linux/macOS profiles are applied in new shells. PowerShell launchers can update the current session. Removing a running wrapper cannot alter its parent's environment; open a new shell after uninstall. Existing terminal processes may retain old PATH/function definitions.

Optional downloaded tools have their own runtime/platform constraints. Offline operation uses bundled guidance and local Python tools and records unavailable downloads honestly.
