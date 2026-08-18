# Architecture

Technical decisions and rationale for Decoded.

## System overview

Decoded is a continuous-ingestion RAG system that pulls new AI/ML papers from
arXiv, enriches them with citation and community signals, parses their PDFs,
embeds them into two Qdrant collections, and (starting Week 2) generates
multi-layer human-readable "decoded" content per paper.

The system is designed as a monorepo with a Python backend (this week) and a
Next.js frontend (Week 3+). All infrastructure runs locally via docker-compose
during development, moving to Fly.io + Neon + Upstash + Vercel in Week 6.

```
┌─────────────────────────────────────────────────────────────────────┐
│                      Continuous Ingestion (Prefect)                  │
├─────────────────────────────────────────────────────────────────────┤
│                                                                       │
│  arXiv API ──▶ Postgres ──▶ Enrichment ──▶ Parsing ──▶ Embedding    │
│  (hourly)      (papers)     (OpenAlex,      (LlamaParse) (Qdrant)   │
│                              S2, HN)                                  │
│                                                                       │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
                    ┌───────────────────────────────┐
                    │  Decoding Engine (Week 2)     │
                    │  Manual per-paper, no cron.   │
                    └───────────────────────────────┘
                                    │
                                    ▼
                    ┌───────────────────────────────┐
                    │  Public Site (Week 3)         │
                    │  Feed, paper pages, search    │
                    └───────────────────────────────┘
```

## Repository structure

Monorepo with app-scoped configuration:

```
decoded/
├── apps/
│   └── api/                    Python backend
│       ├── pyproject.toml      Poetry manages this app
│       ├── src/decoded/        Package code
│       │   ├── cli/            Manual CLIs for each stage
│       │   ├── db/             SQLAlchemy models + repositories
│       │   ├── ingestion/      arXiv poller, enricher, scoring
│       │   ├── external/       Third-party API clients
│       │   ├── parsing/        PDF parser abstraction + LlamaParse
│       │   ├── embeddings/     Qdrant setup, chunker, OpenAI client
│       │   └── flows/          Prefect orchestration
│       └── migrations/         Alembic
├── infra/
│   └── compose.yaml            docker-compose (postgres + qdrant + redis)
├── packages/
│   └── shared/                 Shared types (used by frontend, Week 3+)
└── ARCHITECTURE.md             This file
```

Monorepo chosen over polyrepo because backend + frontend + shared types will
evolve together. Changes to a data shape become one atomic commit, not three
PRs across three repos.

Each app owns its own `pyproject.toml` / `package.json` so tooling stays clean.
Adding a Next.js frontend in Week 3 requires no restructuring.

## Data pipeline (offline)

### Sources

- **arXiv API** — primary source. Categories: `cs.AI`, `cs.CL`, `cs.LG`, `cs.CV`. Rate limit: 1 request per 3 seconds (self-enforced).
- **OpenAlex API** — 200M+ works, citation graph, author affiliations. Free, no key. Email in User-Agent header enters the "polite pool" for higher rate limits.
- **Semantic Scholar API** — pre-generated TL;DRs, influence scores. Aggressively rate-limited without an API key; treated as optional.
- **HN Algolia API** — search Hacker News for paper mentions and upvote counts. Free, no key, no rate limit worth worrying about.

### Poller (`ingestion/arxiv_poller.py`)

- Queries arXiv every hour for papers submitted in the last N hours (default 2)
- Uses the `arxiv` Python library (thin wrapper over the API)
- Sorts by submission date descending, stops as soon as it sees a paper older than the lookback window
- Idempotent upsert on `arxiv_id` (UNIQUE) via `ON CONFLICT DO NOTHING`
- Strips the version suffix (`v1`, `v2`, etc.) so re-submitted papers dedupe
- Logs each run to the `ingestion_runs` table with counts and error samples

### Enricher (`ingestion/enricher.py`)

For each paper with `status=FETCHED`, fires 3 API calls in parallel:

```python
await asyncio.gather(
    openalex.get_by_arxiv_id(id),
    semantic_scholar.get_by_arxiv_id(id),
    hn.search_mentions(id, title),
)
```

Wrapped in a `_safe(coro, source)` helper so one API failing doesn't kill the
whole enrichment. Merges results into the paper's structured columns
(`citation_count`, `hn_mentions`) and free-form `extra` JSONB.

### Priority scorer (`ingestion/scoring.py`)

Pure function that combines all enrichment signals into a single 0-10 score:

- Citations: log-scaled, max 4 points (10 citations = 1, 100 = 2, 1000 = 3)
- HN upvotes: log-scaled, max 3 points
- Top-lab affiliation (Google, DeepMind, OpenAI, Anthropic, etc.): flat +2
- Semantic Scholar TL;DR available: +0.5

