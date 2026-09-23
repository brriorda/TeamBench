"""
Parameterized generator for INC1: Cascading Service Failure.

Each seed produces:
  - Different service names (gateway + two backend services)
  - Different bug type in the root-cause service (bad_timeout, bad_connection_string,
    missing_retry, wrong_port, disabled_healthcheck)
  - Different dependency topology (linear A->B->C or fan A->B+C)
  - Different port numbers
  - Seed-specific expected.json, spec.md, brief.md, and workspace files

TNI driver: The spec tells the Planner the dependency graph, the root cause in
service A, the required fix order (must stabilise C before B before A to prevent
data corruption), and the expected health responses.  The brief gives the Executor
only "services are failing, fix them so all health checks return {status:ok}."
Without the Planner's analysis the Executor may fix in the wrong order or miss
the real root cause.

The grader checks:
  1. All three service files import cleanly
  2. Each service's health_check() returns {"status":"ok","service":<name>}
  3. Root-cause bug in service A is fixed (source inspection + config check)
  4. Service B has retry / circuit-breaker guard (source inspection)
  5. Service C has partial-write guard (source inspection)
  6. Workspace edit trace records the required C -> B -> A/root repair order
  7. Total file size not excessive (< 250 lines across all .py files)
  8. attestation.json exists with verdict=pass
"""
from __future__ import annotations

import json

from generators.base import TaskGenerator, GeneratedTask
from generators.primitives import SeededRandom

# ---------------------------------------------------------------------------
# Pools
# ---------------------------------------------------------------------------

# (svc_a, svc_b, svc_c)
SERVICE_TRIPLETS = [
    ("api_gateway", "user_service", "order_service"),
    ("api_gateway", "auth_service", "payment_service"),
    ("api_gateway", "search_service", "inventory_service"),
    ("frontend_proxy", "session_service", "billing_service"),
    ("load_balancer", "account_service", "ledger_service"),
    ("edge_router", "catalog_service", "fulfillment_service"),
    ("ingress_proxy", "profile_service", "notification_service"),
    ("api_gateway", "recommendation_service", "shipping_service"),
    ("web_gateway", "analytics_service", "reporting_service"),
    ("reverse_proxy", "identity_service", "audit_service"),
]

# (port_a, port_b, port_c)
PORT_TRIPLETS = [
    (8080, 8081, 8082),
    (9000, 9001, 9002),
    (7000, 7001, 7002),
    (5000, 5001, 5002),
    (3000, 3001, 3002),
    (8880, 8881, 8882),
    (9900, 9901, 9902),
    (6060, 6061, 6062),
    (4040, 4041, 4042),
    (8100, 8101, 8102),
]

# (bug_id, description, fix_hint)
BUG_TYPES = [
    (
        "bad_timeout",
        "connection timeout set to 0 ms (immediate timeout)",
        "set upstream_ms in config.json to a positive value (e.g. 5000)",
    ),
    (
        "bad_connection_string",
        "upstream host hard-coded to 'localhost' instead of the correct backend hostname",
        "correct the host field in config.json to '127.0.0.1'",
    ),
    (
        "missing_retry",
        "no retry logic on upstream call — first transient failure crashes the gateway",
        "add a retry loop (at least 3 attempts) around the upstream HTTP call in _call_upstream()",
    ),
    (
        "wrong_port",
        "gateway configured to forward to wrong port (off-by-one in config)",
        "correct the port field in config.json for the backend service",
    ),
    (
        "disabled_healthcheck",
        "health check route returns error unconditionally due to inverted status flag",
        "fix the inverted condition in health_check() so it returns status='ok' when running",
    ),
]

TOPOLOGIES = ["linear", "fan"]


