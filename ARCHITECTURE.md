# Architecture

Technical decisions and rationale for Decoded.

## System overview

Decoded is a continuous-ingestion RAG system that pulls new AI/ML papers from
arXiv, enriches them with citation and community signals, parses their PDFs,
embeds them into two Qdrant collections, and generates multi-layer
human-readable "decoded" content per paper.

The system is a monorepo with a Python backend and a Next.js frontend
(Week 3+). All infrastructure runs locally via docker-compose during
development, moving to Fly.io + Neon + Upstash + Vercel in Week 6.

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
┌─────────────────────────────────────────────────────────────────────┐
│                          Decoding Engine                             │
├─────────────────────────────────────────────────────────────────────┤
│                                                                       │
│   Haiku ──▶ one_sentence, sixty_second      (abstract)               │
│   Sonnet ─▶ deep_dive                       (full paper)             │
│   Vision ─▶ figures                         (extracted images)       │
│   Haiku ──▶ vocabulary, analogies           (from deep_dive)         │
│                                                                       │
│   Real-time path: Instructor + Pydantic                              │
│   Bulk path:      Batch API, 50% cost                                │
│   Manual trigger only — no cron until Week 6                         │
│                                                                       │
└─────────────────────────────────────────────────────────────────────┘
                    │                             │
                    ▼                             ▼
    ┌───────────────────────────┐   ┌───────────────────────────────┐
    │  Evaluation harness       │   │  Public Site (Week 3)         │
    │  Golden set · metrics ·   │   │  Feed, paper pages, search    │
    │  judge · regression gate  │   │                               │
    └───────────────────────────┘   └───────────────────────────────┘
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
│       │   ├── decoding/       Schemas, prompts, generators, batch pipeline
│       │   └── flows/          Prefect orchestration
│       ├── evals/              Golden set, metrics, judge, regression gate
│       ├── scripts/            One-off smoke tests
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

| Collection        | Vectors per paper | Model                    | Dims | Use case                           |
| ----------------- | ----------------- | ------------------------ | ---- | ---------------------------------- |
| `paper_abstracts` | 1                 | `text-embedding-3-large` | 3072 | Feed search, "find papers about X" |
| `paper_chunks`    | 20-100            | `text-embedding-3-small` | 1536 | Fine-grained retrieval for RAG     |

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

| Table             | Purpose                                                        |
| ----------------- | -------------------------------------------------------------- |
| `papers`          | Primary entity. arXiv metadata + enrichment + pipeline status. |
| `authors`         | Deduplicated author records.                                   |
| `paper_authors`   | Many-to-many with author `position` on the paper.              |
| `topics`          | Slug-based topic labels (populated Week 5 via BERTopic).       |
| `paper_topics`    | Many-to-many with confidence score.                            |
| `parsed_contents` | 1:1 with papers. Full markdown + figures + equations.          |
| `ingestion_runs`  | Every pipeline run logged with counts, errors, duration.       |

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
{
  "event": "paper.upserted",
  "arxiv_id": "2401.12345",
  "title": "...",
  "timestamp": "..."
}
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

## Decoding engine

The signature feature. Every paper is turned into layered, human-readable
content. Six sections are implemented; each is generated independently, stored
independently, and evaluated independently.

### Section catalog

| Section        | Source material      | Model               | Stages       | Typical cost (real-time) |
| -------------- | -------------------- | ------------------- | ------------ | ------------------------ |
| `one_sentence` | Title + abstract     | Haiku 4.5           | 1            | $0.003                   |
| `sixty_second` | Title + abstract     | Haiku 4.5           | 1            | $0.005                   |
| `deep_dive`    | Full parsed markdown | Sonnet 4.6          | 1            | $0.179                   |
| `figures`      | Extracted PDF images | Sonnet 4.6 (Vision) | 1 per figure | $0.139                   |
| `vocabulary`   | `deep_dive` output   | Haiku 4.5           | 2            | $0.010                   |
| `analogies`    | `deep_dive` output   | Haiku 4.5           | 3            | $0.036                   |

Full real-time decode: **~$0.37/paper**. Via Batch API: **~$0.19/paper**.

`so_what` is schema'd but not yet generated — deferred to Week 4, where it
folds into the "Explain It Different" work.

### Storage model

One row per `(paper_id, section, schema_version, prompt_version)` in
`decoded_contents`, not one JSON blob per paper. That choice buys three things:

- **Partial regeneration.** Change the deep-dive prompt, regenerate only that section.
- **Independent evaluation.** Each section gets its own metrics without unpacking a monolith.
- **Side-by-side prompt versions.** v1 and v2 of the same section coexist, so a new prompt can be measured against the old one before switching.
  Each row carries full generation metadata inline: model, prompt version, input
  tokens, output tokens, cost in USD, latency. No separate audit table.

