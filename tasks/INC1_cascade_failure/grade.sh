#!/usr/bin/env bash
set -o pipefail
WORKSPACE="$1"
REPORTS="$2"
SUBMISSION="$3"
TASK_DIR="$4"

mkdir -p "$REPORTS"

CHECKS=0; PASSED=0; FAILURES=""
check() {
  CHECKS=$((CHECKS + 1))
  if eval "$1" 2>/dev/null; then
    PASSED=$((PASSED + 1))
  else
    FAILURES="${FAILURES:+${FAILURES},}$2"
  fi
}

# Load seed-specific expected values
EXPECTED_JSON="$REPORTS/expected.json"
if [ -f "$EXPECTED_JSON" ]; then
  SVC_A=$(python3 -c "import json; d=json.load(open('$EXPECTED_JSON')); print(d['svc_a'])")
  SVC_B=$(python3 -c "import json; d=json.load(open('$EXPECTED_JSON')); print(d['svc_b'])")
  SVC_C=$(python3 -c "import json; d=json.load(open('$EXPECTED_JSON')); print(d['svc_c'])")
  BUG_ID=$(python3 -c "import json; d=json.load(open('$EXPECTED_JSON')); print(d['root_cause_bug'])")
else
  SVC_A="api_gateway"
  SVC_B="user_service"
  SVC_C="order_service"
  BUG_ID="bad_timeout"
fi

cd "$WORKSPACE"