class Generator(TaskGenerator):
    task_id = "INC1_cascade_failure"
    domain = "incident"
    difficulty = "hard"
    languages = ["python"]

    def generate(self, seed: int) -> GeneratedTask:
        rng = SeededRandom(seed)  # kept for future use; index selection below

        # Deterministic index selection with different strides so seeds 0,1,2
        # produce genuinely different combinations across all pools.
        svc_a, svc_b, svc_c = SERVICE_TRIPLETS[seed % len(SERVICE_TRIPLETS)]
        port_a, port_b, port_c = PORT_TRIPLETS[(seed * 3 + 1) % len(PORT_TRIPLETS)]
        bug_id, bug_desc, fix_hint = BUG_TYPES[(seed * 7 + 2) % len(BUG_TYPES)]
        topology = TOPOLOGIES[(seed + 1) % len(TOPOLOGIES)]

        fix_order = [svc_c, svc_b, svc_a]

        expected = {
            "svc_a": svc_a,
            "svc_b": svc_b,
            "svc_c": svc_c,
            "port_a": port_a,
            "port_b": port_b,
            "port_c": port_c,
            "root_cause_service": svc_a,
            "root_cause_bug": bug_id,
            "fix_order": fix_order,
            "trace_workspace_edits": True,
            "topology": topology,
            "expected_health_body": {"status": "ok"},
            "fix_hint": fix_hint,
        }

        workspace_files = self._build_workspace(
            svc_a, svc_b, svc_c,
            port_a, port_b, port_c,
            bug_id, topology,
        )

        spec_md = self._generate_spec(
            svc_a, svc_b, svc_c,
            port_a, port_b, port_c,
            bug_id, bug_desc, fix_hint,
            fix_order, topology,
        )
        brief_md = self._generate_brief(svc_a, svc_b, svc_c)

        return GeneratedTask(
            task_id=self.task_id,
            seed=seed,
            spec_md=spec_md,
            brief_md=brief_md,
            expected=expected,
            workspace_files=workspace_files,
        )

    # ------------------------------------------------------------------
    def _build_workspace(
        self,
        svc_a: str, svc_b: str, svc_c: str,
        port_a: int, port_b: int, port_c: int,
        bug_id: str,
        topology: str,
    ) -> dict[str, str]:
        return {
            "config.json": _config_json(svc_a, svc_b, svc_c, port_a, port_b, port_c, bug_id),
            f"{svc_a}.py": _svc_a(svc_a, svc_b, svc_c, port_b, bug_id, topology),
            f"{svc_b}.py": _svc_b(svc_b, svc_c),
            f"{svc_c}.py": _svc_c(svc_c),
            "failure.log": _failure_log(svc_a, svc_b, svc_c, port_a, port_b, port_c, bug_id),
        }

    # ------------------------------------------------------------------
    def _generate_spec(
        self,
        svc_a: str, svc_b: str, svc_c: str,
        port_a: int, port_b: int, port_c: int,
        bug_id: str, bug_desc: str, fix_hint: str,
        fix_order: list, topology: str,
    ) -> str:
        if topology == "linear":
            dep_graph = f"{svc_a} -> {svc_b} -> {svc_c}"
            dep_explanation = (
                f"`{svc_a}` (port {port_a}) is the entry-point. It calls `{svc_b}` "
                f"(port {port_b}), which calls `{svc_c}` (port {port_c})."
            )
        else:
            dep_graph = f"{svc_a} -> {svc_b} + {svc_c}"
            dep_explanation = (
                f"`{svc_a}` (port {port_a}) calls both `{svc_b}` (port {port_b}) and "
                f"`{svc_c}` (port {port_c}). `{svc_b}` also calls `{svc_c}` for persistence."
            )

        return f"""# INC1: Cascading Service Failure

## Incident Summary

**Incident ID**: INC-2024-0615-001
**Severity**: P1
**Status**: Active — all three services degraded

Three services are failing in a cascade. Review `failure.log` for the timeline.

---

## Service Dependency Graph

```
{dep_graph}
```

{dep_explanation}

---

## Root Cause Analysis

**Root-cause service**: `{svc_a}` (port {port_a})
**Bug**: {bug_desc}

This bug causes every call from `{svc_a}` to `{svc_b}` to fail. When `{svc_b}`
receives a failed/empty response it tries to persist anyway via `{svc_c}`, flooding
`{svc_c}` with malformed requests. `{svc_c}` then writes partial records because it
has no atomic-write guard. Once `{svc_c}`'s store is partially corrupt, `{svc_b}`'s
`process()` call raises an unhandled exception, and `{svc_a}` marks itself unhealthy.

---

## Required Fix Order

**CRITICAL**: Fixes MUST be applied in this exact order to prevent data corruption:

1. **Fix `{svc_c}` first** — add an atomic write guard so partial records cannot be committed.
2. **Fix `{svc_b}` second** — add retry/circuit-breaker around the `{svc_c}` call so transient errors do not crash the handler.
3. **Fix `{svc_a}` last** — {fix_hint}.

Applying fixes out of order (e.g. fixing `{svc_a}` first) will cause `{svc_a}` to
resume sending requests before `{svc_c}` is hardened, leading to additional
partial-record corruption in the store.

---

## Expected Post-Fix State

After all fixes, each service's `health_check()` must return:

```json
{{"status": "ok", "service": "<service_name>"}}
```

- `{svc_a}.health_check()` → `{{"status": "ok", "service": "{svc_a}"}}`
- `{svc_b}.health_check()` → `{{"status": "ok", "service": "{svc_b}"}}`
- `{svc_c}.health_check()` → `{{"status": "ok", "service": "{svc_c}"}}`

---

## Fix Specifications

### `{svc_c}.py` — atomic write guard
`store()` must build the full record dict before appending to `_STORE`.
Raise `ValueError` if any required field is missing.

### `{svc_b}.py` — retry / circuit-breaker
`process()` must retry the `{svc_c}` call at least 3 times with backoff before raising.

### `{svc_a}.py` / `config.json` — root-cause fix
{fix_hint}.

---

## Constraints

- Change no more than **50 lines** across all files combined.
- Do not add new service files.
- `config.json` may be edited to correct configuration values.
- Verifier must produce `attestation.json` with `verdict="pass"`.
"""

    def _generate_brief(self, svc_a: str, svc_b: str, svc_c: str) -> str:
        return f"""# INC1: Cascading Service Failure (Brief)

Three Python services are failing in a cascade:
- `{svc_a}.py`
- `{svc_b}.py`
- `{svc_c}.py`

Review `failure.log` for the error timeline and `config.json` for service configuration.

**Goal**: Fix all three services so each `health_check()` function returns
`{{"status": "ok", "service": "<name>"}}`. Also fix any bugs causing data corruption
or unhandled exceptions in `process()` and `store()`.

The Planner has a full incident report with the root cause, dependency graph,
and required fix order. Coordinate with the Planner before making changes.

Keep your diff small — change only what is necessary.
"""


