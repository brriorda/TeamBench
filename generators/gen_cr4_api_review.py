"""
Parameterized generator for CR4: API Design Review Fix.

Each seed produces:
- A different API domain (user management, product catalog, order management,
  content/blog, event booking)
- A Flask/Python REST API with 5-8 endpoints containing deliberate design violations:
    V1: Wrong HTTP method on create endpoint (GET or PUT instead of POST)
    V2: Inconsistent naming (camelCase route/function for search)
    V3: Missing pagination on list endpoint
    V4: Wrong status codes (200 for creation, 200 for not-found, 200 for delete)
    V5: No /api/v1/ prefix (routes at / or /api/ level)
    V6: Bare string error responses (not JSON {error, code} schema)
- A comprehensive API design guidelines document in the spec
- An API review report listing all 6 violations with fix instructions

TNI driver (Pattern D + C):
- Brief: "Code review found issues with the API design. Fix them."
- Spec: Full review doc with every violation + API design guidelines (Planner-only)
- Executor sees only the brief; Planner coordinates the fix list.

Seed -> domain:
  seed % 5 == 0 -> user_management
  seed % 5 == 1 -> product_catalog
  seed % 5 == 2 -> order_management
  seed % 5 == 3 -> content_blog
  seed % 5 == 4 -> event_booking
"""
from __future__ import annotations

from generators.base import TaskGenerator, GeneratedTask
from generators.primitives import SeededRandom


# ---------------------------------------------------------------------------
# Domain definitions
# ---------------------------------------------------------------------------

DOMAINS = [
    {
        "name": "user_management",
        "title": "User Management API",
        "description": "manages user accounts, profiles, and authentication",
        "resource": "user",
        "resources": "users",
        "id_field": "user_id",
        "field1": "email",
        "field2": "role",
        "field3": "is_active",
        "val1": '"admin@example.com"',
        "val2": '"admin"',
        "val3": "True",
        "filter_field": "role",
        "filter_val": '"admin"',
    },
    {
        "name": "product_catalog",
        "title": "Product Catalog API",
        "description": "manages product listings, categories, and inventory",
        "resource": "product",
        "resources": "products",
        "id_field": "product_id",
        "field1": "category",
        "field2": "price",
        "field3": "in_stock",
        "val1": '"electronics"',
        "val2": "29.99",
        "val3": "True",
        "filter_field": "category",
        "filter_val": '"electronics"',
    },
    {
        "name": "order_management",
        "title": "Order Management API",
        "description": "manages customer orders, line items, and fulfillment",
        "resource": "order",
        "resources": "orders",
        "id_field": "order_id",
        "field1": "status",
        "field2": "total",
        "field3": "customer_id",
        "val1": '"pending"',
        "val2": "149.99",
        "val3": '"cust_001"',
        "filter_field": "status",
        "filter_val": '"pending"',
    },
    {
        "name": "content_blog",
        "title": "Content Blog API",
        "description": "manages blog posts, authors, tags, and comments",
        "resource": "post",
        "resources": "posts",
        "id_field": "post_id",
        "field1": "title",
        "field2": "author",
        "field3": "published",
        "val1": '"Hello World"',
        "val2": '"alice"',
        "val3": "False",
        "filter_field": "author",
        "filter_val": '"alice"',
    },
    {
        "name": "event_booking",
        "title": "Event Booking API",
        "description": "manages events, bookings, venues, and capacity",
        "resource": "event",
        "resources": "events",
        "id_field": "event_id",
        "field1": "venue",
        "field2": "capacity",
        "field3": "date",
        "val1": '"Grand Hall"',
        "val2": "200",
        "val3": '"2025-06-15"',
        "filter_field": "venue",
        "filter_val": '"Grand Hall"',
    },
]

# ---------------------------------------------------------------------------
# V1: Wrong HTTP method on create (bad_method always != POST)
# ---------------------------------------------------------------------------
V1_BAD_METHODS = ["GET", "PUT", "GET", "DELETE", "GET"]

# ---------------------------------------------------------------------------
# V2: camelCase route segment to use (will be renamed to snake_case in fix)
# ---------------------------------------------------------------------------
V2_BAD_NAMES = [
    ("getUser",      "get_user"),
    ("bookEvent",    "book_event"),
    ("orderItems",   "order_items"),
    ("createPost",   "create_post"),
    ("searchItems",  "search_items"),
]

