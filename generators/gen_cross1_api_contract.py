"""
Parameterized generator for CROSS1: API Contract Reconciliation.

Each seed produces a different API domain (users/products/orders) but the
same 3 structural mismatches between the Go server and Python client:
  1. Field name: camelCase (userId) vs snake_case (user_id)
  2. Pagination keys: data/next vs results/cursor
  3. Error format: HTTP 422 + errors[] vs HTTP 400 + error string
"""
from __future__ import annotations
import os
from generators.base import TaskGenerator, GeneratedTask
from generators.primitives import SeededRandom


# Per-seed domain configuration
DOMAINS = [
    {
        "name": "users",
        "entity": "User",
        "entity_lower": "user",
        "entity_plural": "users",
        "id_field": "UserID",
        "json_id": "userId",
        "spec_id": "user_id",
        "module": "cross1_user_api",
        "port": "18080",
        "sample_items": [
            '{"UserID": 1, "Name": "Alice", "Email": "alice@example.com"}',
            '{"UserID": 2, "Name": "Bob", "Email": "bob@example.com"}',
        ],
        "extra_fields_go": '    Name  string `json:"name"`\n    Email string `json:"email"`',
        "extra_fields_py": "    name: str\n    email: str",
        "extra_from_dict": '            name=data.get("name", ""),\n            email=data.get("email", ""),',
        "route": "/users",
        "create_body": '{"name": "Charlie", "email": "charlie@example.com"}',
        "invalid_body": "not-json",
    },
    {
        "name": "products",
        "entity": "Product",
        "entity_lower": "product",
        "entity_plural": "products",
        "id_field": "ProductID",
        "json_id": "productId",
        "spec_id": "product_id",
        "module": "cross1_product_api",
        "port": "18081",
        "sample_items": [
            '{"ProductID": 1, "Title": "Widget", "Price": 9.99}',
            '{"ProductID": 2, "Title": "Gadget", "Price": 19.99}',
        ],
        "extra_fields_go": '    Title string  `json:"title"`\n    Price float64 `json:"price"`',
        "extra_fields_py": "    title: str\n    price: float",
        "extra_from_dict": '            title=data.get("title", ""),\n            price=data.get("price", 0.0),',
        "route": "/products",
        "create_body": '{"title": "Doohickey", "price": 4.99}',
        "invalid_body": "not-json",
    },
    {
        "name": "orders",
        "entity": "Order",
        "entity_lower": "order",
        "entity_plural": "orders",
        "id_field": "OrderID",
        "json_id": "orderId",
        "spec_id": "order_id",
        "module": "cross1_order_api",
        "port": "18082",
        "sample_items": [
            '{"OrderID": 1, "Status": "pending", "Amount": 100.0}',
            '{"OrderID": 2, "Status": "shipped", "Amount": 250.0}',
        ],
        "extra_fields_go": '    Status string  `json:"status"`\n    Amount float64 `json:"amount"`',
        "extra_fields_py": "    status: str\n    amount: float",
        "extra_from_dict": '            status=data.get("status", ""),\n            amount=data.get("amount", 0.0),',
        "route": "/orders",
        "create_body": '{"status": "pending", "amount": 75.0}',
        "invalid_body": "not-json",
    },
]