Deterministic, testable in isolation, easy to retune without touching the pipeline.

### Parser (`parsing/`)

Abstract base class `BaseParser` returns `ParseResult(markdown, figures, equations, parse_ms)`.

Three planned implementations, chosen by a router based on paper features:

- **LlamaParse** — cloud API, best general-purpose (current MVP)
- **Nougat** — Meta's LaTeX-aware parser for math-heavy papers (deferred)
- **Docling** — IBM's layout-preserving parser for figure/table-heavy papers (deferred)

Router is in place with hooks for future parsers. Zero-effort to add one later
without touching the ingestion pipeline.

Downloaded PDFs are parsed in-memory, never written to disk. Result stored as
markdown in `parsed_contents.markdown` for downstream chunking.

### Embedder (`embeddings/`)

Two Qdrant collections:

| Collection | Vectors per paper | Model | Dims | Use case |
|---|---|---|---|---|
| `paper_abstracts` | 1 | `text-embedding-3-large` | 3072 | Feed search, "find papers about X" |
| `paper_chunks` | 20-100 | `text-embedding-3-small` | 1536 | Fine-grained retrieval for RAG |

Two collections because they answer different questions and need different
retrieval quality. Abstract search is coarse-grained (find the right paper).
Chunk search is fine-grained (find the exact paragraph that answers the question).

**Section-aware chunker** splits markdown by `## Section` headers first. Sections
under the token limit stay whole. Oversized sections slice with sliding window
(500 target tokens, 50 overlap). Cuts never spill across section boundaries.
Better embeddings, better retrieval, better citations.

**Deterministic point IDs** (UUID5 of `arxiv_id` + `chunk_order`) so re-embedding
overwrites cleanly instead of duplicating.

**Payload indexes** on `arxiv_id`, `paper_id`, `published_at`, `categories`
for fast filtering at query time.

## Storage layer

### Postgres (via SQLAlchemy 2.x + Alembic)

Async engine (`asyncpg` driver). All access via repositories in `db/repositories/`.
Never raw SQL scattered through business logic.

Tables:

| Table | Purpose |
|---|---|
| `papers` | Primary entity. arXiv metadata + enrichment + pipeline status. |
| `authors` | Deduplicated author records. |
| `paper_authors` | Many-to-many with author `position` on the paper. |
| `topics` | Slug-based topic labels (populated Week 5 via BERTopic). |
| `paper_topics` | Many-to-many with confidence score. |
| `parsed_contents` | 1:1 with papers. Full markdown + figures + equations. |
| `ingestion_runs` | Every pipeline run logged with counts, errors, duration. |

Pipeline state is a single enum column on `papers.status`:
`PENDING → FETCHED → ENRICHED → PARSED → EMBEDDED → DECODED → FAILED`.

Each stage queries `WHERE status = 'PREVIOUS_STAGE'` and updates on success.
Simple, resumable, no lock contention.

### Qdrant

Standalone vector DB (not pgvector). Chosen because:

- Better performance at 100k+ vectors (expected corpus size)
- Native hybrid search (dense + sparse in one query)
- Rich payload filtering, indexed
- Standard in production AI Eng roles

pgvector is fine for IBS/CBS scale (a few thousand chunks). Decoded outgrows it fast.

### Redis (Upstash in prod)

- Response cache for the API (Week 3+)
- Rate limiting per user (Week 3+)
- Prefect worker heartbeats (if we switch to Prefect Cloud managed pools)

Not used heavily yet.

## Observability

### Structured logging (`structlog`)

Every log line is JSON:

```json
{"event": "paper.upserted", "arxiv_id": "2401.12345", "title": "...", "timestamp": "..."}
```

Machine-parseable. Grep-able. Ready for a log aggregator later (Grafana Loki
in Week 8).

### Ingestion runs table

Every pipeline stage logs to `ingestion_runs`: source, status, papers_found,
papers_new, errors, duration. One query gives you a full audit trail:

```sql
SELECT source, status, papers_found, papers_new, errors,
       finished_at - started_at AS duration
FROM ingestion_runs
ORDER BY started_at DESC LIMIT 20;
```

## Orchestration (`flows/pipeline.py`)

Prefect 3.x flow wraps the four CLI stages as retryable tasks:

- `arxiv-poll` — 3 retries, 30s/2m/10m backoff, 30-min cache to prevent accidental double-polling
- `enrich-papers` — 2 retries, 60s/5m backoff
- `parse-papers` — 2 retries, gated on `LLAMA_CLOUD_API_KEY`
- `embed-papers` — 2 retries, gated on `OPENAI_API_KEY`