# ---------------------------------------------------------------------------
# V3: Pagination param names
# ---------------------------------------------------------------------------
V3_PARAMS = [
    ("page", "page_size"),
    ("page", "per_page"),
    ("offset", "limit"),
    ("page", "page_size"),
    ("page", "per_page"),
]

# ---------------------------------------------------------------------------
# V4: Wrong status code for each operation
#     (create_bad, notfound_bad, delete_bad, client_err_bad)
#     After fix: create->201, notfound->404, delete->204, client_err->400
# ---------------------------------------------------------------------------
V4_VARIANTS = [
    (200, 200, 200, 500),
    (200, 200, 200, 500),
    (200, 200, 200, 500),
    (200, 200, 200, 500),
    (200, 200, 200, 500),
]

# ---------------------------------------------------------------------------
# V5: Route prefix before the fix (always missing /api/v1/)
# ---------------------------------------------------------------------------
V5_BAD_PREFIXES = [
    "",          # seed 0: no prefix at all -> /{resources}
    "/api",      # seed 1: /api/{resources}
    "",          # seed 2: no prefix
    "/api",      # seed 3: /api/{resources}
    "",          # seed 4: no prefix
]

# ---------------------------------------------------------------------------
# V6: Error body and code to embed (bare strings, no JSON schema)
#     error_msg is the human string used in the raw return
# ---------------------------------------------------------------------------
V6_ERROR_MSGS = [
    ("Not found",          "NOT_FOUND"),
    ("Resource not found", "NOT_FOUND"),
    ("Missing resource",   "NOT_FOUND"),
    ("Not found",          "NOT_FOUND"),
    ("Resource not found", "NOT_FOUND"),
]


