"""Regression tests for task generators, graders, and role-image toolchains.

Purpose:
    Exercise the focused infrastructure fixes for CR4, DIST1, CROSS1, and INC1 without invoking
    an agent model or requiring the intentionally broken starter workspaces to solve themselves.

Run:
    python -m pytest tests/test_task_infrastructure.py -v
"""
from __future__ import annotations

import importlib
import json
import os
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

Cross1Generator = importlib.import_module("generators.gen_cross1_api_contract").Generator
Inc1Generator = importlib.import_module("generators.gen_inc1_cascade_failure").Generator
agent_interface = importlib.import_module("harness.agent_interface")
RunCommandTool = agent_interface.RunCommandTool
WriteFileTool = agent_interface.WriteFileTool


def _stage_generated_task(generator: Any, seed: int, run_dir: Path) -> None:
    """Materialize one generated task instance under a pytest temporary directory."""
    generated = generator.generate(seed=seed)
    generator.write_to_disk(
        generated,
        str(run_dir / "workspace"),
        str(run_dir / "reports"),
    )
    submission = run_dir / "submission"
    submission.mkdir(parents=True)
    (submission / "attestation.json").write_text(
        json.dumps({"verdict": "pass"}) + "\n",
        encoding="utf-8",
    )


def _run_inc1_grader(run_dir: Path) -> dict[str, Any]:
    """Run INC1's grader and return its parsed score artifact."""
    result = subprocess.run(
        [
            "/bin/bash",
            str(ROOT / "tasks/INC1_cascade_failure/grade.sh"),
            str(run_dir / "workspace"),
            str(run_dir / "reports"),
            str(run_dir / "submission"),
            str(ROOT / "tasks/INC1_cascade_failure"),
            str(run_dir / "reports/expected.json"),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    return json.loads((run_dir / "reports/score.json").read_text(encoding="utf-8"))


def test_cross1_missing_go_fails_setup_with_retained_diagnostics(tmp_path: Path) -> None:
    """A missing Go compiler must be an explicit infrastructure failure, not a candidate check."""
    run_dir = tmp_path / "cross1"
    _stage_generated_task(Cross1Generator(), seed=0, run_dir=run_dir)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    python_wrapper = bin_dir / "python3"
    python_wrapper.write_text(
        f"#!/bin/sh\nexec {shlex.quote(sys.executable)} \"$@\"\n",
        encoding="utf-8",
    )
    python_wrapper.chmod(0o755)
    environment = os.environ.copy()
    environment["PATH"] = f"{bin_dir}:/usr/bin:/bin"

    result = subprocess.run(
        [
            "/bin/bash",
            str(ROOT / "tasks/CROSS1_api_contract/grade.sh"),
            str(run_dir / "workspace"),
            str(run_dir / "reports"),
            str(run_dir / "submission"),
            str(ROOT / "tasks/CROSS1_api_contract"),
            str(run_dir / "reports/expected.json"),
        ],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )

    score_path = run_dir / "reports/score.json"
    assert score_path.is_file(), result.stdout + result.stderr
    score = json.loads(score_path.read_text(encoding="utf-8"))
    assert result.returncode != 0
    assert score["failure_modes"] == ["go_toolchain_missing"]
    assert "Go compiler not found on PATH" in score["grader_stderr"]


def test_cross1_declares_toolchain_and_has_no_silent_dependency_fallback() -> None:
    """CROSS1 must declare Go and provision both language toolchains in role images."""
    grader = (ROOT / "tasks/CROSS1_api_contract/grade.sh").read_text(encoding="utf-8")
    task_yaml = (ROOT / "tasks/CROSS1_api_contract/task.yaml").read_text(encoding="utf-8")
    executor = (ROOT / "images/executor/Dockerfile").read_text(encoding="utf-8")
    verifier = (ROOT / "images/verifier/Dockerfile").read_text(encoding="utf-8")

    assert "set -euo pipefail" in grader
    assert "python3 -m ensurepip --upgrade" in grader
    assert "python3 -m pip install --quiet pytest requests" in grader
    assert "command -v go" in grader
    assert "|| true" not in grader
    assert "from client.models import User" not in grader
    assert "languages: [python, go]" in task_yaml
    assert [Cross1Generator().generate(seed).expected["entity"] for seed in range(3)] == [
        "User",
        "Product",
        "Order",
    ]
    for dockerfile in (executor, verifier):
        assert "golang-go" in dockerfile
        assert "pytest" in dockerfile
        assert "requests" in dockerfile


def test_cross1_candidate_failures_produce_diagnostics_and_failure_modes(
    tmp_path: Path,
) -> None:
    """Once setup passes, failed checks must remain explicit in the native score artifact."""
    run_dir = tmp_path / "cross1"
    _stage_generated_task(Cross1Generator(), seed=0, run_dir=run_dir)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    python_wrapper = bin_dir / "python3"
    python_wrapper.write_text(
        f"#!/bin/sh\nexec {shlex.quote(sys.executable)} \"$@\"\n",
        encoding="utf-8",
    )
    python_wrapper.chmod(0o755)
    go_wrapper = bin_dir / "go"
    go_wrapper.write_text(
        "#!/bin/sh\n"
        "if [ \"${1:-}\" = version ]; then echo 'go version go1.22 test'; exit 0; fi\n"
        "if [ \"${1:-}\" = build ]; then exit 0; fi\n"
        "echo 'fake Go runtime unavailable' >&2\n"
        "exit 1\n",
        encoding="utf-8",
    )
    go_wrapper.chmod(0o755)
    environment = os.environ.copy()
    environment["PATH"] = f"{bin_dir}:/usr/bin:/bin"

    result = subprocess.run(
        [
            "/bin/bash",
            str(ROOT / "tasks/CROSS1_api_contract/grade.sh"),
            str(run_dir / "workspace"),
            str(run_dir / "reports"),
            str(run_dir / "submission"),
            str(ROOT / "tasks/CROSS1_api_contract"),
            str(run_dir / "reports/expected.json"),
        ],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )

    assert result.returncode == 0, result.stderr
    score = json.loads((run_dir / "reports/score.json").read_text(encoding="utf-8"))
    assert score["pass"] is False
    assert "C3" in score["failure_modes"]
    assert score["grader_stderr"]


def test_inc1_starter_comments_do_not_satisfy_executable_safeguards(tmp_path: Path) -> None:
    """Retry and atomicity words in starter comments must not pass behavioral checks."""
    run_dir = tmp_path / "inc1-seed0"
    _stage_generated_task(Inc1Generator(), seed=0, run_dir=run_dir)

    score = _run_inc1_grader(run_dir)

    assert "root_cause_not_fixed" in score["failure_modes"]
    assert "svc_b_no_retry" in score["failure_modes"]
    assert "svc_c_no_atomic_guard" in score["failure_modes"]
    assert "wrong_fix_order" in score["failure_modes"]


def test_workspace_tools_record_ordered_content_changes(tmp_path: Path) -> None:
    """Shared write and run tools must emit framework-independent workspace edit events."""
    workspace = tmp_path / "run/workspace"
    workspace.mkdir(parents=True)
    reports = tmp_path / "run/reports"
    reports.mkdir()
    (reports / "expected.json").write_text(
        json.dumps({"trace_workspace_edits": True}) + "\n",
        encoding="utf-8",
    )
    (workspace / "c.py").write_text("before\n", encoding="utf-8")
    (workspace / "b.py").write_text("before\n", encoding="utf-8")
    write_tool = WriteFileTool(allowed_roots=[str(workspace)])
    run_tool = RunCommandTool(cwd=str(workspace))

    write_result = write_tool.execute(path="c.py", content="after\n")
    script = "from pathlib import Path; Path('b.py').write_text('after\\n', encoding='utf-8')"
    run_result = run_tool.execute(cmd=f"{shlex.quote(sys.executable)} -c {shlex.quote(script)}")

    assert write_result.exit_code == 0
    assert run_result.exit_code == 0
    trace_path = tmp_path / "run/logs/workspace_edit_trace.jsonl"
    events = [json.loads(line) for line in trace_path.read_text(encoding="utf-8").splitlines()]
    assert events == [
        {"schema_version": 1, "tool": "write", "paths": ["c.py"]},
        {"schema_version": 1, "tool": "run", "paths": ["b.py"]},
    ]


def test_inc1_wrong_port_seed_uses_expected_json_without_generator_import(
    tmp_path: Path,
) -> None:
    """A corrected wrong-port variant must pass from an isolated staged workspace."""
    run_dir = tmp_path / "inc1-seed3"
    _stage_generated_task(Inc1Generator(), seed=3, run_dir=run_dir)
    expected = json.loads((run_dir / "reports/expected.json").read_text(encoding="utf-8"))
    workspace = run_dir / "workspace"
    write_tool = WriteFileTool(allowed_roots=[str(workspace)])
    svc_c_source = "\n".join(
        [
            f'SERVICE_NAME = "{expected["svc_c"]}"',
            "_STORE = []",
            "def health_check():",
            "    return {'status': 'ok', 'service': SERVICE_NAME}",
            "def store(record):",
            "    entry = {key: record[key] for key in ('id', 'payload', 'checksum')}",
            "    _STORE.append(entry)",
            "    return {'status': 'stored', 'id': entry['id']}",
            "def get_all():",
            "    return list(_STORE)",
            "",
        ]
    )
    svc_b_source = "\n".join(
        [
            f'SERVICE_NAME = "{expected["svc_b"]}"',
            "def health_check():",
            "    return {'status': 'ok', 'service': SERVICE_NAME}",
            "def process(payload):",
            "    for attempt in range(3):",
            "        return payload",
            "    raise RuntimeError('retry budget exhausted')",
            "",
        ]
    )

    assert write_tool.execute(path=f"{expected['svc_c']}.py", content=svc_c_source).exit_code == 0
    assert write_tool.execute(path=f"{expected['svc_b']}.py", content=svc_b_source).exit_code == 0
    config_path = run_dir / "workspace/config.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    config["services"][expected["svc_b"]]["port"] = expected["port_b"]
    assert write_tool.execute(
        path="config.json",
        content=json.dumps(config, indent=2) + "\n",
    ).exit_code == 0

    score = _run_inc1_grader(run_dir)

    assert score["pass"] is True
    assert score["secondary"]["checks_passed"] == 10
    assert score["failure_modes"] == []

    trace_path = run_dir / "logs/workspace_edit_trace.jsonl"
    wrong_order = [
        {"schema_version": 1, "tool": "write", "paths": ["config.json"]},
        {"schema_version": 1, "tool": "write", "paths": [f"{expected['svc_b']}.py"]},
        {"schema_version": 1, "tool": "write", "paths": [f"{expected['svc_c']}.py"]},
    ]
    trace_path.write_text(
        "".join(json.dumps(event) + "\n" for event in wrong_order),
        encoding="utf-8",
    )
    wrong_order_score = _run_inc1_grader(run_dir)
    assert "wrong_fix_order" in wrong_order_score["failure_modes"]
