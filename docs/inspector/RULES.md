# Rule contract and verified sources

Ruleset `2026.10.18.1`, October 18, 2026. Syntax means a recognized literal
declaration; inference means a bounded absence/presence review prompt. Confidence
1.0 describes deterministic extraction, not a calibrated probability or severity
estimate. Every finding has a rule version and file/line evidence. No raw source
excerpts, credential values or automated patches are returned.

| Rule/version | Severity | Applicability and evidence | Counterexample |
|---|---|---|---|
| PR-PY-001/2 | high | Recognized FastAPI(debug=True) or uvicorn.run(reload=True) call | Comments, strings, unrelated debug arguments, shadowed imports, literal False |
| PR-FASTAPI-001/2 | medium | Per FastAPI constructor, no directly declared conventional GET route in that module; **inference** | A registered @app.get route counts; a function name or unused decorator factory does not |
| PR-FASTAPI-002/1 | high | Direct conventional GET health route has literal status_code >= 400 | Default/successful status; dynamic status semantics remain outside literal checks |
| PR-DOCKER-001/2 | medium | External FROM lacks valid sha256 digest | scratch and previous stage aliases; dynamic base gives partial coverage |
| PR-DOCKER-002/2 | medium | Final stage's effective explicit USER is root/0, including internal-stage inheritance | Root used only in an unrelated build stage; final nonroot override |
| PR-DOCKER-003/1 | medium | Effective final shell-form CMD/ENTRYPOINT lacks leading exec | JSON exec form or shell form beginning exec; scripts themselves are not analyzed |
| PR-DOCKER-004/1 | high | Final startup invokes Uvicorn with --reload | Build-stage-only startup, unrelated string values |
| PR-CI-001/2 | high | Remote step/reusable workflow uses lacks full SHA; docker action lacks digest | ./local actions, full SHA/digest; run block strings are not action declarations |
| PR-CI-002/2 | high | Workflow/job scope literal permissions: write-all | read-all or explicit permission map; not a claim that every job inherits it |
| PR-SECRET-001/2 | high | Nonignored environment file exists; **inference**, contents/tracking uninspected | Ignored files and .env.example/.sample/.template |

The following primary sources were checked directly on October 18. These
justify narrow implementation choices, not broader competitor/platform claims
from the research report:

- [Docker build practices](https://docs.docker.com/build/building/best-practices/):
  tags can move; digest pinning trades automatic updates for controlled updates.
  The mutable-image rule is advisory medium severity.
- [Dockerfile reference](https://docs.docker.com/reference/dockerfile/): stage
  inheritance and command forms determine which declarations apply to the final
  stage. Image internals are outside a static local-file scan.
- [GitHub secure use](https://docs.github.com/en/actions/reference/security/secure-use):
  full commit references strengthen action immutability; verify the chosen SHA's
  origin separately. Inspector validates syntax only, not remote provenance.
- [Actions workflow syntax](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax):
  jobs, steps, permissions, local actions and Docker actions have distinct scopes.
- [FastAPI lifespan](https://fastapi.tiangolo.com/advanced/events/): lifecycle
  behavior needs application-specific review. The beta does not certify lifecycle
  or runtime health simply because a route is declared.
- [Git ignore patterns](https://git-scm.com/docs/gitignore): parent exclusion and
  negation guide the documented limited scan policy; this scanner does not query
  tracked status or global Git settings.
- [Official MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk):
  product stdio server and smoke use its typed server and real client lifecycle.
- [SARIF 2.1.0](https://docs.oasis-open.org/sarif/sarif/v2.1.0/os/sarif-v2.1.0-os.html)
  and its [official JSON schema](https://raw.githubusercontent.com/oasis-tcs/sarif-spec/main/sarif-2.1/schema/sarif-schema-2.1.0.json):
  rule identities, relative file URIs, locations, execution failure notifications
  and baselineState are exported and schema-validated locally.

The health-path list and CI severity threshold are explicit beta policy choices,
not universal production standards. No external fetch occurs during analysis.
