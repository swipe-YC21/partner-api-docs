#!/usr/bin/env python3
"""Push api-reference/openapi.json to the Postman spec (Spec Hub).

Usage:
    POSTMAN_API_KEY=pmak-... python3 push_postman.py [--discover] [--spec PATH]

--discover  List the specs in the workspace and store the chosen spec id in
            postman.json (run this once; picks automatically when there is
            exactly one spec).
--spec      Path of the OpenAPI file to push
            (default: api-reference/openapi.json at the repo root).

Reads POSTMAN_API_KEY from the environment. Non-secret ids (workspace, spec,
file path) live in postman.json next to this script.
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[3]
CONFIG_PATH = HERE / "postman.json"
BASE = "https://api.postman.com"


def api(method, path, key, body=None):
    req = urllib.request.Request(
        BASE + path,
        method=method,
        headers={
            "X-Api-Key": key,
            "Content-Type": "application/json",
            # Cloudflare fronts api.postman.com and rejects urllib's default
            # signature with 403 error code 1010.
            "User-Agent": "swipe-docs-sync/1.0",
        },
        data=json.dumps(body).encode() if body is not None else None,
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")[:500]
        return e.code, {"error": detail}


def load_config():
    return json.loads(CONFIG_PATH.read_text()) if CONFIG_PATH.exists() else {}


def save_config(cfg):
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2) + "\n")


def discover(key, cfg):
    ws = cfg["workspace_id"]
    status, data = api("GET", f"/specs?workspaceId={ws}", key)
    if status != 200:
        sys.exit(f"GET /specs failed ({status}): {data}")
    specs = data.get("specs") or data.get("data") or []
    if not specs:
        sys.exit("No specs found in the workspace — create one in Postman "
                 "(Specs > Create) and re-run.")
    print("Specs in workspace:")
    for s in specs:
        print(f"  {s.get('id')}  {s.get('name')}  ({s.get('type', '?')})")
    if len(specs) == 1:
        cfg["spec_id"] = specs[0]["id"]
        save_config(cfg)
        print(f"Stored spec_id={cfg['spec_id']} in {CONFIG_PATH.name}")
    else:
        sys.exit("Multiple specs — put the right id into "
                 f"{CONFIG_PATH} as \"spec_id\" and re-run.")
    return cfg


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--discover", action="store_true")
    ap.add_argument("--update-collection", action="store_true",
                    help="Also overwrite the public collection from the spec "
                         "(replaces any manual edits made to it in Postman)")
    ap.add_argument("--spec", default=str(REPO_ROOT / "api-reference" / "openapi.json"))
    args = ap.parse_args()

    key = os.environ.get("POSTMAN_API_KEY", "").strip().strip('"').strip("'")
    if not key:
        sys.exit("Set POSTMAN_API_KEY (create one at "
                 "https://web.postman.co/settings/me/api-keys).")
    print(f"Using API key {key[:9]}... (length {len(key)})")
    if not key.startswith("PMAK-"):
        print("WARNING: Postman personal API keys start with 'PMAK-'. "
              "This doesn't look like one — collection access keys or "
              "workspace keys won't work here.")

    # Preflight: verify the key itself before touching specs.
    status, data = api("GET", "/me", key)
    if status != 200:
        sys.exit(f"The key was rejected by GET /me ({status}): {data}\n"
                 "Fix: create a Personal API key at "
                 "https://web.postman.co/settings/me/api-keys using the "
                 "Postman account that owns the Swipe workspace, and make "
                 "sure the full key is exported (no quotes, no truncation).")
    user = data.get("user", {})
    print(f"Authenticated as: {user.get('username') or user.get('email') or user.get('id')}")

    cfg = load_config()
    if "workspace_id" not in cfg:
        sys.exit(f"{CONFIG_PATH} must contain workspace_id.")

    if args.discover or not cfg.get("spec_id"):
        cfg = discover(key, cfg)

    spec_id = cfg["spec_id"]
    content = Path(args.spec).read_text()
    json.loads(content)  # refuse to push invalid JSON

    # Find the file path inside the spec (a spec holds one or more files).
    file_path = cfg.get("file_path")
    if not file_path:
        status, data = api("GET", f"/specs/{spec_id}/files", key)
        if status != 200:
            sys.exit(f"GET /specs/{spec_id}/files failed ({status}): {data}")
        files = data.get("files") or data.get("data") or []
        if not files:
            sys.exit("Spec has no files — add one in Postman first.")
        file_path = files[0].get("path") or files[0].get("name")
        cfg["file_path"] = file_path
        save_config(cfg)
        print(f"Using spec file: {file_path}")

    # Update the file content (PUT is documented; retry as PATCH if rejected).
    for method in ("PUT", "PATCH"):
        status, data = api(method, f"/specs/{spec_id}/files/{file_path}", key,
                           {"content": content})
        if status in (200, 201, 204):
            print(f"Pushed {args.spec} -> Postman spec {spec_id} ({file_path}) "
                  f"via {method} [{status}]")
            break
        if status not in (404, 405):
            sys.exit(f"{method} spec file failed ({status}): {data}")
    else:
        sys.exit(f"Could not update spec file (last: {status} {data})")

    if args.update_collection:
        update_collection(key, cfg, args.spec)
    else:
        print("Spec pushed. Postman offers no API for the spec->collection "
              "'Update' sync (UI-only), so either click Update in Postman when "
              "you want the collection refreshed, or run with "
              "--update-collection to overwrite the collection directly "
              "(discards any manual edits made to it in Postman).")


def update_collection(key, cfg, spec_path):
    """Convert the OpenAPI spec to a Postman collection and PUT it over the
    public collection. Fully automatic, but machine-owns the collection:
    manual edits made in Postman are overwritten."""
    import subprocess, tempfile

    uid = cfg.get("collection_uid")
    if not uid:
        sys.exit("postman.json needs collection_uid for --update-collection.")

    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tf:
        out_path = tf.name
    r = subprocess.run(
        ["npx", "--yes", "openapi-to-postmanv2", "-s", spec_path, "-o", out_path,
         "-p", "-O", "folderStrategy=Tags,requestParametersResolution=Example"],
        capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f"openapi-to-postmanv2 failed:\n{r.stdout}\n{r.stderr}")
    converted = json.loads(Path(out_path).read_text())
    # CLI output is the collection itself, or a list of {collection: ...}
    if isinstance(converted, list):
        converted = converted[0]
    collection = converted.get("collection", converted)

    # Keep the public collection's existing display name.
    status, data = api("GET", f"/collections/{uid}", key)
    if status == 200:
        current_name = data.get("collection", {}).get("info", {}).get("name")
        if current_name:
            collection.setdefault("info", {})["name"] = current_name
    else:
        print(f"warning: could not read current collection ({status}); "
              "keeping converter's name")

    status, data = api("PUT", f"/collections/{uid}", key, {"collection": collection})
    if status == 200:
        print(f"Collection {uid} updated from the spec — no manual clicks needed.")
    else:
        sys.exit(f"PUT /collections/{uid} failed ({status}): {str(data)[:400]}")


if __name__ == "__main__":
    main()