# ---------------------------------------------------------------------------
# Module-level code-generation helpers (not methods) so that triple-quoted
# strings start at column 0 and contain no unintended leading whitespace.
# ---------------------------------------------------------------------------

def _config_json(
    svc_a: str, svc_b: str, svc_c: str,
    port_a: int, port_b: int, port_c: int,
    bug_id: str,
) -> str:
    upstream_timeout = 0 if bug_id == "bad_timeout" else 5000
    upstream_port_b = (port_b + 1) if bug_id == "wrong_port" else port_b
    upstream_host = "localhost" if bug_id == "bad_connection_string" else "127.0.0.1"

    obj = {
        "services": {
            svc_a: {"host": "127.0.0.1", "port": port_a},
            svc_b: {"host": upstream_host, "port": upstream_port_b},
            svc_c: {"host": "127.0.0.1", "port": port_c},
        },
        "timeouts": {
            "upstream_ms": upstream_timeout,
            "health_check_ms": 2000,
        },
        "retry": {
            "max_attempts": 1,
            "backoff_ms": 100,
        },
    }
    return json.dumps(obj, indent=2) + "\n"


def _svc_a(
    svc_a: str, svc_b: str, svc_c: str,
    port_b: int,
    bug_id: str,
    topology: str,
) -> str:
    svc_label = svc_a.upper().replace("_", " ")

    if bug_id == "bad_timeout":
        call_upstream = f'''\
def _call_upstream(host, port, path, timeout_ms):
    """Call an upstream service. BUG: timeout_ms=0 causes immediate failure."""
    import urllib.request
    # BUG: timeout of 0 means instant timeout — no upstream call succeeds
    timeout_sec = timeout_ms / 1000.0   # timeout_ms is 0 from config
    url = f"http://{{host}}:{{port}}{{path}}"
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
        return resp.read().decode("utf-8")
'''
    elif bug_id == "bad_connection_string":
        call_upstream = f'''\
def _call_upstream(host, port, path, timeout_ms):
    """Call an upstream service. BUG: host from config may be 'localhost'."""
    import urllib.request
    timeout_sec = timeout_ms / 1000.0
    # BUG: config sets host='localhost' which does not resolve correctly here
    url = f"http://{{host}}:{{port}}{{path}}"
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
        return resp.read().decode("utf-8")
'''
    elif bug_id == "missing_retry":
        call_upstream = f'''\
def _call_upstream(host, port, path, timeout_ms):
    """Call an upstream service. BUG: no retry — first failure raises."""
    import urllib.request
    timeout_sec = timeout_ms / 1000.0
    url = f"http://{{host}}:{{port}}{{path}}"
    req = urllib.request.Request(url)
    # BUG: single attempt only — should retry at least 3 times on failure
    with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
        return resp.read().decode("utf-8")
'''
    elif bug_id == "wrong_port":
        call_upstream = f'''\
def _call_upstream(host, port, path, timeout_ms):
    """Call an upstream service. BUG: port from config is off-by-one."""
    import urllib.request
    timeout_sec = timeout_ms / 1000.0
    # BUG: config.services.{svc_b}.port is {port_b + 1} (should be {port_b})
    url = f"http://{{host}}:{{port}}{{path}}"
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
        return resp.read().decode("utf-8")
'''
    else:  # disabled_healthcheck
        call_upstream = f'''\
def _call_upstream(host, port, path, timeout_ms):
    """Call an upstream service."""
    import urllib.request
    timeout_sec = timeout_ms / 1000.0
    url = f"http://{{host}}:{{port}}{{path}}"
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
        return resp.read().decode("utf-8")
'''

    if bug_id == "disabled_healthcheck":
        health_fn = '''\
def health_check():
    """Return health status. BUG: _service_ok flag is inverted."""
    _service_ok = True
    # BUG: inverted check — returns error when service is actually fine
    if _service_ok:
        return {"status": "error", "service": SERVICE_NAME, "detail": "flag inverted"}
    return {"status": "ok", "service": SERVICE_NAME}
'''
    else:
        health_fn = '''\
def health_check():
    """Return health status of this service."""
    return {"status": "ok", "service": SERVICE_NAME}
'''

    if topology == "linear":
        route_fn = f'''\
def handle_request(path):
    """Route an incoming request through the service chain."""
    cfg = load_config()
    b_host = cfg["services"]["{svc_b}"]["host"]
    b_port = cfg["services"]["{svc_b}"]["port"]
    timeout_ms = cfg["timeouts"]["upstream_ms"]
    try:
        result = _call_upstream(b_host, b_port, path, timeout_ms)
        return {{"status": "ok", "data": result, "routed_via": SERVICE_NAME}}
    except Exception as exc:
        return {{"status": "error", "detail": str(exc), "service": SERVICE_NAME}}
'''
    else:  # fan
        route_fn = f'''\
def handle_request(path):
    """Route an incoming request to both downstream services."""
    cfg = load_config()
    b_host = cfg["services"]["{svc_b}"]["host"]
    b_port = cfg["services"]["{svc_b}"]["port"]
    c_host = cfg["services"]["{svc_c}"]["host"]
    c_port = cfg["services"]["{svc_c}"]["port"]
    timeout_ms = cfg["timeouts"]["upstream_ms"]
    results = {{}}
    for name, host, port in [("{svc_b}", b_host, b_port), ("{svc_c}", c_host, c_port)]:
        try:
            results[name] = _call_upstream(host, port, path, timeout_ms)
        except Exception as exc:
            results[name] = {{"error": str(exc)}}
    return {{"status": "ok", "data": results, "routed_via": SERVICE_NAME}}
'''

    return f'''\
"""
{svc_label} — entry-point service that routes to downstream services.

Dependency chain ({topology} topology):
  {svc_a} -> {svc_b} -> {svc_c}

BUG: {bug_id} causes all downstream calls to fail.
"""
import json
import os

SERVICE_NAME = "{svc_a}"
CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")


def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


{call_upstream}

{health_fn}

{route_fn}

if __name__ == "__main__":
    print(health_check())
'''


