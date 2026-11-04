# Compatibility

| Component | Initial alpha contract |
|---|---|
| Python | 3.11+; CI matrix 3.11 and 3.13 |
| Codex CLI | 0.166.0 is the pinned native test baseline |
| Platforms | Windows, Linux, macOS workflows; local evidence is platform-specific |
| Git | Required for repository provisioning and scoped refresh |
| Runtime Python packages | None outside the standard library |
| Node | Optional; required for Repomix or npm-distributed competitors |

The project does not claim every future Codex version is compatible. Native profile loading and skill catalog discovery can change. A version becomes supported after its packaged native checks pass. The presence of a workflow is not evidence that hosted CI has run.

The standalone Codex executable bypasses Auto-Skills. Workspace isolation described here applies to launches through the wrapper. Scope is selected at session launch; a session that later changes working directories must use the lock appropriately or start a new scoped session.

Linux/macOS profiles are applied in new shells. PowerShell launchers can update the current session. Removing a running wrapper cannot alter its parent's environment; open a new shell after uninstall. Existing terminal processes may retain old PATH/function definitions.

Optional downloaded tools have their own runtime/platform constraints. Offline operation uses bundled guidance and local Python tools and records unavailable downloads honestly.
