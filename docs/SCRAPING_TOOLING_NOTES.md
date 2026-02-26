# Scraping Tooling Notes (Feb 2026)

This note captures external recommendations for Python/Rust scraping stacks and how they map to ZHC-Nova priorities.

## Observed Tool Leaders

- Python: `Scrapy`, `Playwright (python)`, `Firecrawl`, `Scrapling`, `ScrapeGraphAI`.
- Rust: `spider-rs/spider`, `reqwest + scraper` stack, `Firecrawl` Rust SDK.

## ZHC-Nova Position

- We are still in control-plane hardening and operational reliability mode.
- Scraping framework expansion should not bypass existing gate flow (`plan -> review -> approve -> resume`).
- For now, browser automation pilot (`agent-browser`) remains the primary integration track.

## Recommended Adoption Order

1. Keep scraping frameworks on watchlist while finishing reliability closeout metrics.
2. Run scoped browser-data pilot using existing `agent-browser` controls and domain allowlists.
3. If broader crawling is required, start with Python `Scrapy + scrapy-playwright` for maintainability.
4. Add Rust crawler lane (`spider`) only when throughput/latency constraints justify extra complexity.

## Non-Goals (for now)

- No broad anti-bot escalation work in core runtime.
- No multi-framework scraping mesh.
- No direct deployment of scraping tools outside approval-policy gates.