def _svc_b(svc_b: str, svc_c: str) -> str:
    svc_label = svc_b.upper().replace("_", " ")
    return f'''\
"""
{svc_label} — middle-tier service.

Depends on {svc_c} for persistent storage.
BUG: no retry or circuit-breaker guard around the {svc_c} call.
When {svc_c} is overwhelmed by partial writes it rejects connections,
and this service propagates the exception uncaught, crashing the handler.
"""
import json
import os

SERVICE_NAME = "{svc_b}"
CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")


def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def health_check():
    """Return health status of this service."""
    return {{"status": "ok", "service": SERVICE_NAME}}


def process(payload):
    """Process payload and persist via {svc_c}.
    BUG: no retry — if {svc_c} rejects the connection, exception propagates uncaught.
    """
    import urllib.request
    cfg = load_config()
    c_host = cfg["services"]["{svc_c}"]["host"]
    c_port = cfg["services"]["{svc_c}"]["port"]
    timeout_ms = cfg["timeouts"]["upstream_ms"]
    timeout_sec = max(0.1, timeout_ms / 1000.0)
    url = f"http://{{c_host}}:{{c_port}}/store"
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data,
                                 headers={{"Content-Type": "application/json"}})
    # BUG: single attempt only, no circuit-breaker, no fallback
    with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
        return json.loads(resp.read().decode("utf-8"))


if __name__ == "__main__":
    print(health_check())
'''


