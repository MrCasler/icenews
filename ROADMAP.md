# ICENews Roadmap

This roadmap is optimized for “**online-ready quickly**” while meeting a government-grade standard of predictability and safety.

Guiding rule: **make it correct → make it observable → make it deployable**.

---

## Current state (today)

- Ingestion from X via Scrapfly works and writes to SQLite (`icenews_social.db`).
- FastAPI dashboard renders `/` and exposes `GET /api/posts` and `GET /api/accounts`.
- Security tests exist (`tests/test_security.py`).
- There are known UX bugs around **initial posts rendering** and **post action buttons**.

---

## User stories (M0: Local demo stable)

### Feed correctness
- **US-Feed-01**: As a viewer, I open `/` and see the latest posts immediately (no manual refresh).
  - Acceptance: posts appear on first load; refresh button still works.
- **US-Feed-02**: As a viewer, I can filter by category and see matching posts.

### Post actions (must be reliable)
- **US-Post-01**: As a viewer, I can open a post on X (card click + explicit link).
- **US-Post-02**: As a viewer, I can share a post and get feedback (native share or clipboard).
- **US-Post-03**: As a viewer, I can like/unlike a post and see a **global** like count.

### Analytics (prod-only)
- **US-Analytics-01**: As an operator, I can see Umami events for:
  - `open_post`, `share`, `like`, `unlike`, `filter_change`

---

## Milestones

### M0 — Local demo stable (now)
**Goal**: dashboard behaves correctly every time.

Deliverables:
- Fix initial render and actions with runtime evidence (no “it seems…”)
- Add smoke tests for core endpoints and homepage render
- Document setup/run instructions (`README.md`)

### M1 — Ingestion + scheduler stable
**Goal**: predictable ingestion cost and reliable operation.

Deliverables:
- `ICENEWS_MAX_TWEETS_PER_ACCOUNT=4` enforced per run
- Scheduler every 6 hours, clear logs on success/failure
- Simple backup strategy for `icenews_social.db`

### M2 — Deploy safely (public internet)
**Goal**: `https://icenews.eu` online with minimal attack surface.

Deliverables:
- VM + Docker + Caddy (automatic Let’s Encrypt HTTPS)
- Read-only password gate enabled by default
- Reverse proxy rate limiting
- Operator runbook (`RUNBOOK.md`)

### M3 — Monitoring + maintenance
**Goal**: operational clarity and easy iteration.

Deliverables:
- Umami dashboards for engagement
- Error reporting basics (structured logs, ingestion success metrics)
- “Add accounts” workflow (weekly list updates)

---

## Risks / constraints

- **Scrapfly credits**: ingestion frequency and per-run tweet limit drive cost.
- **Public exposure**: without auth/rate limiting, you invite scraping + abuse.
- **SQLite**: fine for now, but ensure single-writer discipline (scheduler writes; web reads).

