# How This Agent Was Built

This is a step-by-step account of how the Writer-Reviewer workflow in this repo was created, deployed, evaluated, and hardened, using the `microsoft-foundry` skill end-to-end.

## 1. Define the workflow

**Ask:** "Create a multi-agent workflow app with Agent Framework SDK. Writer-Reviewer content collaboration. The final workflow output is plain text containing the refined content after the writer-reviewer collaboration."

- Used the Microsoft Agent Framework Python SDK (`agent-framework==1.13.0`).
- Modeled two typed executors with `WorkflowBuilder`:
  - `Writer` — drafts content, later revises based on reviewer feedback, and returns exactly one final plain-text artifact.
  - `Reviewer` — reviews the draft and returns concise, internal-only feedback.
- Wired the graph: `writer -> reviewer -> writer`, with `output_from=[writer, reviewer]` so the workflow can yield the final output from either node.
- Enforced the "final output only" contract directly in both `Writer` prompts (`_create_draft` and `revise`) so the workflow never leaks drafts, reviewer feedback, or step labels — even if a user prompt asks to see intermediate steps.

Result: [app.py](app.py)'s `Writer`, `Reviewer`, and `build_workflow`.

## 2. Local testing

- Added `tests/test_workflow.py` with unit tests around the workflow contract (2 tests passing).
- Verified both CLI mode (`python app.py "<prompt>"`) and hosted server mode (`ResponsesHostServer`) start without errors.
- Fixed a hosting mismatch: `workflow.as_agent()` needs the start executor to accept `list[Message]`, not just a single `Message` — added a `draft_messages` handler on `Writer` for that.
- Fixed the deployment entrypoint: Foundry runs `python app.py` with **no arguments**, so `main()` now defaults to starting the Responses server when no `prompt` is given (`args.server or not args.prompt`).

## 3. Debug tooling

- Set up `.vscode` launch configs for **Debug Local Agent/Workflow HTTP Server** (starts the Responses server + opens Foundry Toolkit Agent Inspector) and **Debug Local Agent/Workflow in Terminal** (direct CLI run).
- Installed `agent-dev-cli` for local debugging, but separately with `--no-deps`, because it pins an outdated `agent-framework-core<1.3.0` cap that would otherwise downgrade the runtime SDK. This is documented in [requirements-dev.txt](requirements-dev.txt) and [README.md](README.md).

## 4. Deploy to Microsoft Foundry

- Reused an existing Foundry project (`agent-workflow-prj` in resource `ron-agent-workflow-foundry`) with model deployment `gpt-5.4-mini`.
- Configured direct-code hosting in [azure.yaml](azure.yaml):
  - `host: azure.ai.agent`, `kind: hosted`
  - `codeConfiguration`: `entryPoint: app.py`, `runtime: python_3_14`, `dependencyResolution: remote_build`
  - `container.resources`: 0.5 CPU / 1 GiB
  - `protocols`: `responses` v2.0.0
- Deployed with `azd` (`AZURE_DEV_USER_AGENT=microsoft_foundry_skill azd deploy`), producing agent `foundry-workflow-2`, now at version 3.
- Smoke-tested the deployed agent with a real prompt (launch announcement) and confirmed clean plain-text output.
- Ran the built-in health check (11 passed, 0 failed, 2 expected skips).

## 5. Evaluation

- Generated a 15-case synthetic dataset (`smoke-core`, [datasets/smoke-core](datasets/smoke-core)) covering normal and adversarial prompts (e.g., requests to leak drafts/reviewer feedback, exact-string preservation, mixed-format asks).
- Created a rubric-based evaluator ([evaluators/smoke-core/rubric_dimensions.json](evaluators/smoke-core/rubric_dimensions.json)) wired through [eval.yaml](eval.yaml).
- First run flagged a real evaluator bug: the rubric was scoring the hidden internal reviewer feedback instead of only the observable final output. Fixed the rubric/baseline instructions and re-uploaded as evaluator version 2.
- Re-ran evaluation against agent v3 (`smoke-core-v2`, eval `eval_2750f3f59a2545f49457c3ff48e1cdd1`, run `evalrun_a6f3d7e6885543c3874673e1282767a9`):
  - **15 total, 6 passed, 9 failed, 0 errored.**
  - No execution/runtime errors — every failure was a content/behavior gap, not a crash.
- Investigated failures by directly invoking the deployed agent with one of the adversarial cases and confirmed the root cause: v3 was leaking `Draft` / `Review` / `Final` section labels for prompts that explicitly asked to see the process, instead of holding the line on "final output only."
- Hardened the `Writer` instructions and the `revise` prompt in [app.py](app.py) to explicitly refuse to expose intermediate artifacts even under adversarial prompting, then re-validated locally before considering another deploy + re-eval cycle.

## 6. Tracing

- Added OpenTelemetry tracing via `agent_framework.observability.configure_otel_providers`, called once in `configure_tracing()` at startup.
- Local/dev: tracing is enabled only when a target is configured — either `VS_CODE_EXTENSION_PORT` (Agent Inspector) or an explicit `OTEL_EXPORTER_OTLP_ENDPOINT`. When neither is set, `configure_tracing()` is a no-op so nothing spams a non-existent local collector, and the hosted Foundry runtime's own telemetry setup is left untouched.
- Foundry Toolkit integration: when running under the VS Code debugger, `VS_CODE_EXTENSION_PORT` is passed through so traces stream straight into the Agent Inspector.
- `enable_sensitive_data=True` so spans capture full prompt/completion text for debugging draft/review/final content flow.
- Configurable via standard `OTEL_EXPORTER_OTLP_ENDPOINT` / `OTEL_EXPORTER_OTLP_PROTOCOL` env vars (see [.env.example](.env.example)) to point at any OTLP-compatible backend, including Azure Monitor/App Insights linked to the Foundry project.

## Key lessons

- Foundry's hosted entrypoint contract (`python app.py`, no args, `list[Message]`-capable start executor) must be handled explicitly — it's easy to build something that only works from the CLI.
- Evaluators need the same "final output only" discipline as the agent: an evaluator that can see internal state will produce misleading scores.
- A 0-errored, N-failed eval result means the app is stable but not yet meeting behavioral requirements — worth invoking the agent directly on a failing case before changing anything, to confirm the actual failure mode instead of guessing.
