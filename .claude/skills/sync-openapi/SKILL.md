---
name: sync-openapi
description: Regenerate api-reference/openapi.json from the backend's flask_restx schema. Use whenever the backend API changes, when asked to sync/update/regenerate the OpenAPI spec or schema, or when the docs spec drifts from the live API. Converts the backend's Swagger 2.0 output to OpenAPI 3.0.1 and applies the docs overlay (hidden endpoints, description fill-ins, summary casing).
---

# Sync the OpenAPI spec from the backend

The Swipe backend (`vectorx-automated-erp`, flask_restx in `services/api/src/partner/`)
serves its schema as **Swagger 2.0** at `https://app.getswipe.in/api/partner/swagger.json`.
The docs need **OpenAPI 3.0.1**. Never hand-edit the version field or paste the raw
swagger output into `api-reference/openapi.json` — run the converter.

## Steps

1. Run the converter from the repo root:

   ```bash
   python3 .claude/skills/sync-openapi/scripts/convert.py
   ```

   - Default source is the live schema URL. To convert from a local backend instead,
     pass a URL or file path, e.g.
     `python3 .claude/skills/sync-openapi/scripts/convert.py http://localhost:5000/partner/swagger.json`
   - Output goes to `api-reference/openapi.json`.

2. Read the script's report and act on it:
   - **Paths added** → each new endpoint needs an MDX page under `api-reference/`
     (frontmatter `openapi: <method> <path>`), a nav entry in `docs.json`, and a
     changelog entry in `api-reference/change-log.mdx`.
   - **Paths removed** → remove the corresponding MDX pages and nav entries, and add
     a redirect in `docs.json` from the old page URL to its closest replacement.
   - **Operations without description** → best fixed in the backend (the flask_restx
     docstring body below the summary line becomes the description). For a docs-only
     fix, add the operation to `api-reference/spec-overlay.json` under `operations`.

3. Review `git diff api-reference/openapi.json` — the diff should reflect actual
   backend changes, nothing else.

4. Verify: `npx --yes mint@latest broken-links` must pass. Do not commit or push —
   leave changes for review.

5. **Postman**: the same spec lives in Postman's Spec Hub (workspace and ids in
   `scripts/postman.json`). It syncs automatically — a push to `main` that touches
   `api-reference/openapi.json` triggers `.github/workflows/postman-sync.yml`,
   which runs `scripts/push_postman.py` using the `POSTMAN_API_KEY` repo secret.
   To push manually instead:

   ```bash
   POSTMAN_API_KEY=pmak-... python3 .claude/skills/sync-openapi/scripts/push_postman.py
   ```

   First-time setup: run with `--discover` once to resolve and store the spec id,
   and add `POSTMAN_API_KEY` as a GitHub Actions secret. The script never stores
   the key; it only reads the environment.

   CI also passes `--update-collection`, which converts the spec with
   `openapi-to-postmanv2` and PUTs it over the public "Run in Postman"
   collection (uid in `scripts/postman.json`). The collection is **purely
   generated — never hand-edit it in Postman**; every sync overwrites it.
   Postman's spec→collection "Update" button has no public API, which is why
   the collection is written directly.

## The overlay (`api-reference/spec-overlay.json`)

Applied automatically by the converter, after conversion:

- `exclude_path_prefixes` — stripped from the public spec no matter what the backend
  serves (currently `/v2/expense`: live routes, intentionally undocumented; the
  backend also hides them via `doc=False`, this is the docs-side belt-and-braces).
- `summaries` — exact-match renames normalizing title casing.
- `operations` — descriptions keyed by `"METHOD /path"`, filled in **only when the
  backend operation has no description**. Once a description is added to the backend
  docstring, it wins; the overlay entry can then be deleted.

## Conversion details (what the script handles)

`swagger: 2.0` → `openapi: 3.0.1`, `basePath` → `servers` (fixed to
`https://app.getswipe.in/api/partner`), flask_restx's apiKey Authorization header →
proper `bearerAuth` http/bearer security scheme, `definitions` →
`components.schemas` with `$ref` rewriting, body params → `requestBody`,
formData → form/multipart `requestBody`, response `schema` → per-content-type
`content` (file responses become empty `content`, matching the PDF endpoints).
