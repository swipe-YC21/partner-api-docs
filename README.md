# Swipe Partner API Documentation

Source for [developers.getswipe.in](https://developers.getswipe.in/) — the developer documentation for the Swipe Partner API, built with [Mintlify](https://mintlify.com).

## Repo layout

- `docs.json` — site configuration (navigation, versions, theme, contextual menu)
- `*.mdx` — guide pages (Introduction, Document, Customer, Payment, Product, Subscriptions, EwayBill, E-Invoices, Webhooks)
- `api-reference/openapi.json` — the OpenAPI spec; the single source of truth for all endpoint pages
- `api-reference/**/*.mdx` — generated endpoint pages, one per operation, referencing the spec via `openapi:` frontmatter
- `images/`, `logo/` — static assets

## Local development

Install the Mintlify CLI and run the dev server from the repo root (where `docs.json` lives):

```
npm i -g mint
mint dev
```

## Checking for broken links

Run this before pushing — it validates all relative internal links:

```
mint broken-links
```

Internal links must be root-relative (`/api-reference/...`), never absolute (`https://developers.getswipe.in/...`), so the link checker can validate them.

## Updating the API reference

Edit `api-reference/openapi.json` (endpoint summaries, descriptions, fields, examples), then regenerate pages for any new endpoints:

```
npx @mintlify/scraping@latest openapi-file ./api-reference/openapi.json -o api-reference
```

Add any newly generated pages to the navigation in `docs.json` — pages not listed there are orphaned but still publicly served.

When making an API-visible change, add an entry to `api-reference/change-log.mdx`.

## Publishing

Changes merged to `main` deploy automatically via the Mintlify GitHub App.