# ── 1. All service files import cleanly ──────────────────────────────────────
check "python3 -c \"
import importlib.util, sys, os
for svc in ['${SVC_A}', '${SVC_B}', '${SVC_C}']:
    path = os.path.join('.', svc + '.py')
    spec = importlib.util.spec_from_file_location(svc, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
print('IMPORTS_OK')
\"" "services_fail_to_import"

# ── 2. svc_a health_check() returns {status:ok} ─────────────────────────────
check "python3 -c \"
import importlib.util, os
spec = importlib.util.spec_from_file_location('${SVC_A}', './${SVC_A}.py')
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
result = mod.health_check()
assert result.get('status') == 'ok', f'svc_a health={result}'
assert result.get('service') == '${SVC_A}', f'svc_a service field={result}'
print('SVC_A_HEALTH_OK')
\"" "svc_a_health_fail"

# ── 3. svc_b health_check() returns {status:ok} ─────────────────────────────
check "python3 -c \"
import importlib.util, os
spec = importlib.util.spec_from_file_location('${SVC_B}', './${SVC_B}.py')
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
result = mod.health_check()
assert result.get('status') == 'ok', f'svc_b health={result}'
assert result.get('service') == '${SVC_B}', f'svc_b service field={result}'
print('SVC_B_HEALTH_OK')
\"" "svc_b_health_fail"

# ── 4. svc_c health_check() returns {status:ok} ─────────────────────────────
check "python3 -c \"
import importlib.util, os
spec = importlib.util.spec_from_file_location('${SVC_C}', './${SVC_C}.py')
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
result = mod.health_check()
assert result.get('status') == 'ok', f'svc_c health={result}'
assert result.get('service') == '${SVC_C}', f'svc_c service field={result}'
print('SVC_C_HEALTH_OK')
\"" "svc_c_health_fail"

# ── 5. svc_a root-cause bug is fixed ────────────────────────────────────────
check "python3 -c \"
bug_id = '${BUG_ID}'
with open('${SVC_A}.py') as f:
    code = f.read()
if bug_id == 'bad_timeout':
    # timeout_ms must not be used raw when config value is 0
    # check that either timeout is corrected in config or code guards against 0
    import json
    cfg = json.load(open('config.json'))
    t = cfg.get('timeouts', {}).get('upstream_ms', -1)
    assert t > 0, f'upstream_ms still 0 in config: {t}'
elif bug_id == 'bad_connection_string':
    import json
    cfg = json.load(open('config.json'))
    # find any service entry that was 'localhost' — must now be 127.0.0.1
    for svc_cfg in cfg.get('services', {}).values():
        assert svc_cfg.get('host') != 'localhost', 'host still localhost in config'
elif bug_id == 'missing_retry':
    import ast
    tree = ast.parse(code)
    target = next(
        (node for node in ast.walk(tree)
         if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
         and node.name == '_call_upstream'),
        tree,
    )
    has_loop = any(isinstance(node, (ast.For, ast.While)) for node in ast.walk(target))
    has_retry_call = any(
        isinstance(node, ast.Call)
        and 'retry' in (
            node.func.id if isinstance(node.func, ast.Name)
            else node.func.attr if isinstance(node.func, ast.Attribute)
            else ''
        ).lower()
        for node in ast.walk(target)
    )
    assert has_loop or has_retry_call, 'No executable retry logic found in svc_a'
elif bug_id == 'wrong_port':
    import json
    cfg = json.load(open('config.json'))
    expected = json.load(open('${REPORTS}/expected.json'))
    correct_port = expected['port_b']
    actual_port = cfg['services'].get(expected['svc_b'], {}).get('port', -1)
    assert actual_port == correct_port, f'port still wrong: {actual_port} != {correct_port}'
elif bug_id == 'disabled_healthcheck':
    # health_check must not return status=error when _service_ok is True
    import importlib.util
    spec = importlib.util.spec_from_file_location('svc_a_mod', '${SVC_A}.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    r = mod.health_check()
    assert r.get('status') == 'ok', f'health still returns error: {r}'
print('ROOT_CAUSE_FIXED')
\"" "root_cause_not_fixed"

# ── 6. svc_b has retry/circuit-breaker guard ────────────────────────────────
check "python3 -c \"
import ast
with open('${SVC_B}.py') as f:
    code = f.read()
tree = ast.parse(code)
target = next(
    (node for node in ast.walk(tree)
     if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == 'process'),
    tree,
)
has_loop = any(isinstance(node, (ast.For, ast.While)) for node in ast.walk(target))
has_guard_call = any(
    isinstance(node, ast.Call)
    and any(token in (
        node.func.id if isinstance(node.func, ast.Name)
        else node.func.attr if isinstance(node.func, ast.Attribute)
        else ''
    ).lower() for token in ('retry', 'circuit'))
    for node in ast.walk(target)
)
assert has_loop or has_guard_call, 'No executable retry/circuit-breaker logic found in svc_b'
print('SVC_B_RETRY_OK')
\"" "svc_b_no_retry"

# ── 7. svc_c has atomic write guard ─────────────────────────────────────────
check "python3 -c \"
import importlib.util
spec = importlib.util.spec_from_file_location('svc_c_guard', './${SVC_C}.py')
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
before = len(mod.get_all())
try:
    mod.store({'id': 'incomplete', 'payload': 'payload'})
except (KeyError, TypeError, ValueError):
    pass
else:
    raise AssertionError('Incomplete record was accepted')
assert len(mod.get_all()) == before, 'Incomplete record was partially committed'
complete = {'id': 'complete', 'payload': 'payload', 'checksum': 'sha256:test'}
mod.store(complete)
stored = mod.get_all()
assert len(stored) == before + 1, 'Complete record was not committed'
assert stored[-1].get('checksum') == complete['checksum'], 'Checksum was not committed atomically'
print('SVC_C_GUARD_OK')
\"" "svc_c_no_atomic_guard"

# ── 8. Required repair sequence: svc_c, then svc_b, then root cause ──────────
EDIT_TRACE="$(dirname "$WORKSPACE")/logs/workspace_edit_trace.jsonl"
check "python3 - '$EDIT_TRACE' '${SVC_A}.py' '${SVC_B}.py' '${SVC_C}.py' '${BUG_ID}' <<'PYEOF'
import json
import pathlib
import sys

trace_path, svc_a_path, svc_b_path, svc_c_path, bug_id = sys.argv[1:]
trace_file = pathlib.Path(trace_path)
assert trace_file.is_file(), f'Missing workspace edit trace: {trace_path}'

events = []
for line_number, line in enumerate(trace_file.read_text(encoding='utf-8').splitlines(), 1):
    if not line.strip():
        continue
    event = json.loads(line)
    assert event.get('schema_version') == 1, f'Unsupported trace schema on line {line_number}'
    paths = event.get('paths')
    assert isinstance(paths, list) and all(isinstance(path, str) for path in paths), \
        f'Invalid trace paths on line {line_number}'
    events.append(paths)

def first_change(path):
    return next((index for index, paths in enumerate(events) if path in paths), None)

config_bugs = {'bad_timeout', 'bad_connection_string', 'wrong_port'}
root_path = 'config.json' if bug_id in config_bugs else svc_a_path
sequence = [first_change(svc_c_path), first_change(svc_b_path), first_change(root_path)]
assert all(index is not None for index in sequence), \
    f'Missing required edit event for C/B/root sequence: {sequence}'
assert sequence[0] < sequence[1] < sequence[2], \
    f'Required C -> B -> root edit order not observed: {sequence}'
print('FIX_ORDER_OK')
PYEOF
" "wrong_fix_order"

# ── 9. Diff size not excessive ───────────────────────────────────────────────
check "python3 -c \"
import os
total_lines = 0
for svc in ['${SVC_A}', '${SVC_B}', '${SVC_C}']:
    path = svc + '.py'
    if os.path.isfile(path):
        with open(path) as f:
            total_lines += len(f.readlines())
# Heuristic: total line count of all 3 files should stay reasonable (< 250)
assert total_lines < 250, f'Files appear over-extended: {total_lines} lines total'
print('DIFF_SIZE_OK')
\"" "excessive_changes"

# ── 10. Attestation ──────────────────────────────────────────────────────────
check "python3 -c \"
import json, sys
att = json.load(open(sys.argv[1]))
assert att.get('verdict') == 'pass', f'verdict={att.get(\"verdict\")}'
\" '$SUBMISSION/attestation.json'" "bad_attestation"

PARTIAL=$(python3 -c "print(round($PASSED/max(1,$CHECKS), 2))")
if [ "$PASSED" -eq "$CHECKS" ]; then SUCCESS=1; PASS=true; else SUCCESS=0; PASS=false; fi
FM=$(python3 -c "import json; print(json.dumps([x for x in '${FAILURES}'.split(',') if x]))")

cat > "$REPORTS/score.json" <<JSON
{
  "pass": $PASS,
  "primary": {"success": $SUCCESS},
  "secondary": {"checks_passed": $PASSED, "checks_total": $CHECKS, "partial_score": $PARTIAL},
  "failure_modes": $FM
}
JSON
