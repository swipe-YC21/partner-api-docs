# Swipe Partner API Docs — Agent Guide

Mintlify documentation for the Swipe Partner API, published at
**https://developers.getswipe.in**. Pushing to `main` auto-deploys via the
Mintlify GitHub App — treat every push as a production deploy.

## Golden rules

1. **Do not commit or push unless explicitly asked.** Make changes, verify
   locally, and leave the working tree for review.
2. **Never hand-edit `api-reference/openapi.json`.** It is generated — see
   "Spec pipeline" below. Content fixes belong in the backend or the overlay.
3. **Verify locally before finishing**: `npx --yes mint@latest broken-links`
   must pass, `docs.json` must be valid JSON, and for content changes run the
   dev server (`npx --yes mint@latest dev`, port 3000; a preview config exists
   in `.claude/launch.json`) and check the changed pages render.
4. Every `.mdx` file is publicly served **even if it's not in the nav** —
   never leave orphaned pages. When deleting or renaming a page, add a
   redirect in `docs.json`.

## Repo map

| Path | What it is |
| ---- | ---------- |
| `docs.json` | Site config: nav (versions v2 / v1-deprecated), redirects, contextual menu, playground languages (`defaults: required`), feedback, SEO |
| `*.mdx` (root) | Get Started pages (introduction, quickstart, authentication, api-conventions, build-with-ai) and Guides (document, customer, vendor, payment, product, inventory, subscriptions, ewaybills, einvoices, webhooks) |
| `api-reference/*.mdx` | Resources: error-codes, tax-codes, reference-data, change-log |
| `api-reference/<group>/*.mdx` | Endpoint pages — frontmatter `openapi: <method> <path>` only, plus at most a short `<Note>` |
| `api-reference/openapi.json` | **Generated** OpenAPI 3.0.1 spec — the source for all endpoint pages and the playground |
| `api-reference/spec-overlay.json` | Docs-side overlay applied during generation (see below) |
| `.claude/skills/sync-openapi/` | The generator: skill instructions + `scripts/convert.py` |
| `images/screenshots/` | Dashboard screenshots embedded in guides via `<Frame>` |

## Spec pipeline (important)

The backend (`vectorx-automated-erp` repo, flask_restx code in
`services/api/src/partner/`) serves **Swagger 2.0** at
`https://app.getswipe.in/api/partner/swagger.json` (fetch with a non-default
User-Agent; plain urllib gets a Cloudflare 403). To update the docs spec:

```bash
python3 .claude/skills/sync-openapi/scripts/convert.py
```

This converts to OpenAPI 3.0.1 and applies `spec-overlay.json`:

- `exclude_path_prefixes` — `/v2/expense` is intentionally undocumented
  (live routes, hidden with `doc=False` in the backend too).
- `operations` — endpoint descriptions, applied **only when the backend
  operation has none**. The long-term home for these is the backend
  docstring body (first line = summary, rest = description); each one moved
  there can be deleted from the overlay.
- The converter also garbage-collects unreferenced schemas and reports
  added/removed paths. New paths need an MDX page, a nav entry, and a
  changelog entry; removed paths need page deletion + a redirect.

**Backend gotcha**: flask_restx registers swagger models in a global registry
keyed by name. Two models with the same name silently overwrite each other and
corrupt the generated schema (this happened; all names were de-duplicated on
2026-08-26 — v1 copies got a `V1` suffix, vendor copies a `Vendor` prefix).
When adding backend models, keep names globally unique.

## Content conventions

- Every page needs frontmatter: `title`, `description`, and `icon`
  (FontAwesome name). Descriptions feed SEO and `llms.txt`.
- Internal links are **root-relative** (`/api-reference/...`), never absolute
  `https://developers.getswipe.in/...` — the link checker only validates
  relative links. CI runs it on every PR (`.github/workflows/broken-links.yml`).
- Guide pages follow a template: what the resource is → lifecycle (Mermaid
  where useful) → one minimal real payload in a `<CodeGroup>`
  (cURL / Python / JavaScript) → gotchas as callouts → dashboard screenshot in
  `<Frame>` → `<CardGroup>` of endpoint links.
- Any API-visible change gets an entry in `api-reference/change-log.mdx`
  (dated `<Update>` component, text not screenshots).
- Sidebar group names have no version suffix ("Documents", not "Document V2").

## API facts (verified — don't contradict these)

- Base URL: `https://app.getswipe.in/api/partner`; auth is
  `Authorization: Bearer <API key>`.
- **API keys are company-scoped.** Docs recommend creating a separate test
  company for experimentation (guide:
  https://community.getswipe.in/t/how-to-add-new-company-on-web/1191).
- **Rate limit: 1 request/second** (confirmed by the team). The status code
  returned when exceeded is unconfirmed — don't invent a 429.
- All dates are `DD-MM-YYYY`. Responses use the envelope
  `{success, message, error_code, errors, data}`; business errors → HTTP 400,
  auth → 401, unexpected → 500.
- Documents are addressed by the `hash_id` returned at creation.
  Subscriptions are created via `POST /v2/doc` with
  `document_type=subscription` — there is no separate create endpoint.
- Two MCP servers exist: `https://app.getswipe.in/api/mcp/sse` (self-hosted,
  OAuth OTP + company selection, ~26 tools; source in the backend repo at
  `services/api/src/mcp_server/`) and `https://developers.getswipe.in/mcp`
  (Mintlify-hosted docs search, free). Both documented on `/build-with-ai`.
- The site is on Mintlify's free tier: the paid Assistant ("Ask AI") and
  personalization (playground key-prefill) are **not** available — don't
  reference them as existing features.

## Known open items

- The webhook response-timeout value (10s) and the currency-table corrections
  (Zimbabwe ZWL, Bosnia BAM, Palestine) still need backend confirmation.
- Analytics integration in `docs.json` is pending a GA4/PostHog ID.
- Expense endpoints stay hidden until the team decides to publish them; when
  that happens, remove `doc=False` in the backend, drop the overlay exclusion,
  regenerate, and build an "Expenses" group with pages + nav + changelog.
