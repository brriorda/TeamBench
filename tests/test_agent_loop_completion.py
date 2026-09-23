"""Tests for AgentLoop's backward-compatible structured completion API.

Run with:
    uv run pytest tests/test_agent_loop_completion.py -q
"""
from __future__ import annotations

from pathlib import Path

from harness.agent_interface import AdapterResponse, RoleConfig, Tool, ToolResult
from harness.agent_loop import AgentLoop, CompletionContext, TerminationReason


class ScriptedAdapter:
    """Return deterministic adapter responses in order."""

    def __init__(self, responses: list[AdapterResponse]) -> None:
        """Store a private response queue."""
        self.responses = list(responses)

    def generate_with_tools(
        self,
        messages: list[dict],
        system_prompt: str,
        tools: list[dict],
    ) -> AdapterResponse:
        """Return the next fixture response."""
        return self.responses.pop(0)

    def get_usage(self) -> dict:
        """Return empty deterministic usage."""
        return {}


class FinishTool(Tool):
    """Successful terminal-tool fixture."""

    name = "finish_turn"

    def execute(self, **kwargs: object) -> ToolResult:
        """Acknowledge completion."""
        return ToolResult(stdout="finished")


def _loop(
    tmp_path: Path,
    responses: list[AdapterResponse],
    **kwargs: object,
) -> AgentLoop:
    """Construct one isolated loop fixture."""
    return AgentLoop(
        role_config=RoleConfig(role="planner", system_prompt="plan", tools=[FinishTool()]),
        adapter=ScriptedAdapter(responses),
        messages_dir=str(tmp_path / "messages"),
        log_dir=str(tmp_path / "logs"),
        max_turns=int(kwargs.pop("max_turns", 2)),
        **kwargs,
    )


def test_legacy_run_keeps_list_contract_and_max_turn_behavior(tmp_path: Path) -> None:
    """Old callers still receive unfinished turns when the cap is reached."""
    loop = _loop(
        tmp_path,
        [AdapterResponse(tool_calls=[]), AdapterResponse(tool_calls=[])],
    )
    turns = loop.run("start")
    assert isinstance(turns, list)
    assert len(turns) == 2
    assert turns[-1].done is False


def test_adapter_done_is_a_structured_model_stop(tmp_path: Path) -> None:
    """AdapterResponse.done terminates without relying on a text marker."""
    result = _loop(tmp_path, [AdapterResponse(done=True)]).run_with_result("start")
    assert result.termination_reason is TerminationReason.MODEL_DONE
    assert result.natural is True
    assert result.turns[-1].done is True


def test_optional_nonempty_no_tool_response_is_final(tmp_path: Path) -> None:
    """Callers may opt into standard final-response completion."""
    result = _loop(
        tmp_path,
        [AdapterResponse(text="Plan delivered.")],
        complete_on_no_tool_final=True,
    ).run_with_result("start")
    assert result.termination_reason is TerminationReason.NO_TOOL_FINAL


def test_successful_declared_terminal_tool_stops_after_logging(tmp_path: Path) -> None:
    """A caller-declared terminal tool produces a logged completed turn."""
    result = _loop(
        tmp_path,
        [AdapterResponse(tool_calls=[{"name": "finish_turn", "args": {}}])],
        terminal_tools={"finish_turn"},
    ).run_with_result("start")
    assert result.termination_reason is TerminationReason.TERMINAL_TOOL
    assert result.turns[-1].done is True
    assert (tmp_path / "logs/turn_000.json").read_text(encoding="utf-8").find(
        '"done": true'
    ) != -1


def test_completion_policy_receives_executed_turn_evidence(tmp_path: Path) -> None:
    """A caller callback runs after tools and may select a structured reason."""
    observed: list[CompletionContext] = []

    def complete(context: CompletionContext) -> TerminationReason:
        """Capture the callback input and end this fixture invocation."""
        observed.append(context)
        return TerminationReason.TERMINAL_TOOL

    result = _loop(
        tmp_path,
        [AdapterResponse(tool_calls=[{"name": "finish_turn", "args": {}}])],
        completion_policy=complete,
    ).run_with_result("start")
    assert result.termination_reason is TerminationReason.TERMINAL_TOOL
    assert observed[0].role == "planner"
    assert observed[0].tool_results[0]["exit_code"] == 0