Flow runs sequentially: each stage only starts if the previous finished. Failure
in one stage doesn't stop the others (parse failure still lets embed catch up
later runs).

**Scheduling** is deferred to Week 6 (deploy). Current state: flow deployed to
Prefect but not scheduled. Runs triggered manually while developing to avoid
running up LLM costs before there's a product to serve.

## Async everywhere

Every I/O operation is async:

- FastAPI routes (already async by default)
- SQLAlchemy 2.x with `AsyncSession` and `asyncpg`
- OpenAI SDK (`AsyncOpenAI`)
- Anthropic SDK (`AsyncAnthropic`) — used starting Week 2
- Qdrant client (`AsyncQdrantClient`)
- HTTP requests (`httpx.AsyncClient`)
- Redis (`redis.asyncio`)

The app is I/O-bound (99% of time waiting on Postgres, Qdrant, OpenAI, arXiv).
Sync would require 100x more worker processes to serve the same concurrency.

Discipline: if it does I/O, it's `async`. One accidental blocking call kills
concurrency for the whole request.

## Cost discipline

Decoding is expensive (~$0.05-0.30 per paper × hundreds of papers/day). To
control cost during development:

- **No automatic decoding.** Manual CLI only, one paper at a time by ID.
- **Small batch limits.** `parse_limit=5`, `embed_limit=10` while iterating.
- **Priority-scored ordering.** Whatever we do decode is the top-N by priority.

Production plan (Week 6): tier the decoding.

- Nightly job auto-decodes top ~10-20 papers/day (~$3-5/day fixed cost)
- On-demand decoding uses user credits (3/week free tier, unlimited on Pro)
- All decoded content cached publicly → every paid decode benefits the next visitor

## Key decisions

| Decision | Chosen | Alternative | Why |
|---|---|---|---|
| Repo structure | Monorepo | Polyrepo | Shared types + atomic changes across backend/frontend/shared |
| Python ORM | SQLAlchemy 2.x async | Raw SQL, Django ORM | Standard for production Python, type-safe, migration story via Alembic |
| DB driver | asyncpg | psycopg | Fastest async Postgres driver |
| Vector DB | Qdrant | pgvector, Pinecone, Weaviate | Scales past pgvector; standard in senior AI Eng roles; no vendor lock-in |
| Embedding models | `text-embedding-3-large` (abstracts), `text-embedding-3-small` (chunks) | One model for both | Different retrieval quality needs; cost of chunks dominates |
| Chunker | Section-aware with sliding-window fallback | Fixed-size | Preserves semantic coherence; cleaner embeddings |
| PDF parser | LlamaParse | PyMuPDF, Nougat, Docling | Best out-of-box for academic PDFs; router leaves room for others |
| Rate limiter (arXiv) | Client-side sleep | none, exponential backoff only | arXiv explicitly requests 1 req/3s; being a good citizen |
| Enrichment fan-out | `asyncio.gather` + `_safe` wrapper | Sequential calls | Latency = slowest call, not sum; one API down doesn't kill enrichment |
| Priority scoring | Pure function combining 4 signals | Hardcoded thresholds, ML model | Testable, tunable without pipeline changes; ML overkill for MVP |
| Idempotency | UNIQUE `arxiv_id` + `ON CONFLICT DO NOTHING`; UUID5 point IDs in Qdrant | Check-then-insert | Correct under race conditions, cheaper |
| Logging | structlog (JSON) | stdlib logging | Machine-parseable, aggregator-ready |
| Orchestration | Prefect 3 | cron, Celery, Airflow, Dagster | Modern DX, free tier, UI-first, native async |
| Secrets | Env vars via `pydantic-settings` (dev), Prefect Blocks (prod) | .env files scattered | Single source of truth per environment |

## Roadmap

- **Week 2** — Decoding engine (7 sections per paper, Anthropic Batch API, Prompt Caching, DSPy, Claude Vision)
- **Week 3** — Next.js 15 frontend, Clerk auth, Cohere Rerank, SEO
- **Week 4** — "Explain It Different" (6 modes: math/analogy/story/diagram/code/standard)
- **Week 5** — Field Pulse dashboards, BERTopic clustering, weekly email digest
- **Week 6** — Podcast mode (ElevenLabs), production deploy, launch

## What's not built yet (intentional)

- **Auth / users** — Week 3
- **Rate limiting** — Week 3
- **Semantic caching** — Week 3
- **Retrieval reranker** — Week 3 (Cohere Rerank v3)
- **DSPy optimization** — Week 4
- **Analytics** — Week 5 (PostHog)
- **Voice** — Week 6
- **Kubernetes** — deferred, may or may not happen depending on scale