def _svc_c(svc_c: str) -> str:
    svc_label = svc_c.upper().replace("_", " ")
    return f'''\
"""
{svc_label} — data-store / persistence service.

BUG: store() writes fields one at a time without a transaction guard.
If interrupted mid-write (common during cascade overload), the record
is left in a partial state, corrupting the dataset.
"""
import os

SERVICE_NAME = "{svc_c}"
CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")

_STORE: list = []   # in-memory store (testable without network)


def health_check():
    """Return health status of this service."""
    return {{"status": "ok", "service": SERVICE_NAME}}


def store(record: dict) -> dict:
    """Persist a record.
    BUG: writes fields individually — if an exception occurs mid-write
    the record is partially committed (no atomic write / rollback).
    """
    entry = {{}}
    # BUG: no atomic write — partial record can be committed on error
    entry["id"] = record.get("id")           # written first
    entry["payload"] = record.get("payload") # written second
    entry["checksum"] = record.get("checksum") # may never be written
    _STORE.append(entry)   # appended even if checksum is missing
    return {{"status": "stored", "id": entry["id"]}}


def get_all() -> list:
    """Return all stored records."""
    return list(_STORE)


if __name__ == "__main__":
    print(health_check())
'''


def _failure_log(
    svc_a: str, svc_b: str, svc_c: str,
    port_a: int, port_b: int, port_c: int,
    bug_id: str,
) -> str:
    if bug_id == "bad_timeout":
        root_error = (
            f"[{svc_a}] WARN  timeout=0ms — upstream call to "
            f"{svc_b}:{port_b} timed out immediately"
        )
    elif bug_id == "bad_connection_string":
        root_error = (
            f"[{svc_a}] ERROR connection refused: host='localhost' unreachable "
            f"(expected 127.0.0.1:{port_b})"
        )
    elif bug_id == "missing_retry":
        root_error = (
            f"[{svc_a}] ERROR upstream {svc_b}:{port_b} returned transient 503, "
            f"no retry configured"
        )
    elif bug_id == "wrong_port":
        root_error = (
            f"[{svc_a}] ERROR connection refused: {svc_b} not listening on port "
            f"{port_b + 1} (correct port: {port_b})"
        )
    else:  # disabled_healthcheck
        root_error = (
            f"[{svc_a}] ERROR health_check() returning status='error' — "
            f"_service_ok flag is inverted"
        )

    return (
        f"2024-06-15T03:12:00Z  INFO  [{svc_a}] Service started on 127.0.0.1:{port_a}\n"
        f"2024-06-15T03:12:01Z  INFO  [{svc_b}] Service started on 127.0.0.1:{port_b}\n"
        f"2024-06-15T03:12:01Z  INFO  [{svc_c}] Service started on 127.0.0.1:{port_c}\n"
        f"2024-06-15T03:15:44Z  INFO  [{svc_a}] Received request GET /api/v1/data\n"
        f"2024-06-15T03:15:44Z  {root_error}\n"
        f"2024-06-15T03:15:44Z  ERROR [{svc_b}] Request from {svc_a} failed — "
        f"attempting {svc_c} call anyway\n"
        f"2024-06-15T03:15:44Z  ERROR [{svc_b}] Unhandled exception in process(): "
        f"upstream {svc_c}:{port_c} rejected connection\n"
        f"2024-06-15T03:15:44Z  WARN  [{svc_c}] Connection flood detected — "
        f"store() interrupted mid-write, partial record committed id=None\n"
        f"2024-06-15T03:15:45Z  ERROR [{svc_a}] Cascade failure — "
        f"all downstream services degraded\n"
        f"2024-06-15T03:15:45Z  ERROR [{svc_a}] health_check returning error — "
        f"marking service unhealthy\n"
        f"2024-06-15T03:15:46Z  ALERT on-call paged: cascade failure across "
        f"{svc_a}, {svc_b}, {svc_c}\n"
        f"2024-06-15T03:15:47Z  INFO  Incident INC-2024-0615-001 opened. Severity: P1\n"
    )
