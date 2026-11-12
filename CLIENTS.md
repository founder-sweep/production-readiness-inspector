# Inspector: coding-agent setup

Run local Python/FastAPI release checks and prepare a private before/after handoff.

## Runtime and credentials

Follow the existing runtime setup in the README. Use a dedicated Python 3.12+ environment. Set `CONTENTSWEEP_INSPECTOR_MCP_COMMAND` to the absolute path of its installed `prodcheck-mcp` executable. Launch from a trusted workspace; the working directory is not a filesystem sandbox. Do not install or execute dependencies from the project being assessed. Set `CONTENTSWEEP_INSPECTOR_ROOT` to the explicitly authorized inspection root. The server requires this root and accepts only contained relative inspection paths.

## Gemini CLI

Install the extension from this repository:

```sh
gemini extensions install https://github.com/founder-sweep/production-readiness-inspector --ref main
```

The explicit branch selects the integration source rather than an older Python runtime release archive. Provide the requested setting in the native installation prompt. API keys are sensitive settings. The extension supplies the existing skill and default MCP connection; it does not approve tool calls or spending. For a project-managed connection, merge the Gemini example from `client-configs/gemini.json` into the intended profile.

## Kilo

Use the published marketplace entry when available, or merge `client-configs/kilo.json` into your private user-level Kilo CLI configuration and install the existing skill. Alternatively set `KILO_CONFIG` to the absolute path of an explicitly trusted private configuration file. Kilo CLI rejects environment substitutions in untrusted project configuration and drops MCP entries with variable-bearing project headers; keep the supplied environment-based credentials in user-level configuration. The editor marketplace installs its prompted values into private MCP settings. The catalog entry includes a companion skill; companion installation requires a client version supporting that feature. Review prerequisites before installation.

## Cline

Ask Cline to follow this README and `llms-install.md`. Merge the entry in `client-configs/cline.json` into the editor extension's MCP settings and provide the named setting privately. Cline editor 4.1.26 supports `${env:NAME}` interpolation. Make those variables available in the client launch environment, or fill the actual values directly in the client's private MCP settings. Restart the client after changing its launch environment. The hosted editor example selects `streamableHttp` explicitly. Keep tool approvals enabled.

Cline CLI 3.0.74 stores its connection under a `transport` object. Use its native command to write that schema instead of copying the editor JSON into a CLI profile. With the required private setting(s) available in the launch environment:

```bash
cline mcp add contentsweep-inspector --yes --transport stdio -- "${CONTENTSWEEP_INSPECTOR_MCP_COMMAND}" --root "${CONTENTSWEEP_INSPECTOR_ROOT}"
```

For an isolated CLI profile, retain its `--config`, `--data-dir` and `--hooks-dir` options on configuration commands. Start a fresh Cline CLI task after adding the server so the model discovers its new tools. Copy the existing skill directory with every relative resource into the project's `.cline/skills/` directory; manual file copying does not require a second skill-install command. Verify an actual MCP result after setup.

## Cursor

Install the Cursor plugin from the marketplace or load this repository as a local plugin for development. Configure its declared variable in the plugin settings. The root `mcp.json` is the native plugin connection definition; the copy in `client-configs/cursor.json` is for a manually managed connection. For the manual copy, use Cursor's documented environment interpolation in place of the plugin variable. Preserve unrelated entries. With Cursor CLI, place local environments at absolute paths without spaces: the current CLI splits a no-argument stdio command containing spaces. A locally created executable symlink at a path without spaces is also suitable; it must point to the verified installed product executable. In native Cursor 3.29.15, Inspector's project-scoped Configure action returned "Plugin not installed". The tested recovery was to select Add for Myself, remove the failed project scope, save the declared variables in the private plugin configuration, and use the MCP server's Reload action. Verify Connected and the expected tools before running a task. This recovery does not require a second manually configured connection.

## Skill and first task

Read [inspect-release](skills/contentsweep-inspector/SKILL.md) and its relative references. Use the repository-owned synthetic example first and inspect the substantive result, not just execution success. Fixture approval never authorizes customer uploads, business meanings, purchases or downstream writes. For Inspector, read `metadata.complete`, `metadata.issues`, and `metadata.baseline` from the actual tool JSON. Pass the entire previous report, including its metadata and finding instances, as `baseline`; a summary is insufficient. The example directories are `defective` and `corrected`.

## Price and supported scope

Local CLI and MCP are free. Optional hosted metadata reports have three trials, then $19/100 reports.

Static local Python/FastAPI, Docker and GitHub Actions inspection. No target-code execution or source upload. Python 3.12+; reviewed source installation on macOS, qualified 0.3.0 wheel on Linux.

## Recovery and removal

Keep private keys out of source control and command history. Remove only this product's plugin/server/owned companion skill. Keep unrelated tools and settings. Kilo 7.8.27's native skill Remove action deletes `SKILL.md` and leaves companion files. After native removal, preview cleanup of this exact skill directory using the supplied ownership manifest:

```bash
python scripts/remove-owned-agent-skill.py --skill-dir "/absolute/path/to/.kilo/skills/inspect-release"
```

Review the matching paths, then repeat with `--apply` to remove only unchanged owned companion files. The helper refuses an active skill entry or a symlinked skill directory, and preserves modified files, unknown files and other skills. It does not edit client configuration. When names conflict, inspect the client's selected source path before installing or removing a skill. Client installation, marketplace acceptance, recommendations and paid adoption are separate outcomes.
