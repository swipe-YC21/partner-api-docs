#!/usr/bin/env python3
"""Convert the flask_restx Swagger 2.0 schema to OpenAPI 3.0.1 for the docs.

Usage:
    python3 convert.py [SOURCE] [-o OUTPUT]

SOURCE   URL or file path of the Swagger 2.0 schema.
         Default: https://app.getswipe.in/api/partner/swagger.json
OUTPUT   Where to write the OpenAPI 3.0.1 JSON.
         Default: api-reference/openapi.json (relative to the repo root)

The script also applies api-reference/spec-overlay.json:
  - exclude_path_prefixes: paths stripped from the public spec
  - summaries: exact-match summary renames (casing normalization)
  - operations: descriptions filled in ONLY where the backend provides none
"""

import argparse
import json
import sys
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
DEFAULT_SOURCE = "https://app.getswipe.in/api/partner/swagger.json"
DEFAULT_OUTPUT = REPO_ROOT / "api-reference" / "openapi.json"
OVERLAY_PATH = REPO_ROOT / "api-reference" / "spec-overlay.json"
SERVER_URL = "https://app.getswipe.in/api/partner"

HTTP_METHODS = {"get", "post", "put", "delete", "patch", "options", "head"}


def load_source(source: str) -> dict:
    if source.startswith("http://") or source.startswith("https://"):
        # A plain urllib UA gets 403'd by Cloudflare in front of app.getswipe.in
        req = urllib.request.Request(source, headers={"User-Agent": "swipe-docs-sync/1.0"})
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.load(r)
    return json.loads(Path(source).read_text())


def rewrite_refs(obj):
    """#/definitions/X -> #/components/schemas/X, recursively."""
    if isinstance(obj, dict):
        return {
            k: (v.replace("#/definitions/", "#/components/schemas/")
                if k == "$ref" and isinstance(v, str) else rewrite_refs(v))
            for k, v in obj.items()
        }
    if isinstance(obj, list):
        return [rewrite_refs(v) for v in obj]
    return obj


PARAM_SCHEMA_KEYS = (
    "type", "format", "enum", "default", "minimum", "maximum", "minLength",
    "maxLength", "pattern", "items", "uniqueItems", "multipleOf",
    "exclusiveMinimum", "exclusiveMaximum",
)


def convert_parameter(p: dict):
    """Convert a non-body Swagger 2.0 parameter to OpenAPI 3.0."""
    out = {k: p[k] for k in ("name", "in", "description", "required") if k in p}
    schema = {k: p[k] for k in PARAM_SCHEMA_KEYS if k in p}
    if p.get("collectionFormat") == "multi":
        out["explode"] = True
        out["style"] = "form"
    if schema:
        out["schema"] = schema
    return out


def convert_operation(op: dict, consumes: list, produces: list):
    new = {k: v for k, v in op.items()
           if k not in ("parameters", "responses", "consumes", "produces")}
    consumes = op.get("consumes", consumes) or ["application/json"]
    produces = op.get("produces", produces) or ["application/json"]

    params, body, form = [], None, []
    for p in op.get("parameters", []):
        if p.get("in") == "body":
            body = p
        elif p.get("in") == "formData":
            form.append(p)
        else:
            params.append(convert_parameter(p))
    if params:
        new["parameters"] = params

    if body is not None:
        rb = {"content": {ct: {"schema": body.get("schema", {})} for ct in consumes}}
        if body.get("description"):
            rb["description"] = body["description"]
        if body.get("required"):
            rb["required"] = True
        new["requestBody"] = rb
    elif form:
        props, required, has_file = {}, [], False
        for p in form:
            prop = {k: p[k] for k in PARAM_SCHEMA_KEYS if k in p}
            if prop.get("type") == "file":
                prop = {"type": "string", "format": "binary"}
                has_file = True
            if prop.get("type") == "array" and prop.get("items", {}).get("type") == "file":
                prop["items"] = {"type": "string", "format": "binary"}
                has_file = True
            if p.get("description"):
                prop["description"] = p["description"]
            if p.get("required"):
                required.append(p["name"])
            props[p["name"]] = prop
        schema = {"type": "object", "properties": props}
        if required:
            schema["required"] = required
        ct = "multipart/form-data" if has_file else "application/x-www-form-urlencoded"
        new["requestBody"] = {"content": {ct: {"schema": schema}}}

    responses = {}
    for code, resp in op.get("responses", {}).items():
        r = {k: v for k, v in resp.items() if k not in ("schema", "headers")}
        r.setdefault("description", "")
        if "headers" in resp:
            r["headers"] = {
                name: {"description": h.get("description", ""),
                       "schema": {k: h[k] for k in PARAM_SCHEMA_KEYS if k in h}}
                for name, h in resp["headers"].items()
            }
        schema = resp.get("schema")
        if schema is not None:
            if schema.get("type") == "file":
                r["content"] = {}
            else:
                r["content"] = {ct: {"schema": schema} for ct in produces
                                if ct != "application/octet-stream"} or \
                               {"application/json": {"schema": schema}}
        responses[str(code)] = r
    new["responses"] = responses or {"200": {"description": "Success"}}
    return new


