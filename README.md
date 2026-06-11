# TPE Judicial Fulltext API

Railway fallback service for TPE Radar's 司法院裁判書全文查詢.

Used when Cloudflare Worker's MCP path fails (e.g., old cases not in MCP corpus).

## Endpoint

```
POST /api/legal/fulltext
Content-Type: application/json

{"case_number": "臺灣高等法院114年度抗字第2234號"}
```

## Architecture

```
Frontend → Cloudflare Worker (tries MCP first, ~fast)
                            → MCP timeout? → Railway (Playwright, ~10s)
```

## Deploy

Connect this repo to [Railway](https://railway.app) — auto-deploys on push.