### Structured output

Pydantic models define every section's shape. Field descriptions are not
documentation — Instructor sends them to the model as part of the tool
definition, so a description like `"under 20 words, plain language, no jargon"`
is prompt engineering.

Validators enforce hard constraints. `OneSentence` rejects anything over 20
words; Instructor catches the `ValidationError`, feeds it back to the model as
a repair message, and retries. Two retries handle essentially every case.

### Multi-stage sections

`vocabulary` and `analogies` are not single calls:

- **Vocabulary** — stage 1 extracts technical terms from the deep dive; stage 2 defines each one, contextualized to this paper rather than generically.
- **Analogies** — stage 1 extracts core mechanisms worth explaining; stage 2 generates three candidate analogies per mechanism, each in a different everyday domain; stage 3 has an LLM judge pick the best one.
  Splitting stages beats one mega-prompt: each prompt does one job, and the
  failure modes stay isolated and diagnosable.

### Figure extraction

PyMuPDF pulls raster images out of the PDF in memory. Filters run before any
API call, because a logo costs the same to analyze as a real chart:

- Minimum 200×150 px (drops logos, watermarks, decorative marks)
- Maximum 5 MB per image (Anthropic's limit)
- Maximum 6 figures per paper (cost cap — covers the important figures for most papers)
- CMYK → RGB conversion (some academic PDFs embed CMYK, which the Vision API rejects)
  Each figure is sent to Claude Vision with the surrounding page text as context.
  Vision alone often misreads caption text in dense layouts; the page text fixes
  caption attribution and figure numbering.

Figures are not persisted. Bytes are extracted, sent, discarded. Storing them
in R2 for frontend display comes in Week 3.

### Batch API

Batch runs at 50% of standard rates with a 24-hour SLA (in practice, 2-4
minutes). Decoding is offline work — nobody waits on it — so the SLA costs
nothing.

Batch does not work with Instructor, which is built around a synchronous
request-response cycle. Batch splits that in half: build the request now, parse
the response later. So the pipeline does manually what Instructor does
internally:

- `pydantic_to_tool()` — Pydantic model → JSON schema → Anthropic tool definition
- `tool_choice: {"type": "tool", "name": ...}` — forces structured output, no prose preamble to strip
- `parse_tool_response()` — tool-use JSON → validated Pydantic
  `custom_id` must match `^[a-zA-Z0-9_-]{1,64}$`, so IDs are sanitized to
  `{arxiv_id}__{section}` with dots replaced. Results come back unordered and
  detached from context; the `custom_id` is the only link back to what was
  requested. Figures produce N requests per paper and are regrouped into a single
  section row before storage.

Batch latency is flat regardless of request count — 2 requests take about as
long as 200. Batching many papers at once is the whole point.

`vocabulary` and `analogies` stay on the real-time path. Their later stages
depend on earlier stages' output, which Batch can't express in a single
submission. Combined they cost $0.046; the complexity of chained batches isn't
worth it.

### Model routing

Haiku for extractive work (summarizing an abstract, pulling terms out of text).
Sonnet where the task needs judgment: weighing which results matter, finding
the paper's actual "aha," interpreting a chart.

Deep dive and figures are 85% of the cost. Any future cost work starts there —
capping figures at 3, or A/B testing Haiku on figures to see if quality holds.

### Context management

Deep dive sends the full parsed paper, not the abstract. Abstract-only decoding
forces the model to invent specifics it can't know.

`token_utils.py` budgets against a 180k ceiling (20k headroom on Sonnet's
200k), subtracting the system prompt, title, and abstract, then truncates the
body with an explicit `[TRUNCATED]` marker. A runaway 200-page appendix
degrades gracefully instead of throwing.

### Prompt caching

Implemented via `cache_control: {"type": "ephemeral"}` on the system block, but
**not currently activating** on this account. Verified with raw SDK calls at
2488 tokens (past Haiku's 2048 minimum) — Anthropic returns
`cache_read=0, cache_write=0` on every call.

The pattern is correct in code. Root cause is account- or model-side, not
implementation. Revisit in Week 6 when decode volume makes the savings
material. Expected savings when it works: ~90% on the system prompt portion of
each call.

## Evaluation

Reading output by hand doesn't scale and isn't reproducible. From Week 2
onward, changing a prompt requires proving it didn't make anything worse.

### Golden set

A versioned set of papers in `evals/golden/papers.json`, tagged by type
(empirical, theory, survey, benchmark, position). Type diversity matters
because each type fails differently — a survey has no results section, a
position paper has no method.

Target size is 15-30 papers. `evals/pick_golden.py` suggests candidates
diversified across arXiv categories.

### Three metric families

**Deterministic** (`evals/metrics/deterministic.py`) — 30+ checks, no LLM, free
and instant. Word counts, jargon blacklist, preamble detection, structural
completeness, Flesch-Kincaid readability, circular definitions, duplicate
terms, generic headings, AI-jargon contamination inside analogies. These catch
roughly 70% of real problems at zero cost.

**LLM-as-judge** (`evals/metrics/judge.py`) — runs on Haiku with structured
verdicts:

- _Faithfulness_ — counts supported vs unsupported claims against the source paper, returns a ratio. This is the only metric that catches hallucination.
- _Heading quality_ — 1-5 rubric penalizing generic section titles.
- _Analogy quality_ — 1-5 rubric penalizing shallow analogies and AI jargon used to explain AI.
  Ragas was evaluated and skipped. Its metrics assume a QA-over-retrieved-context
  shape that doesn't match multi-section generative decoding, and a purpose-built
  judge is cheaper and more legible.

**Cost and latency** — already recorded per section in `decoded_contents`, so
regressions in cost are visible alongside regressions in quality.

### Regression gate

`evals/gate.py` compares the current run against a committed baseline
(`evals/golden/baseline.json`) and fails on either condition:

- **Absolute floor breached** — e.g. `pass_rate < 0.70`, `faithfulness < 0.80`, judge scores `< 3.0`
- **Regression beyond tolerance** — a drop larger than 0.05 (or 0.3 on the 1-5 judge scale) versus baseline
  Improvements are reported but never block. Promoting a new baseline is an
  explicit action (`gate.py --promote`), so quality standards only move
  deliberately.

### CI

`.github/workflows/evals.yml` runs on any PR touching `decoding/` or `evals/`.
CI restores a SQL dump of the decoded golden set (`evals/golden/fixtures.sql`)
and runs deterministic metrics only — no API calls, so a PR costs nothing.
LLM-based metrics run locally before opening the PR.

## Cost discipline

Decoding is expensive (~$0.19-0.37 per paper × hundreds of papers/day). To
control cost during development:

- **No automatic decoding.** Manual CLI only, targeted by arXiv ID or `--top N`.
- **Small batch limits.** `parse_limit=5`, `embed_limit=10` while iterating.
- **Priority-scored ordering.** Whatever we do decode is the top-N by priority.
- **Batch API by default** for bulk work — half price for a latency we don't care about.
- **Figure cap at 6 per paper**, with size filtering before any Vision call.
- **Haiku for extractive sections**, Sonnet only where judgment is required.
  Production plan (Week 6): tier the decoding.

- Nightly job auto-decodes top ~10-20 papers/day (~$3-5/day fixed cost)
- On-demand decoding uses user credits (3/week free tier, unlimited on Pro)
- All decoded content cached publicly → every paid decode benefits the next visitor

## Key decisions

| Decision                | Chosen                                                                  | Alternative                        | Why                                                                               |
| ----------------------- | ----------------------------------------------------------------------- | ---------------------------------- | --------------------------------------------------------------------------------- |
| Repo structure          | Monorepo                                                                | Polyrepo                           | Shared types + atomic changes across backend/frontend/shared                      |
| Python ORM              | SQLAlchemy 2.x async                                                    | Raw SQL, Django ORM                | Standard for production Python, type-safe, migration story via Alembic            |
| DB driver               | asyncpg                                                                 | psycopg                            | Fastest async Postgres driver                                                     |
| Vector DB               | Qdrant                                                                  | pgvector, Pinecone, Weaviate       | Scales past pgvector; standard in senior AI Eng roles; no vendor lock-in          |
| Embedding models        | `text-embedding-3-large` (abstracts), `text-embedding-3-small` (chunks) | One model for both                 | Different retrieval quality needs; cost of chunks dominates                       |
| Chunker                 | Section-aware with sliding-window fallback                              | Fixed-size                         | Preserves semantic coherence; cleaner embeddings                                  |
| PDF parser              | LlamaParse                                                              | PyMuPDF, Nougat, Docling           | Best out-of-box for academic PDFs; router leaves room for others                  |
| Rate limiter (arXiv)    | Client-side sleep                                                       | none, exponential backoff only     | arXiv explicitly requests 1 req/3s; being a good citizen                          |
| Enrichment fan-out      | `asyncio.gather` + `_safe` wrapper                                      | Sequential calls                   | Latency = slowest call, not sum; one API down doesn't kill enrichment             |
| Priority scoring        | Pure function combining 4 signals                                       | Hardcoded thresholds, ML model     | Testable, tunable without pipeline changes; ML overkill for MVP                   |
| Idempotency             | UNIQUE `arxiv_id` + `ON CONFLICT DO NOTHING`; UUID5 point IDs in Qdrant | Check-then-insert                  | Correct under race conditions, cheaper                                            |
| Logging                 | structlog (JSON)                                                        | stdlib logging                     | Machine-parseable, aggregator-ready                                               |
| Orchestration           | Prefect 3                                                               | cron, Celery, Airflow, Dagster     | Modern DX, free tier, UI-first, native async                                      |
| Secrets                 | Env vars via `pydantic-settings` (dev), Prefect Blocks (prod)           | .env files scattered               | Single source of truth per environment                                            |
| Decoded content storage | One row per section, versioned by schema + prompt                       | Single JSON blob per paper         | Partial regeneration, independent evaluation, A/B prompt versions                 |
| Structured LLM output   | Instructor + Pydantic (real-time), raw tool schemas (batch)             | Raw JSON parsing, regex extraction | Validation and retry for free; descriptions double as prompt engineering          |
| Decoder model routing   | Haiku for extractive, Sonnet for judgment                               | One model everywhere               | 10x cost difference; extractive tasks don't need Sonnet's reasoning               |
| Deep dive context       | Full parsed paper                                                       | Abstract only, RAG within paper    | Cross-section reasoning needs the whole document; abstract-only invents specifics |
| Bulk decoding           | Anthropic Batch API                                                     | Real-time for everything           | 50% cost cut for a 24h SLA we don't care about                                    |
| Multi-stage sections    | Vocabulary (2 stages), analogies (3 stages with judge)                  | One mega-prompt per section        | Each prompt does one job; failure modes stay isolated                             |
| Figure extraction       | PyMuPDF in-memory, size-filtered, capped at 6                           | Docling, store all figures         | Zero storage cost; filters drop logos before paying for Vision                    |
| Eval metrics            | Custom deterministic + purpose-built LLM judge                          | Ragas, DeepEval, promptfoo         | Ragas assumes QA-over-context shape; custom judge is cheaper and more legible     |
| Eval gate               | Absolute floors + regression tolerance vs committed baseline            | Manual review, floors only         | Catches slow drift that per-run review misses                                     |
| CI eval strategy        | SQL fixtures + deterministic metrics only                               | Regenerate golden set per PR       | Zero API cost per PR; LLM metrics run locally before opening                      |

## Roadmap

- ~~**Week 1** — Continuous ingestion (arXiv → enrichment → parsing → embedding), Prefect orchestration~~ **done**
- ~~**Week 2** — Decoding engine (6 sections, Batch API, Claude Vision), evaluation harness with regression gate~~ **done**
- **Week 3** — Next.js 15 frontend, Clerk auth, Cohere Rerank, SEO, Langfuse observability
- **Week 4** — "Explain It Different" (6 modes: math/analogy/story/diagram/code/standard), DSPy prompt compilation, MLflow experiment tracking
- **Week 5** — Field Pulse dashboards, BERTopic clustering, weekly email digest
- **Week 6** — Podcast mode (ElevenLabs), production deploy, launch

## What's not built yet (intentional)

- **`so_what` section** — schema'd but not generated; folds into Week 4
- **Auth / users** — Week 3
- **Rate limiting** — Week 3
- **Semantic caching** — Week 3
- **Retrieval reranker** — Week 3 (Cohere Rerank v3)
- **Langfuse tracing** — Week 3, when real user requests exist to trace
- **Figure storage (R2)** — Week 3, when the frontend needs to display them
- **DSPy optimization** — Week 4
- **MLflow experiment tracking** — Week 4, when prompt variants outgrow JSON files
- **Nightly auto-decode job** — Week 6, when there's a product to serve
- **Analytics** — Week 5 (PostHog)
- **Voice** — Week 6
- **Kubernetes** — deferred, may or may not happen depending on scale

## Known issues

- **Prompt caching not activating.** Implementation is correct and verified against the raw SDK at 2488 tokens; Anthropic returns zero cache tokens regardless. Account- or model-side. Revisit Week 6.
- **Batch figure results incomplete.** Early runs returned 1 of 6 figures. Root cause was `max_length=800` on `FigureExplained.plain_language` rejecting longer explanations during validation. Limit raised to 2000; needs a confirming regeneration.
- **Golden set undersized.** Currently 1 paper. `pass_rate` is not meaningful until 8+ papers of mixed type are in the set.