def convert(spec2: dict) -> dict:
    if spec2.get("swagger") != "2.0":
        sys.exit(f"Source is not Swagger 2.0 (got: {spec2.get('swagger') or spec2.get('openapi')})")

    out = {
        "openapi": "3.0.1",
        "info": spec2.get("info", {}),
        "servers": [{"url": SERVER_URL}],
        "security": [{"bearerAuth": []}],
        "paths": {},
        "components": {
            "securitySchemes": {
                "bearerAuth": {
                    "type": "http",
                    "scheme": "bearer",
                    "bearerFormat": "JWT",
                    "description": "Bearer authentication header of the form "
                                   "Bearer <token>, where <token> is your auth token.",
                }
            },
            "schemas": rewrite_refs(spec2.get("definitions", {})),
        },
    }

    consumes = spec2.get("consumes", ["application/json"])
    produces = spec2.get("produces", ["application/json"])
    for path, item in spec2.get("paths", {}).items():
        shared_params = [convert_parameter(p) for p in item.get("parameters", [])
                         if p.get("in") != "body"]
        new_item = {}
        if shared_params:
            new_item["parameters"] = shared_params
        for m, op in item.items():
            if m in HTTP_METHODS and isinstance(op, dict):
                new_item[m] = convert_operation(rewrite_refs(op), consumes, produces)
        out["paths"][path] = new_item
    return out


def apply_overlay(spec3: dict, overlay: dict):
    stripped, filled, renamed = [], 0, 0
    for prefix in overlay.get("exclude_path_prefixes", []):
        for path in [p for p in spec3["paths"] if p.startswith(prefix)]:
            del spec3["paths"][path]
            stripped.append(path)
    summaries = overlay.get("summaries", {})
    op_overlays = overlay.get("operations", {})
    for path, item in spec3["paths"].items():
        for m, op in item.items():
            if m not in HTTP_METHODS or not isinstance(op, dict):
                continue
            if op.get("summary") in summaries:
                op["summary"] = summaries[op["summary"]]
                renamed += 1
            key = f"{m.upper()} {path}"
            entry = op_overlays.get(key, {})
            if not op.get("description") and entry.get("description"):
                op["description"] = entry["description"]
                filled += 1
            if not op.get("summary") and entry.get("summary"):
                op["summary"] = entry["summary"]
    return stripped, filled, renamed


def gc_schemas(spec3: dict):
    """Drop component schemas not reachable from any path (e.g. models of
    excluded endpoints)."""
    schemas = spec3["components"]["schemas"]
    reachable, queue = set(), []

    def scan(obj):
        if isinstance(obj, dict):
            ref = obj.get("$ref")
            if isinstance(ref, str) and ref.startswith("#/components/schemas/"):
                name = ref.split("/")[-1]
                if name not in reachable:
                    reachable.add(name)
                    queue.append(name)
            for v in obj.values():
                scan(v)
        elif isinstance(obj, list):
            for v in obj:
                scan(v)

    scan(spec3["paths"])
    while queue:
        name = queue.pop()
        if name in schemas:
            scan(schemas[name])
    dropped = sorted(set(schemas) - reachable)
    for name in dropped:
        del schemas[name]
    return dropped


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("source", nargs="?", default=DEFAULT_SOURCE)
    ap.add_argument("-o", "--output", default=str(DEFAULT_OUTPUT))
    args = ap.parse_args()

    spec2 = load_source(args.source)
    spec3 = convert(spec2)

    overlay = json.loads(OVERLAY_PATH.read_text()) if OVERLAY_PATH.exists() else {}
    stripped, filled, renamed = apply_overlay(spec3, overlay)
    dropped = gc_schemas(spec3)

    out_path = Path(args.output)
    old_paths = set()
    if out_path.exists():
        try:
            old_paths = set(json.loads(out_path.read_text()).get("paths", {}))
        except json.JSONDecodeError:
            pass

    out_path.write_text(json.dumps(spec3, indent=2, ensure_ascii=False) + "\n")

    new_paths = set(spec3["paths"])
    no_desc = [f"{m.upper()} {p}" for p, item in spec3["paths"].items()
               for m, op in item.items()
               if m in HTTP_METHODS and isinstance(op, dict) and not op.get("description")]

    print(f"wrote {out_path} ({len(new_paths)} paths)")
    print(f"overlay: stripped {stripped or 'nothing'}, "
          f"filled {filled} descriptions, renamed {renamed} summaries")
    if dropped:
        print(f"dropped unreferenced schemas: {dropped}")
    if old_paths:
        added, removed = sorted(new_paths - old_paths), sorted(old_paths - new_paths)
        print(f"paths added vs previous spec: {added or 'none'}")
        print(f"paths removed vs previous spec: {removed or 'none'}")
        if added:
            print("NOTE: new paths need MDX pages + docs.json nav entries "
                  "+ a changelog entry.")
    if no_desc:
        print(f"WARNING: {len(no_desc)} operations have no description: {no_desc}")


if __name__ == "__main__":
    main()
