"""
TPE Judicial Fulltext API
Minimal FastAPI service for 司法院裁判書全文擷取 via Playwright.
Deployed on Railway as fallback when Cloudflare Worker MCP fails.

POST /api/legal/fulltext  { "case_number": "臺灣..." }
GET  /health
"""
import asyncio
import re
import time
from contextlib import asynccontextmanager
from typing import Optional
from urllib.parse import unquote

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# ── Cache (in-memory, resets on restart) ──────────────────────────────────────
_cache: dict = {}

# ── Models ────────────────────────────────────────────────────────────────────
class FulltextRequest(BaseModel):
    case_number: str


# ── Case number parser ─────────────────────────────────────────────────────────
def parse_case_number(raw: str) -> dict:
    raw = raw.strip()
    court_m = re.match(r'^(.+?法院)', raw)
    year_m  = re.search(r'(\d+)\s*年度', raw)
    type_m  = re.search(r'年度\S*?(\S+?)字第', raw)
    num_m   = re.search(r'第\s*(\d+)\s*號', raw)
    return {
        "court":    court_m.group(1) if court_m else "",
        "year":     year_m.group(1)  if year_m  else "",
        "case_type":type_m.group(1)  if type_m  else "",
        "number":   num_m.group(1)   if num_m   else "",
        "judgment_type": "刑事" if "刑事" in raw else ("民事" if "民事" in raw else ""),
        "raw": raw,
    }


def search_query(parsed: dict) -> str:
    if parsed["year"] and parsed["case_type"] and parsed["number"]:
        return f"{parsed['year']}年度{parsed['case_type']}字第{parsed['number']}號"
    return parsed["raw"]


def link_matches(text: str, parsed: dict) -> bool:
    court_short = (parsed["court"]
                   .replace("臺灣","").replace("地方法院","").replace("台灣",""))
    return (
        parsed["year"] in text and
        parsed["case_type"] in text and
        parsed["number"] in text and
        (not court_short or court_short in text or parsed["court"] in text)
    )


# ── Playwright scraper ─────────────────────────────────────────────────────────
async def _playwright_fetch(case_number: str) -> dict:
    from playwright.async_api import async_playwright

    parsed = parse_case_number(case_number)
    kw = search_query(parsed)
    t0 = time.time()

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"]
        )
        try:
            page = await browser.new_page()
            page.set_default_timeout(20000)

            await page.goto("https://judgment.judicial.gov.tw/FJUD/default.aspx")
            await page.wait_for_load_state("domcontentloaded")
            await page.fill("input[name='txtKW']", kw)
            await page.locator("input[type='submit']").first.click()
            await page.wait_for_timeout(3500)

            result_url = await page.evaluate("""
                () => Array.from(document.querySelectorAll('a'))
                    .find(a => a.href.includes('qryresultlst'))?.href
            """)
            if not result_url:
                return {"error": f"司法院查無結果：{case_number}"}

            await page.goto(result_url)
            await page.wait_for_timeout(3000)

            links = await page.evaluate("""
                () => Array.from(document.querySelectorAll('a'))
                    .map(a => ({text: a.innerText.trim(), href: a.href}))
                    .filter(a => a.href.includes('data.aspx'))
            """)

            # Best match: court + year + type + number; prefer 判決 over 裁定
            candidates = [l for l in links if link_matches(l["text"], parsed)]
            if not candidates:
                candidates = [l for l in links
                              if (parsed["year"] in l["text"] and
                                  parsed["case_type"] in l["text"] and
                                  parsed["number"] in l["text"])]
            if not candidates:
                return {"error": f"找不到符合案件：{case_number}，搜尋到 {len(links)} 筆"}

            prefer_judgment = "判決" in case_number
            candidates.sort(key=lambda l: 0 if (prefer_judgment and "判決" in l["text"]) else 1)
            target = candidates[0]

            await page.goto(target["href"])
            await page.wait_for_timeout(2500)

            title = await page.title()
            full_text = await page.evaluate("""
                () => {
                    for (const sel of ['.text-pre','.jud','.htmlcontent','#divContent']) {
                        const el = document.querySelector(sel);
                        if (el && el.innerText.trim().length > 100) return el.innerText.trim();
                    }
                    return document.body.innerText.trim();
                }
            """)

            jid_m = re.search(r'id=([^&]+)', page.url)
            jid = unquote(jid_m.group(1)) if jid_m else ""

            return {
                "case_number":   case_number,
                "title":         title,
                "court":         parsed["court"],
                "year":          parsed["year"],
                "case_type":     parsed["case_type"],
                "number":        parsed["number"],
                "judgment_type": parsed["judgment_type"],
                "jfull":         full_text,
                "jid":           jid,
                "source_url":    page.url,
                "char_count":    len(full_text),
                "_source":       "railway-playwright",
                "_elapsed":      round(time.time() - t0, 2),
            }
        finally:
            await browser.close()


# ── FastAPI app ────────────────────────────────────────────────────────────────
app = FastAPI(title="TPE Judicial Fulltext API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "ok", "service": "tpe-judicial-api"}


@app.post("/api/legal/fulltext")
async def get_fulltext(req: FulltextRequest):
    key = req.case_number.strip()
    if not key:
        raise HTTPException(status_code=422, detail="case_number is required")

    if key in _cache:
        return {**_cache[key], "cached": True}

    result = await _playwright_fetch(key)

    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])

    _cache[key] = result
    return result
