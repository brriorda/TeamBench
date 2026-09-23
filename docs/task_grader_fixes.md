# Task generator and grader fixes for upstream review

## Purpose

This note records four focused TeamBench task-infrastructure corrections prepared for a future
upstream pull request. The changes fix generator or grader defects that can make a valid candidate
ungradable, report infrastructure failure as candidate failure, or award credit to unchanged
starter code.

The affected tasks are:

- `CR4_api_review`
- `DIST1_queue_race`
- `CROSS1_api_contract`
- `INC1_cascade_failure`

These are benchmark-fixture corrections, not changes to task objectives or agent prompts.

## Summary

### CR4_api_review

**Problem.** The generated pytest reset fixture iterated over every private module attribute and
cleared every dictionary. That included unrelated interpreter/module dictionaries and could corrupt
the test process before candidate behavior was evaluated.

**Fix.** `generators/gen_cr4_api_review.py` now clears only the seed-selected generated resource
store, for example `getattr(app_module, "_users").clear()`.

**Regression.** `test_cr4_reset_fixture_clears_only_generated_store` checks all three authored
seeds and rejects the former broad `dir(app_module)` loop.

### DIST1_queue_race

**Problem.** The grader invoked pytest with `--timeout` without installing `pytest-timeout`. Its
dependency setup used a silent fallback, and uv-created environments can omit the `pip` module
entirely. As a result, otherwise valid workspaces could receive misleading dynamic-test failures or
no native score.

**Fix.** `tasks/DIST1_queue_race/grade.sh` now:

1. enables `set -euo pipefail`;
2. bootstraps pip with `python3 -m ensurepip --upgrade`;
3. strictly installs `pytest` and `pytest-timeout` with `python3 -m pip`;
4. preflights the timeout option before candidate checks; and
5. contains no `|| true` dependency fallback.

TeamBench's `harness.grade_task` fallback preserves grader stdout and stderr when setup exits before
the task writes a native score.

**Regression.** `test_dist1_grader_bootstraps_pip_before_installing_timeout_plugin` verifies the
required command order and absence of the silent fallback. The grader was also exercised end to end
from a newly created pip-less uv environment and produced a native 12/12 passing score for a known
good workspace.

### CROSS1_api_contract

**Problems.** The task had five interacting infrastructure defects:

1. dependency installation used bare `pip`, hid stderr, and continued with `|| true`;
2. pytest and Go failures were suppressed or reduced to generic failed candidate checks;
3. the task requires Go, but its metadata declared only Python and the role images lacked Go; and
4. `failure_modes` was always empty, even when checks failed; and
5. checks hard-coded the seed-0 `User`/`userId` contract, preventing product and order seeds from
   earning full credit.

In a pip-less environment without Go, the old grader exited successfully, reported zero pytest
tests, and labeled the missing compiler as a candidate compilation failure.

**Fixes.** The CROSS1 condition now:

- declares `languages: [python, go]`;
- preflights `pytest`, `requests`, and the Go compiler before scoring candidate checks;
- bootstraps pip and strictly installs missing Python dependencies with quiet output;
- fails setup with a structured failure mode and nonzero exit;
- stores combined setup, pytest, and Go diagnostics in `score.json` as `grader_stderr`;
- removes silent `|| true` behavior from dependency and test execution;
- records the identifiers of failed candidate checks in `failure_modes`;
- reads the entity class and camelCase ID field from seed-specific `expected.json`; and
- provisions `golang-go`, `pytest`, and `requests` in the executor and verifier images.

**Regressions.** `tests/test_task_infrastructure.py` verifies that a missing Go compiler produces
`go_toolchain_missing` with retained diagnostics, that no candidate checks are scored first, that
the task metadata declares Go, and that both role images contain the required toolchains.

### INC1_cascade_failure

**Problems.** The seed-specific grader contained three correctness defects:

1. the `wrong_port` branch imported `generators.base` from the isolated candidate workspace, where
   the package is unavailable, so a correct seed-3 repair could not pass;
2. retry and atomic-write checks searched raw source text, allowing words in starter comments and
   docstrings to earn credit; and
3. the required repair order was scored through filesystem modification times, which do not
   reliably encode semantic edit order and can change during copying or bulk edits.

The untouched seed-0 starter previously received 8/10 checks because its comments contained words
such as `retry` and `atomic`.

**Fixes.** The INC1 grader now:

- reads the correct port directly from the trusted seed-specific `expected.json`, without importing
  generator code;
- uses AST structure to require executable retry/circuit-breaker logic in services A and B;
- behaviorally verifies that service C rejects incomplete records without committing them and
  atomically accepts a complete record; and
- preserves the explicit C → B → A/root repair-order requirement using an ordered workspace edit
  trace emitted by TeamBench's shared `write` and `run` tools.

The trace records only the relative paths whose contents changed and the responsible tool name; it
does not retain source contents, commands, model messages, environment variables, or credentials.
Trace collection is enabled only when generated verifier metadata sets `trace_workspace_edits`;
other TeamBench tasks do not incur workspace-snapshot overhead.
For configuration-rooted variants (`bad_timeout`, `bad_connection_string`, and `wrong_port`), the
final root-cause event is the edit to `config.json`. For code-rooted variants, it is the edit to the
generated service-A module. An event that changes multiple required targets at once cannot satisfy
the strict sequence.

The generator documentation now describes trace-based sequence validation instead of timestamp
comparison.

**Regressions.** `tests/test_task_infrastructure.py` verifies that comment-only starter code fails
the executable safeguards, that both direct writes and shell-command changes emit ordered trace
events, that a corrected seed-3 `wrong_port` fixture can pass all 10 grader checks from an isolated
workspace, and that the same final state fails when its trace records the wrong repair order.

## Validation

From the TeamBench repository root:

```bash
python -m pytest \
  tests/test_task_infrastructure.py \
  tests/test_contamination.py::test_cr4_reset_fixture_clears_only_generated_store \
  tests/test_contamination.py::test_dist1_grader_bootstraps_pip_before_installing_timeout_plugin \
  -q
bash -n \
  tasks/CROSS1_api_contract/grade.sh \
  tasks/INC1_cascade_failure/grade.sh \
  tasks/DIST1_queue_race/grade.sh
uv lock --check
```

Additional manual smoke coverage performed before the CROSS1/INC1 fixes:

- staged CROSS1 seeds 0–2 and INC1 seeds 0–4;
- parsed every generated Python file;
- collected all nine CROSS1 pytest tests after installing its declared Python dependencies;
- reproduced CROSS1's missing-Go errors and silent dependency behavior; and
- reproduced INC1's isolated seed-3 import failure and comment-driven false positives.

## Review considerations

- CROSS1 performs task-local package installation only when its Python preflight fails. The role
  images bake in those dependencies, avoiding network installation during normal container runs.
- The grader diagnostics contain tool output only. No environment dump, authorization header, API
  key, certificate, or other credential is persisted.
- The workspace edit trace is evaluation evidence under TeamBench's existing cooperative-agent
  threat model, not a tamper-resistant audit log. Hardening it against a deliberately adversarial
  shell process would require stronger process/filesystem isolation than this task-level patch.
- Task identifiers and seed-specific expected data are authored benchmark inputs. This change does
  not broaden shell execution to user-provided commands.
- The images continue to run agents as non-root and retain `network_mode: none` at runtime. Adding
  Go expands the image toolchain but does not add privileges or expose services.
- Base-image digest pinning and OS/Python package version pinning are broader supply-chain concerns
  already present in the current Dockerfiles; they are not changed by this focused patch.