class Generator(TaskGenerator):
    task_id = "CR4_api_review"
    domain = "code_review"
    difficulty = "hard"
    languages = ["python"]

    def generate(self, seed: int) -> GeneratedTask:
        rng = SeededRandom(seed)

        domain = DOMAINS[seed % len(DOMAINS)]
        v1_bad   = V1_BAD_METHODS[seed % len(V1_BAD_METHODS)]
        v2_bad, v2_good = V2_BAD_NAMES[rng.randint(0, len(V2_BAD_NAMES) - 1)]
        v3_p1, v3_p2    = V3_PARAMS[seed % len(V3_PARAMS)]
        v4_create, v4_notfound, v4_delete, v4_client = V4_VARIANTS[seed % len(V4_VARIANTS)]
        v5_bad_prefix    = V5_BAD_PREFIXES[seed % len(V5_BAD_PREFIXES)]
        v6_msg, v6_code  = V6_ERROR_MSGS[seed % len(V6_ERROR_MSGS)]

        port = 5000 + (seed % 10) * 100

        workspace_files = {
            "app.py": self._generate_app(
                domain, v1_bad, v2_bad,
                v3_p1, v3_p2,
                v4_create, v4_notfound, v4_delete, v4_client,
                v5_bad_prefix,
                v6_msg,
                port,
            ),
            "requirements.txt": "flask>=2.3.0\npytest>=7.0.0\npytest-flask>=1.2.0\n",
            "tests/__init__.py": "",
            "tests/test_api.py": self._generate_tests(domain, v3_p1, v3_p2),
        }

        expected = {
            "domain":       domain["name"],
            "resource":     domain["resource"],
            "resources":    domain["resources"],
            "v1_bad_method": v1_bad,
            "v2_bad_name":  v2_bad,
            "v2_good_name": v2_good,
            "v3_param1":    v3_p1,
            "v3_param2":    v3_p2,
            "v4_create_bad":   v4_create,
            "v4_notfound_bad": v4_notfound,
            "v4_delete_bad":   v4_delete,
            "v4_client_bad":   v4_client,
            "v5_bad_prefix":   v5_bad_prefix,
            "v5_good_prefix":  "/api/v1",
            "v6_error_msg":    v6_msg,
            "port":            port,
        }

        spec_md  = self._generate_spec(
            domain, v1_bad, v2_bad, v2_good,
            v3_p1, v3_p2,
            v4_create, v4_notfound, v4_delete, v4_client,
            v5_bad_prefix,
            v6_msg, v6_code,
        )
        brief_md = self._generate_brief(domain)

        return GeneratedTask(
            task_id=self.task_id,
            seed=seed,
            spec_md=spec_md,
            brief_md=brief_md,
            expected=expected,
            workspace_files=workspace_files,
        )

    # ------------------------------------------------------------------
    # Workspace: Flask app with 6 deliberate design violations
    # ------------------------------------------------------------------

    def _generate_app(
        self,
        domain: dict,
        v1_bad: str,           # wrong HTTP method for create
        v2_bad: str,           # camelCase function/route name
        v3_p1: str,            # pagination param 1
        v3_p2: str,            # pagination param 2
        v4_create: int,        # wrong code for create success
        v4_notfound: int,      # wrong code for not-found
        v4_delete: int,        # wrong code for delete success
        v4_client: int,        # wrong code for client errors
        v5_bad_prefix: str,    # route prefix (missing /api/v1)
        v6_msg: str,           # bare error message string
        port: int,
    ) -> str:
        r   = domain["resource"]
        rs  = domain["resources"]
        idf = domain["id_field"]
        f1  = domain["field1"]
        f2  = domain["field2"]
        f3  = domain["field3"]
        ff  = domain["filter_field"]

        # V5: route prefix (does NOT start with /api/v1/)
        if v5_bad_prefix:
            prefix = f"{v5_bad_prefix}/{rs}"
        else:
            prefix = f"/{rs}"

        # V1: use a distinct sub-path for create so it never conflicts with
        # the GET list route even when v1_bad == "GET".
        # The violation is: the endpoint that SHOULD be POST /{rs} is instead
        # registered as {v1_bad} at /{rs}/new — agents must move it to POST /{rs}.
        create_path = f"{prefix}/new"

        return f'''"""
{domain["title"]}

This module implements a REST API for {domain["description"]}.

NOTE: This file contains API design issues identified in code review.
See the review report for the full list of violations that must be fixed.
"""
from flask import Flask, request, jsonify

app = Flask(__name__)

# ---------------------------------------------------------------------------
# In-memory data store
# ---------------------------------------------------------------------------
_{rs}: dict = {{}}
_id_counter: int = 1


def _new_id() -> str:
    global _id_counter
    _id_counter += 1
    return f"{r}_{{_id_counter - 1}}"


# ===========================================================================
# VIOLATION SUMMARY (all must be fixed):
#   V1: create_{r} is at "{create_path}" with method {v1_bad} instead of
#       POST at "{prefix}"
#   V2: search route is "{prefix}/{v2_bad}" (camelCase) instead of
#       "{prefix}/search" with snake_case function name
#   V3: list_{rs} returns all records with no pagination
#   V4: wrong status codes — create returns {v4_create} (need 201),
#       not-found returns {v4_notfound} (need 404),
#       delete returns {v4_delete} (need 204),
#       client errors return {v4_client} (need 400)
#   V5: all routes use prefix "{prefix}" instead of /api/v1/{rs}
#   V6: error responses are bare strings, not JSON {{error, code}} objects
# ===========================================================================


# VIOLATION V1: create endpoint uses wrong method AND wrong path
# Correct: POST {prefix}  |  Current: {v1_bad} {create_path}
@app.route("{create_path}", methods=["{v1_bad}"])
def create_{r}():
    """Create a new {r}.

    VIOLATION V1: Route is {v1_bad} {create_path} — should be POST {prefix}.
    VIOLATION V5: Route missing /api/v1/ prefix.
    """
    data = request.get_json(force=True) or {{}}
    if "{f1}" not in data:
        # VIOLATION V6: bare string error, not JSON schema
        # VIOLATION V4: should be 400, not {v4_client}
        return "{v6_msg}", {v4_client}
    rid = _new_id()
    record = {{
        "{idf}": rid,
        "{f1}": data["{f1}"],
        "{f2}": data.get("{f2}"),
        "{f3}": data.get("{f3}", False),
    }}
    _{rs}[rid] = record
    # VIOLATION V4: should be 201, not {v4_create}
    return jsonify(record), {v4_create}


@app.route("{prefix}", methods=["GET"])
def list_{rs}():
    """List {rs}.

    VIOLATION V3: No pagination — returns entire dataset unconditionally.
    VIOLATION V5: Route missing /api/v1/ prefix.
    """
    # BUG V3: no {v3_p1}/{v3_p2} parameters — returns everything
    items = list(_{rs}.values())
    return jsonify({{"{rs}": items, "count": len(items)}})


@app.route("{prefix}/<item_id>", methods=["GET"])
def get_{r}(item_id: str):
    """Retrieve a single {r} by ID.

    VIOLATION V5: Route missing /api/v1/ prefix.
    VIOLATION V4+V6: not-found returns bare string with wrong status.
    """
    record = _{rs}.get(item_id)
    if record is None:
        # VIOLATION V6: bare string, not JSON error schema
        # VIOLATION V4: should be 404, not {v4_notfound}
        return "{v6_msg}", {v4_notfound}
    return jsonify(record)


@app.route("{prefix}/<item_id>", methods=["PUT"])
def update_{r}(item_id: str):
    """Update an existing {r}.

    VIOLATION V5: Route missing /api/v1/ prefix.
    """
    record = _{rs}.get(item_id)
    if record is None:
        # VIOLATION V6: bare string error
        return "{v6_msg}", 404
    data = request.get_json(force=True) or {{}}
    record.update({{k: v for k, v in data.items() if k != "{idf}"}})
    _{rs}[item_id] = record
    return jsonify(record)


@app.route("{prefix}/<item_id>", methods=["DELETE"])
def delete_{r}(item_id: str):
    """Delete a {r}.

    VIOLATION V5: Route missing /api/v1/ prefix.
    VIOLATION V4: should return 204, not {v4_delete}.
    """
    record = _{rs}.pop(item_id, None)
    if record is None:
        # VIOLATION V6: bare string error
        return "{v6_msg}", 404
    # VIOLATION V4: should be 204, not {v4_delete}
    return jsonify({{"deleted": True}}), {v4_delete}


# VIOLATION V2: camelCase route and function name
@app.route("{prefix}/{v2_bad}", methods=["GET"])
def {v2_bad}():
    """Search/filter {rs}.

    VIOLATION V2: Route and function use camelCase name '{v2_bad}'.
                  Should be /search with function 'search_{rs}'.
    VIOLATION V5: Route missing /api/v1/ prefix.
    """
    filter_val = request.args.get("{ff}")
    results = [
        item for item in _{rs}.values()
        if filter_val is None or str(item.get("{ff}")) == str(filter_val)
    ]
    return jsonify({{"{rs}": results}})


@app.route("{prefix}/health", methods=["GET"])
def health_check():
    """Health check.

    VIOLATION V5: Route missing /api/v1/ prefix.
    """
    return jsonify({{"status": "ok", "service": "{domain["title"]}"}})


@app.route("{prefix}/stats", methods=["GET"])
def get_stats():
    """Aggregate statistics.

    VIOLATION V4: Returns {v4_client} for bad client input (should be 400).
    VIOLATION V5: Route missing /api/v1/ prefix.
    VIOLATION V6: bare string error response.
    """
    group_by = request.args.get("group_by", "{f1}")
    if group_by not in ("{f1}", "{f2}", "{f3}"):
        # VIOLATION V4+V6: should be 400 with JSON error schema
        return "{v6_msg}", {v4_client}
    counts: dict = {{}}
    for item in _{rs}.values():
        key = str(item.get(group_by, "unknown"))
        counts[key] = counts.get(key, 0) + 1
    return jsonify({{"group_by": group_by, "counts": counts, "total": len(_{rs})}})


if __name__ == "__main__":
    app.run(debug=True, port={port})
'''

    # ------------------------------------------------------------------
    # Tests for the FIXED version
    # ------------------------------------------------------------------

    def _generate_tests(self, domain: dict, v3_p1: str, v3_p2: str) -> str:
        r   = domain["resource"]
        rs  = domain["resources"]
        f1  = domain["field1"]
        f2  = domain["field2"]
        v1  = domain["val1"]
        v2  = domain["val2"]
        ff  = domain["filter_field"]

        base = f"/api/v1/{rs}"

        return f'''"""
Integration tests for the fixed {domain["title"]}.

These tests validate the API after ALL design violations have been corrected:
  V1: create uses POST
  V2: search route is snake_case
  V3: list endpoint supports pagination
  V4: correct status codes (201 create, 404 not-found, 204 delete, 400 client-error)
  V5: all routes under /api/v1/
  V6: all error responses are JSON with "error" and "code" keys
"""
import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import app as flask_app


@pytest.fixture(autouse=True)
def reset_store():
    """Reset in-memory store before each test."""
    import app as app_module
    getattr(app_module, "_{rs}").clear()
    yield


@pytest.fixture
def client():
    flask_app.config["TESTING"] = True
    with flask_app.test_client() as c:
        yield c


# ── V5: All routes under /api/v1/ ────────────────────────────────────────────

def test_list_route_versioned(client):
    """GET {base} must exist and return 200."""
    resp = client.get("{base}")
    assert resp.status_code == 200, (
        f"Expected 200, got {{resp.status_code}}. "
        "Route may be missing /api/v1/ prefix (V5 not fixed)."
    )


def test_health_route_versioned(client):
    """Health check must be under /api/v1/."""
    resp = client.get("{base}/health")
    assert resp.status_code == 200, (
        f"Expected 200, got {{resp.status_code}}. Health route missing /api/v1/ prefix."
    )
    data = resp.get_json()
    assert data is not None and "status" in data


# ── V1: Create uses POST ──────────────────────────────────────────────────────

def test_create_uses_post(client):
    """POST {base} must be accepted (not 405)."""
    resp = client.post("{base}", json={{"{f1}": {v1}, "{f2}": {v2}}})
    assert resp.status_code != 405, (
        "POST returned 405 Method Not Allowed — V1 not fixed (create still uses wrong method)."
    )


def test_get_method_not_create(client):
    """GET {base} must list resources, not create (idempotent)."""
    # Two GETs in a row must not increase count
    r1 = client.get("{base}")
    r2 = client.get("{base}")
    d1 = r1.get_json()
    d2 = r2.get_json()
    assert d1 == d2, "GET is not idempotent — it may be mutating state (V1 issue)."


# ── V4: Correct status codes ──────────────────────────────────────────────────

def test_create_returns_201(client):
    """POST must return 201 Created."""
    resp = client.post("{base}", json={{"{f1}": {v1}, "{f2}": {v2}}})
    assert resp.status_code == 201, (
        f"Expected 201, got {{resp.status_code}} — V4 create status not fixed."
    )


def test_not_found_returns_404(client):
    """GET on missing resource must return 404."""
    resp = client.get("{base}/nonexistent_xyz_999")
    assert resp.status_code == 404, (
        f"Expected 404, got {{resp.status_code}} — V4 not-found status not fixed."
    )


def test_delete_returns_204(client):
    """DELETE must return 204 No Content."""
    # Create first
    cr = client.post("{base}", json={{"{f1}": {v1}, "{f2}": {v2}}})
    assert cr.status_code == 201
    created = cr.get_json()
    item_id = next(v for k, v in created.items() if "id" in k.lower())
    dr = client.delete(f"{base}/{{item_id}}")
    assert dr.status_code == 204, (
        f"Expected 204, got {{dr.status_code}} — V4 delete status not fixed."
    )


def test_client_error_returns_400(client):
    """POST with missing required field must return 400."""
    resp = client.post("{base}", json={{}})
    assert resp.status_code == 400, (
        f"Expected 400, got {{resp.status_code}} — V4 client-error status not fixed."
    )


# ── V6: JSON error schema ─────────────────────────────────────────────────────

def test_not_found_error_is_json(client):
    """404 response must be JSON with 'error' and 'code' fields."""
    resp = client.get("{base}/no_such_id_abc")
    assert resp.status_code == 404
    data = resp.get_json()
    assert data is not None, "404 must return JSON body, not a plain string (V6 not fixed)."
    assert "error" in data, f"JSON error body must have 'error' key. Got: {{data}}"
    assert "code" in data, f"JSON error body must have 'code' key. Got: {{data}}"


def test_bad_request_error_is_json(client):
    """400 response must be JSON with 'error' and 'code' fields."""
    resp = client.post("{base}", json={{}})
    assert resp.status_code == 400
    data = resp.get_json()
    assert data is not None, "400 must return JSON body (V6 not fixed)."
    assert "error" in data, f"JSON error body must have 'error' key. Got: {{data}}"
    assert "code" in data, f"JSON error body must have 'code' key. Got: {{data}}"


# ── V3: Pagination ────────────────────────────────────────────────────────────

def test_list_accepts_pagination_params(client):
    """List endpoint must accept {v3_p1} and {v3_p2} query params."""
    resp = client.get("{base}?{v3_p1}=1&{v3_p2}=10")
    assert resp.status_code == 200, (
        f"GET with pagination params returned {{resp.status_code}} — V3 not fixed."
    )


def test_list_respects_page_size(client):
    """List with {v3_p2}=2 must return at most 2 items."""
    # Seed 5 records
    for i in range(5):
        client.post("{base}", json={{"{f1}": f"val_{{i}}", "{f2}": {v2}}})
    resp = client.get("{base}?{v3_p1}=1&{v3_p2}=2")
    assert resp.status_code == 200
    data = resp.get_json()
    items_key = "{rs}" if "{rs}" in data else "items"
    if items_key in data:
        assert len(data[items_key]) <= 2, (
            f"Expected <=2 items with {v3_p2}=2, got {{len(data[items_key])}} — V3 not fixed."
        )


def test_list_response_has_total(client):
    """List response must include a 'total' count field (pagination envelope)."""
    resp = client.get("{base}?{v3_p1}=1&{v3_p2}=10")
    data = resp.get_json()
    assert "total" in data, (
        f"List response missing 'total' field — pagination envelope not implemented (V3)."
    )


# ── V2: snake_case routes ─────────────────────────────────────────────────────

def test_search_route_snake_case(client):
    """Search route must be /search (snake_case), not a camelCase name."""
    resp = client.get("{base}/search")
    assert resp.status_code != 404, (
        "GET {base}/search returned 404 — snake_case search route not implemented (V2 not fixed)."
    )
    assert resp.status_code == 200


def test_update_and_get(client):
    """Basic create->get->update->get round-trip under /api/v1/."""
    cr = client.post("{base}", json={{"{f1}": {v1}, "{f2}": {v2}}})
    assert cr.status_code == 201
    created = cr.get_json()
    item_id = next(v for k, v in created.items() if "id" in k.lower())

    gr = client.get(f"{base}/{{item_id}}")
    assert gr.status_code == 200

    ur = client.put(f"{base}/{{item_id}}", json={{"{f1}": "updated_value"}})
    assert ur.status_code == 200
    assert ur.get_json()["{f1}"] == "updated_value"
'''

    # ------------------------------------------------------------------
    # Spec: Full API review report + design guidelines (Planner-only)
    # ------------------------------------------------------------------

    def _generate_spec(
        self,
        domain: dict,
        v1_bad: str,
        v2_bad: str, v2_good: str,
        v3_p1: str, v3_p2: str,
        v4_create: int, v4_notfound: int, v4_delete: int, v4_client: int,
        v5_bad_prefix: str,
        v6_msg: str, v6_code: str,
    ) -> str:
        r  = domain["resource"]
        rs = domain["resources"]
        f1 = domain["field1"]
        f2 = domain["field2"]
        f3 = domain["field3"]

        if v5_bad_prefix:
            route_example = f"{v5_bad_prefix}/{rs}"
        else:
            route_example = f"/{rs}"

        return f"""# CR4: API Design Review Fix

## Goal
Fix all six API design violations identified in the code review of `app.py`.
The API must comply with the API Design Guidelines below after your changes.

All existing tests in `tests/test_api.py` must pass.

---

## Module Under Review

**{domain["title"]}** — `app.py`

This module {domain["description"]}.

---

## API Design Guidelines

### G1 — HTTP Methods
| Intent | Method |
|--------|--------|
| Create resource | **POST** |
| Read resource(s) | **GET** |
| Replace resource | **PUT** |
| Partial update | **PATCH** |
| Delete resource | **DELETE** |

Never use GET for operations that mutate state.
Never use PUT or DELETE for creation.

### G2 — Naming Conventions
- All route path segments must use **snake_case** (e.g. `/search_results`, not `/searchResults`)
- Collection endpoints use plural nouns (e.g. `/{rs}`, not `/{r}`)
- Python function names must mirror their route in snake_case
- A search/filter endpoint must be named `search_{rs}` and routed to `/search`

### G3 — Pagination
- Every collection `GET` endpoint **must** support pagination via query parameters
- Required parameters: `{v3_p1}` and `{v3_p2}`
- Default values: `{v3_p1}=1`, `{v3_p2}=20`
- Response envelope must include:
  ```json
  {{
    "{rs}": [...paginated slice...],
    "{v3_p1}": <current page>,
    "{v3_p2}": <items per page>,
    "total": <total record count>
  }}
  ```
- Never return the entire dataset in a single response

### G4 — HTTP Status Codes
| Situation | Code |
|-----------|------|
| Create (POST) success | **201 Created** |
| Read (GET) success | 200 OK |
| Update success | 200 OK |
| Delete success | **204 No Content** |
| Resource not found | **404 Not Found** |
| Invalid client input | **400 Bad Request** |
| Validation failure | 422 Unprocessable Entity |
| Unexpected server error | 500 Internal Server Error |

### G5 — API Versioning
- Every route must be prefixed with `/api/v1/`
- Correct: `GET /api/v1/{rs}`, `POST /api/v1/{rs}`, `DELETE /api/v1/{rs}/<id>`
- Incorrect: `GET /{rs}`, `GET /api/{rs}`, `GET /v1/{rs}`

### G6 — Error Response Schema
Every non-2xx response **must** return JSON conforming to:
```json
{{
  "error": "<human-readable description>",
  "code":  "<SCREAMING_SNAKE_CASE identifier>"
}}
```
Plain string responses like `return "Not found", 404` are **not permitted**.

---

## Code Review Report — `app.py`

The following six violations were identified. **All must be fixed.**

---

### VIOLATION V1 — Wrong HTTP Method (breaks G1)

**Location**: `create_{r}()` route decorator

**Problem**: The create endpoint is decorated with `methods=["{v1_bad}"]`.
Creating a new resource is a mutating operation and **must** use POST.

**Required fix**: Change the route decorator to `methods=["POST"]`.

```python
# Before (WRONG):
@app.route("{route_example}", methods=["{v1_bad}"])
def create_{r}():

# After (CORRECT):
@app.route("/api/v1/{rs}", methods=["POST"])
def create_{r}():
```

---

### VIOLATION V2 — camelCase Route and Function Name (breaks G2)

**Location**: Search/filter endpoint — route `/{v2_bad}` and function `{v2_bad}`

**Problem**: Both the URL path segment and the Python function name use camelCase
(`{v2_bad}`). All routes and functions must use snake_case.

**Required fix**: Rename the route to `/search` and the function to `search_{rs}`.

```python
# Before (WRONG):
@app.route("{route_example}/{v2_bad}", methods=["GET"])
def {v2_bad}():

# After (CORRECT):
@app.route("/api/v1/{rs}/search", methods=["GET"])
def search_{rs}():
```

---

### VIOLATION V3 — No Pagination on List Endpoint (breaks G3)

**Location**: `list_{rs}()` — `GET {route_example}`

**Problem**: The endpoint returns the entire `_{rs}` store unconditionally.
For any non-trivial dataset this is a reliability and performance hazard.

**Required fix**: Add `{v3_p1}` and `{v3_p2}` query parameters and slice the result.

```python
@app.route("/api/v1/{rs}", methods=["GET"])
def list_{rs}():
    {v3_p1}  = int(request.args.get("{v3_p1}", 1))
    {v3_p2} = int(request.args.get("{v3_p2}", 20))
    all_items = list(_{rs}.values())
    start = ({v3_p1} - 1) * {v3_p2}
    sliced = all_items[start : start + {v3_p2}]
    return jsonify({{
        "{rs}":     sliced,
        "{v3_p1}":  {v3_p1},
        "{v3_p2}": {v3_p2},
        "total":   len(all_items),
    }})
```

---

### VIOLATION V4 — Wrong HTTP Status Codes (breaks G4)

**Locations and required fixes**:

| Function | Current code | Required code | Reason |
|----------|-------------|---------------|--------|
| `create_{r}()` success path | `{v4_create}` | **201** | Resource creation |
| `get_{r}()` not-found path | `{v4_notfound}` | **404** | Resource missing |
| `delete_{r}()` success path | `{v4_delete}` | **204** | Deletion confirmed |
| `create_{r}()` + `get_stats()` client-error paths | `{v4_client}` | **400** | Bad client input |

Update every `return ..., STATUS` to use the correct code from the table above.

---

### VIOLATION V5 — Missing `/api/v1/` Prefix (breaks G5)

**Problem**: All routes currently use prefix `"{route_example}"` instead of `/api/v1/{rs}`.

**Required fix**: Update **every** `@app.route(...)` in the file to use the `/api/v1/` prefix.

```python
# Before:
@app.route("{route_example}", ...)
@app.route("{route_example}/<item_id>", ...)

# After:
@app.route("/api/v1/{rs}", ...)
@app.route("/api/v1/{rs}/<item_id>", ...)
```

This applies to ALL eight routes: list, create, get, update, delete, search, health, stats.

---

### VIOLATION V6 — Bare String Error Responses (breaks G6)

**Problem**: Every non-2xx return in `app.py` uses a bare string:

```python
return "{v6_msg}", 404   # WRONG — plain string, not JSON
```

**Required fix**: Replace every error return with `jsonify()` conforming to G6:

```python
return jsonify({{"error": "{v6_msg}", "code": "{v6_code}"}}), 404  # CORRECT
```

**Locations** (all must be updated):
- `create_{r}()` — missing-field validation error (`{v4_client}`)
- `get_{r}()` — not-found (`404`)
- `update_{r}()` — not-found (`404`)
- `delete_{r}()` — not-found (`404`)
- `get_stats()` — bad `group_by` parameter (`{v4_client}` → should be `400`)

---

## Summary of All Required Changes

| # | Violation | Location | Fix |
|---|-----------|----------|-----|
| V1 | `{v1_bad}` used for create | `create_{r}()` decorator | Change to `POST` |
| V2 | camelCase route `/{v2_bad}` | search route + function | Rename to `/search` + `search_{rs}()` |
| V3 | No pagination on list | `list_{rs}()` | Add `{v3_p1}` + `{v3_p2}`, slice + envelope |
| V4 | Wrong status codes | create/get/delete/stats | 201 / 404 / 204 / 400 |
| V5 | Missing `/api/v1/` prefix | all 8 routes | Add `/api/v1/` to every route |
| V6 | Bare string errors | 5 error returns | Wrap with `jsonify({{"error":..., "code":...}})` |

## Deliverables
1. `app.py` with all six violations corrected.
2. `tests/test_api.py` must pass without modification.
3. Verifier writes `attestation.json` with `verdict: pass` once all checks pass.
"""

    # ------------------------------------------------------------------
    # Brief: Minimal info for Executor (TNI: Planner has the full spec)
    # ------------------------------------------------------------------

    def _generate_brief(self, domain: dict) -> str:
        r  = domain["resource"]
        rs = domain["resources"]
        return f"""# CR4: API Design Fix (Brief)

## Your Task
The **{domain["title"]}** (`app.py`) was flagged during code review for
multiple API design violations.

Fix all the violations so the API conforms to the team's REST API design guidelines.

## What You Know
- The API is implemented in `app.py` (Flask/Python).
- The code review found issues with HTTP methods, route naming, pagination,
  status codes, API versioning, and error response format.
- `tests/test_api.py` must pass without any modification after your fixes.
- Do NOT modify `tests/test_api.py`.
- Install dependencies before running tests:
  ```bash
  pip install -r requirements.txt
  pytest tests/test_api.py -v
  ```

## What the Planner Has
The Planner has the full API review report with every violation, the exact
locations in `app.py`, and the specific fixes required. Follow the Planner's
instructions precisely.
"""