class Generator(TaskGenerator):
    task_id = "CROSS1_api_contract"
    domain = "Multi-lang"
    difficulty = "hard"
    languages = ["go", "python"]

    def generate(self, seed: int) -> GeneratedTask:
        rng = SeededRandom(seed)
        d = DOMAINS[seed % len(DOMAINS)]

        workspace_files = self._make_workspace(d, seed)

        tasks_dir = os.path.join(os.path.dirname(__file__), "..", "tasks", "CROSS1_api_contract")
        with open(os.path.join(tasks_dir, "spec.md")) as f:
            spec_md = f.read()
        with open(os.path.join(tasks_dir, "brief.md")) as f:
            brief_md = f.read()

        return GeneratedTask(
            task_id="CROSS1_api_contract",
            seed=seed,
            spec_md=spec_md,
            brief_md=brief_md,
            expected={
                "mismatches_fixed": 3,
                "entity": d["entity"],
                "field_name": d["json_id"],
                "pagination_key": "data",
                "error_status": 422,
                "seed": seed,
                "domain": d["name"],
            },
            workspace_files=workspace_files,
            metadata={"difficulty": "hard", "category": "Multi-lang"},
        )

    def _make_workspace(self, d: dict, seed: int = 0) -> dict:
        files = {}

        # ---------------------------------------------------------------
        # Go service files (source of truth — correct camelCase + new keys)
        # ---------------------------------------------------------------
        files["service/go.mod"] = f'module {d["module"]}\n\ngo 1.18\n// instance-seed: {seed}\n'

        files["service/models.go"] = self._go_models(d)
        files["service/handlers.go"] = self._go_handlers(d)
        files["service/main.go"] = self._go_main(d)
        files["service/middleware.go"] = self._go_middleware(d)

        # ---------------------------------------------------------------
        # Python client (BUGGY — 3 mismatches)
        # ---------------------------------------------------------------
        files["client/__init__.py"] = ""
        files["client/models.py"] = self._py_models(d)
        files["client/api.py"] = self._py_api(d)
        files["client/exceptions.py"] = self._py_exceptions(d)

        # ---------------------------------------------------------------
        # API spec (WRONG in 3 places)
        # ---------------------------------------------------------------
        files["api_spec.yaml"] = self._api_spec(d)

        # ---------------------------------------------------------------
        # Tests (use real Go server via subprocess)
        # ---------------------------------------------------------------
        files["tests/__init__.py"] = ""
        files["tests/conftest.py"] = self._conftest(d)
        files["tests/test_integration.py"] = self._test_integration(d)
        files["tests/test_pagination.py"] = self._test_pagination(d)
        files["tests/test_errors.py"] = self._test_errors(d)

        return files

    # ------------------------------------------------------------------
    # Go source generators
    # ------------------------------------------------------------------

    def _go_models(self, d: dict) -> str:
        entity = d["entity"]
        id_field = d["id_field"]
        json_id = d["json_id"]
        extra = d["extra_fields_go"]
        return f'''package main

type {entity} struct {{
\t{id_field} int    `json:"{json_id}"`
{extra}
}}

type PaginatedResponse struct {{
\tData  interface{{}} `json:"data"`
\tNext  string       `json:"next"`
\tTotal int          `json:"total"`
}}

type ErrorResponse struct {{
\tErrors []string `json:"errors"`
}}
'''

    def _go_handlers(self, d: dict) -> str:
        entity = d["entity"]
        id_field = d["id_field"]
        route = d["route"]
        port = d["port"]
        # Build two sample items inline
        sample1 = "{" + f"{id_field}: 1"
        sample2 = "{" + f"{id_field}: 2"
        # extra field initializers from the sample_items description
        extra_inits1 = self._go_extra_inits(d, 1)
        extra_inits2 = self._go_extra_inits(d, 2)
        return f'''package main

import (
\t"encoding/json"
\t"net/http"
\t"strconv"
)

func list{entity}s(w http.ResponseWriter, r *http.Request) {{
\titems := []{entity}{{
\t\t{{{id_field}: 1{extra_inits1}}},
\t\t{{{id_field}: 2{extra_inits2}}},
\t}}
\tpage := 1
\tpageStr := r.URL.Query().Get("page")
\tif pageStr != "" {{
\t\tpage, _ = strconv.Atoi(pageStr)
\t}}

\tresp := PaginatedResponse{{
\t\tData:  items,
\t\tNext:  "cursor_" + strconv.Itoa(page+1),
\t\tTotal: len(items),
\t}}
\tw.Header().Set("Content-Type", "application/json")
\tjson.NewEncoder(w).Encode(resp)
}}

func create{entity}(w http.ResponseWriter, r *http.Request) {{
\tvar item {entity}
\tif err := json.NewDecoder(r.Body).Decode(&item); err != nil {{
\t\tw.WriteHeader(422)
\t\tw.Header().Set("Content-Type", "application/json")
\t\tjson.NewEncoder(w).Encode(ErrorResponse{{
\t\t\tErrors: []string{{"Invalid JSON body", "Request body required"}},
\t\t}})
\t\treturn
\t}}
\tw.WriteHeader(201)
\tw.Header().Set("Content-Type", "application/json")
\tjson.NewEncoder(w).Encode(item)
}}
'''

    def _go_extra_inits(self, d: dict, idx: int) -> str:
        """Generate extra field initializers for Go struct literals."""
        name = d["name"]
        if name == "users":
            names = ["Alice", "Bob"]
            emails = ["alice@example.com", "bob@example.com"]
            return f', Name: "{names[idx-1]}", Email: "{emails[idx-1]}"'
        elif name == "products":
            titles = ["Widget", "Gadget"]
            prices = ["9.99", "19.99"]
            return f', Title: "{titles[idx-1]}", Price: {prices[idx-1]}'
        else:  # orders
            statuses = ["pending", "shipped"]
            amounts = ["100.0", "250.0"]
            return f', Status: "{statuses[idx-1]}", Amount: {amounts[idx-1]}'

    def _go_main(self, d: dict) -> str:
        entity = d["entity"]
        route = d["route"]
        return f'''package main

import (
\t"fmt"
\t"net/http"
\t"os"
)

func main() {{
\tport := "8080"
\tif p := os.Getenv("PORT"); p != "" {{
\t\tport = p
\t}}

\tmux := http.NewServeMux()
\tmux.HandleFunc("{route}", func(w http.ResponseWriter, r *http.Request) {{
\t\tif r.Method == "GET" {{
\t\t\tlist{entity}s(w, r)
\t\t}} else if r.Method == "POST" {{
\t\t\tcreate{entity}(w, r)
\t\t}} else {{
\t\t\tw.WriteHeader(405)
\t\t}}
\t}})

\tfmt.Printf("Server starting on port %s\\n", port)
\thttp.ListenAndServe(":"+port, mux)
}}
'''

    def _go_middleware(self, d: dict) -> str:
        return '''package main

import "net/http"

// corsMiddleware adds basic CORS headers for local testing.
func corsMiddleware(next http.Handler) http.Handler {
\treturn http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
\t\tw.Header().Set("Access-Control-Allow-Origin", "*")
\t\tw.Header().Set("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
\t\tw.Header().Set("Access-Control-Allow-Headers", "Content-Type")
\t\tif r.Method == "OPTIONS" {
\t\t\tw.WriteHeader(204)
\t\t\treturn
\t\t}
\t\tnext.ServeHTTP(w, r)
\t})
}
'''

    # ------------------------------------------------------------------
    # Python source generators (BUGGY)
    # ------------------------------------------------------------------

    def _py_models(self, d: dict) -> str:
        entity = d["entity"]
        id_field = d["id_field"].lower()   # python attr name: userid, productid, orderid
        spec_id = d["spec_id"]             # buggy: user_id, product_id, order_id
        json_id = d["json_id"]             # correct: userId, productId, orderId
        extra_fields = d["extra_fields_py"]
        extra_from_dict = d["extra_from_dict"]
        return f'''from dataclasses import dataclass
from typing import Optional


@dataclass
class {entity}:
    {spec_id}: int    # BUG: server sends "{json_id}" (camelCase)
{extra_fields}

    @classmethod
    def from_dict(cls, data: dict) -> \'{entity}\':
        return cls(
            {spec_id}=data.get("{spec_id}"),  # BUG: should be data.get("{json_id}")
{extra_from_dict}
        )
'''

    def _py_api(self, d: dict) -> str:
        entity = d["entity"]
        entity_lower = d["entity_lower"]
        entity_plural = d["entity_plural"]
        route = d["route"]
        spec_id = d["spec_id"]
        return f'''import requests
from typing import List, Optional, Tuple


class APIClient:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")

    def list_{entity_plural}(self, page: int = 1) -> Tuple[List, Optional[str]]:
        resp = requests.get(
            f"{{self.base_url}}{route}",
            params={{"page": page}},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        from client.models import {entity}
        # BUG: server sends "data" and "next", not "results" and "cursor"
        items = [
            {entity}.from_dict(u)
            for u in data.get("results", [])   # BUG: should be "data"
        ]
        next_cursor = data.get("cursor")        # BUG: should be "next"
        return items, next_cursor

    def create_{entity_lower}(self, payload: dict) -> dict:
        resp = requests.post(
            f"{{self.base_url}}{route}",
            json=payload,
            timeout=10,
        )
        if resp.status_code >= 400:
            from client.exceptions import parse_error_response
            raise parse_error_response(resp)
        return resp.json()
'''

    def _py_exceptions(self, d: dict) -> str:
        return '''class APIError(Exception):
    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        self.message = message
        super().__init__(f"API Error {status_code}: {message}")


def parse_error_response(response) -> APIError:
    if response.status_code == 400:
        data = response.json()
        return APIError(400, data.get("error", "Unknown error"))
    return APIError(response.status_code, "HTTP error")
'''

    # ------------------------------------------------------------------
    # API spec (WRONG in 3 places)
    # ------------------------------------------------------------------

    def _api_spec(self, d: dict) -> str:
        entity_lower = d["entity_lower"]
        entity_plural = d["entity_plural"]
        spec_id = d["spec_id"]    # wrong: user_id
        json_id = d["json_id"]    # correct: userId
        route = d["route"]
        return f'''openapi: "3.0.0"
info:
  title: {entity_plural.capitalize()} API
  version: "1.0.0"
  description: >
    API spec for the {entity_plural} service.
    NOTE: This spec has 3 errors. The Go server is the source of truth.

paths:
  {route}:
    get:
      summary: List {entity_plural}
      parameters:
        - name: page
          in: query
          schema:
            type: integer
      responses:
        "200":
          description: Paginated list of {entity_plural}
          content:
            application/json:
              schema:
                type: object
                properties:
                  results:
                    type: array
                    items:
                      $ref: "#/components/schemas/{entity_lower.capitalize()}"
                  cursor:
                    type: string
                  total:
                    type: integer
    post:
      summary: Create a {entity_lower}
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: "#/components/schemas/{entity_lower.capitalize()}"
      responses:
        "201":
          description: Created
        "400":
          description: Validation error
          content:
            application/json:
              schema:
                type: object
                properties:
                  error:
                    type: string

components:
  schemas:
    {entity_lower.capitalize()}:
      type: object
      properties:
        {spec_id}:
          type: integer
'''

    # ------------------------------------------------------------------
    # Test generators
    # ------------------------------------------------------------------

    def _conftest(self, d: dict) -> str:
        port = d["port"]
        name = d["name"]
        return f'''import subprocess
import time
import os
import signal
import pytest


@pytest.fixture(scope="session")
def go_server():
    """Build and start the Go server for integration tests."""
    workspace = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    server_dir = os.path.join(workspace, "service")
    binary = "/tmp/cross1_server_{name}"
    env = os.environ.copy()
    env["PORT"] = "{port}"

    # Build the server binary
    build = subprocess.run(
        ["go", "build", "-o", binary, "."],
        cwd=server_dir,
        capture_output=True,
        text=True,
    )
    if build.returncode != 0:
        pytest.skip(f"Go build failed: {{build.stderr}}")

    proc = subprocess.Popen(
        [binary],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    time.sleep(0.8)  # Wait for startup
    if proc.poll() is not None:
        pytest.skip("Go server failed to start")

    yield "http://localhost:{port}"

    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
'''

    def _test_integration(self, d: dict) -> str:
        entity = d["entity"]
        entity_plural = d["entity_plural"]
        spec_id = d["spec_id"]
        json_id = d["json_id"]
        return f'''import pytest
from client.api import APIClient


def test_list_{entity_plural}_returns_items(go_server):
    client = APIClient(go_server)
    items, cursor = client.list_{entity_plural}()
    assert len(items) > 0, "Expected at least one {d['entity_lower']} in response"


def test_list_{entity_plural}_id_is_set(go_server):
    client = APIClient(go_server)
    items, cursor = client.list_{entity_plural}()
    assert items[0].{spec_id} is not None, (
        f"Expected {{items[0].{spec_id}!r}} to be set — "
        "check that from_dict maps the correct camelCase key from the server"
    )
    assert items[0].{spec_id} > 0, "ID must be a positive integer"


def test_list_{entity_plural}_cursor_present(go_server):
    client = APIClient(go_server)
    items, cursor = client.list_{entity_plural}(page=1)
    assert cursor is not None, (
        "Pagination cursor must not be None — "
        "check that api.py reads the correct key from the server response"
    )
    assert len(cursor) > 0, "Pagination cursor must be non-empty"
'''

    def _test_pagination(self, d: dict) -> str:
        entity_plural = d["entity_plural"]
        return f'''import pytest
from client.api import APIClient


def test_pagination_page1(go_server):
    client = APIClient(go_server)
    items, cursor = client.list_{entity_plural}(page=1)
    assert cursor is not None, "page=1 must return a next cursor"
    assert cursor.startswith("cursor_"), f"Unexpected cursor format: {{cursor!r}}"


def test_pagination_page2(go_server):
    client = APIClient(go_server)
    items1, cursor1 = client.list_{entity_plural}(page=1)
    items2, cursor2 = client.list_{entity_plural}(page=2)
    assert cursor1 != cursor2, "Cursors for different pages must differ"


def test_list_returns_list(go_server):
    client = APIClient(go_server)
    items, cursor = client.list_{entity_plural}()
    assert isinstance(items, list), f"Expected list, got {{type(items).__name__}}"
'''

    def _test_errors(self, d: dict) -> str:
        entity_plural = d["entity_plural"]
        route = d["route"]
        # Build without f-string dict literals that contain colons to avoid
        # "Invalid format specifier" from Python's f-string parser.
        ct_header = '{"Content-Type": "application/json"}'
        errors_return = '{"errors": ["Invalid JSON body", "Request body required"]}'
        # Use plain string concat so we can write literal {go_server} without
        # f-string brace-escaping confusion.
        url1 = 'f"{go_server}' + route + '"'
        return (
            "import pytest\n"
            "import requests\n"
            "from client.api import APIClient\n"
            "from client.exceptions import APIError, parse_error_response\n"
            "\n"
            "\n"
            "def test_invalid_body_raises_api_error(go_server):\n"
            '    """Sending invalid JSON must raise APIError with status 422."""\n'
            "    with pytest.raises(APIError) as exc_info:\n"
            "        import requests as _req\n"
            "        resp = _req.post(\n"
            f"            {url1},\n"
            '            data="not-json",\n'
            f"            headers={ct_header},\n"
            "            timeout=10,\n"
            "        )\n"
            "        if resp.status_code >= 400:\n"
            "            raise parse_error_response(resp)\n"
            "    err = exc_info.value\n"
            "    assert err.status_code == 422, (\n"
            '        f"Expected status 422, got {err.status_code} -- "\n'
            '        "check that parse_error_response handles HTTP 422"\n'
            "    )\n"
            "\n"
            "\n"
            "def test_error_message_is_string(go_server):\n"
            '    """The error message extracted from the response must be a non-empty string."""\n'
            "    import requests as _req\n"
            "    resp = _req.post(\n"
            f"        {url1},\n"
            '        data="bad",\n'
            f"        headers={ct_header},\n"
            "        timeout=10,\n"
            "    )\n"
            '    assert resp.status_code == 422, f"Expected 422, got {resp.status_code}"\n'
            "    body = resp.json()\n"
            "    assert 'errors' in body, f\"Response missing 'errors' key: {body}\"\n"
            '    assert isinstance(body["errors"], list), "errors must be an array"\n'
            '    assert len(body["errors"]) > 0, "errors array must be non-empty"\n'
            "\n"
            "\n"
            "def test_parse_error_response_422():\n"
            '    """Unit test: parse_error_response must handle a 422 with errors array."""\n'
            "\n"
            "    class FakeResponse:\n"
            "        status_code = 422\n"
            "\n"
            "        def json(self):\n"
            f"            return {errors_return}\n"
            "\n"
            "    err = parse_error_response(FakeResponse())\n"
            "    assert err.status_code == 422\n"
            '    assert "Invalid JSON" in err.message or "body" in err.message.lower()\n'
        )
