# Architecture

Technical decisions and rationale for Decoded.

## System overview

Decoded is a continuous-ingestion RAG system that pulls new AI/ML papers from
arXiv, enriches them with citation and community signals, parses their PDFs,
embeds them into two Qdrant collections, generates multi-layer human-readable
"decoded" content per paper, and serves it as a public, search-indexable site
with five on-demand explanation modes behind a credit system.

The system is a monorepo: FastAPI backend, Next.js 15 frontend. Local
development runs on docker-compose; production runs on Vercel + Neon + Qdrant
Cloud, with the API moving to Fly.io in Week 6.

```
OFFLINE — runs on a schedule, nobody is waiting
┌─────────────────────────────────────────────────────────────────────┐
│                      Continuous Ingestion (Prefect)                  │
├─────────────────────────────────────────────────────────────────────┤
│  arXiv API ──▶ Postgres ──▶ Enrichment ──▶ Parsing ──▶ Embedding    │
│  (hourly)      (papers)     (OpenAlex,     (LlamaParse)  (Qdrant)   │
│                              S2, HN)                                 │
└─────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    Decoding Engine — 6 sections                      │
├─────────────────────────────────────────────────────────────────────┤
│   Haiku ──▶ one_sentence, sixty_second      (abstract)               │
│   Sonnet ─▶ deep_dive                       (full paper)             │
│   Vision ─▶ figures                         (extracted images)       │
│   Haiku ──▶ vocabulary, analogies           (from deep_dive)         │
│                                                                      │
│   Bulk path: Batch API, 50% cost · Manual trigger until Week 6       │
└─────────────────────────────────────────────────────────────────────┘
                   │                              │
                   ▼                              │
   ┌───────────────────────────────┐              │
   │  Evaluation + experiments     │              │
   │  Golden set · deterministic   │              │
   │  checks · judges · gate       │              │
   │  MLflow · DSPy optimization   │              │
   └───────────────────────────────┘              │
                                                  │
ONLINE — runs per request, someone is waiting     │
┌─────────────────────────────────────────────────┼───────────────────┐
│                                                 ▼                    │
│   Next.js (Vercel)                        FastAPI                    │
│   ├─ /            feed, ISR 5min    ◀──▶  GET  /v1/papers           │
│   ├─ /paper/[id]  ISR 1h, JSON-LD,  ◀──▶  GET  /v1/papers/{id}      │
│   │               OG image, modes    ◀──▶  GET  /v1/papers/{id}/modes│
│   │                                  ◀──▶  POST .../modes/{m}/generate│
│   ├─ /search      dynamic           ◀──▶  GET  /v1/search           │
│   └─ /library     auth-guarded      ◀──▶  GET  /v1/me/*             │
│                                                                      │
│   Every request: Redis cache → rate limit → Postgres / Qdrant        │
│   Every LLM call and search traced to Langfuse                       │
└──────────────────────────────────────────────────────────────────────┘
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│              Explanation Modes — on demand, credit-metered           │
├─────────────────────────────────────────────────────────────────────┤
│   Sonnet ─▶ math, code                      (full paper)             │
│   Sonnet ─▶ story, diagram                  (from deep_dive)         │
│   Luna ───▶ analogy                         (from deep_dive)         │
│                                                                      │
│   Atomic claim → spend credit → background task → client polls       │
│   Cache hit is free and permanent, for every later visitor           │
└─────────────────────────────────────────────────────────────────────┘
```

## Repository structure

Monorepo with app-scoped configuration:

```
decoded/
├── apps/
│   ├── api/                    Python backend
│   │   ├── pyproject.toml      Poetry manages this app
│   │   ├── src/decoded/        Package code
│   │   │   ├── api/            FastAPI routers + response schemas + deps
│   │   │   ├── auth/           Clerk JWT verification, user resolution
│   │   │   ├── cache/          Redis client, rate limiting
│   │   │   ├── cli/            Manual CLIs for each stage
│   │   │   ├── db/             SQLAlchemy models + repositories
│   │   │   ├── decoding/       Schemas, prompts, generators, batch pipeline
│   │   │   ├── embeddings/     Qdrant setup, chunker, OpenAI client
│   │   │   ├── external/       Third-party API clients
│   │   │   ├── flows/          Prefect orchestration
│   │   │   ├── ingestion/      arXiv poller, enricher, scoring
│   │   │   ├── modes/          Explanation modes: schemas, prompts, generator
│   │   │   ├── observability/  Langfuse tracing, MLflow experiments
│   │   │   ├── parsing/        PDF parser abstraction + LlamaParse
│   │   │   └── search/         Retrieval engine + Cohere reranker
│   │   ├── evals/              Golden set, metrics, judge, regression gate
│   │   ├── optimization/       DSPy programs, metrics, compiled artefacts
│   │   ├── scripts/            One-off smoke tests
│   │   └── migrations/         Alembic
│   └── web/                    Next.js 15 frontend
│       ├── package.json
│       └── src/
│           ├── app/            App Router pages, OG images, sitemap, robots
│           ├── components/     Feed, paper sections, search, modes, auth
│           ├── lib/            API client, formatters, decoded and mode types
│           ├── types/          Generated from the FastAPI OpenAPI spec
│           └── proxy.ts        Clerk middleware + /api rewrite
├── infra/
│   └── compose.yaml            docker-compose (postgres + qdrant + redis)
├── packages/
│   └── shared/                 Generated API types (see note below)
└── ARCHITECTURE.md             This file
```

Monorepo chosen over polyrepo because backend and frontend evolve together.
Changes to a data shape become one atomic commit, not two PRs across two repos.

Each app owns its own `pyproject.toml` / `package.json` so tooling stays clean.

**Note on `packages/shared`:** generated types currently live in
`apps/web/src/types/api.ts` rather than being imported from `packages/shared`.
Vercel deploys `apps/web` in isolation, so a relative import reaching outside
that directory fails at build time. Making `packages/shared` a real npm
workspace is deferred to Week 6 alongside the Fly.io deploy. The generator
script keeps the file in sync either way, which was the point.

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

### Langfuse (`observability/tracing.py`)

Structured logs answer "what happened." Langfuse answers "what did the model
actually see, and what did it cost." Once real users arrive, the questions
change shape: a user complains about one bad deep dive, and you need the exact
prompt and response for that request — not a SQL query across a cost column.

Two primitives wrap the Langfuse SDK:

- `trace_span(name, ...)` — context manager around a unit of work. Used on `decode_paper` and `search`.
- `record_generation(...)` — one LLM call, with model, token usage, cost, and latency. Langfuse treats generations differently from spans: it groups by model and aggregates cost automatically.

**Graceful degradation is the design constraint.** If `LANGFUSE_PUBLIC_KEY` is
absent, `init_tracing()` logs once and every call becomes a no-op through
`_NoOpSpan`. Every SDK call is individually wrapped in try/except. Observability
failing must never fail a request — the whole point is watching the system, not
becoming a dependency of it.

CLIs call `init_tracing()` and `flush()` explicitly, because they don't go
through the FastAPI lifespan. Langfuse batches events, so without an explicit
flush a short-lived process exits before anything is sent.

The Langfuse SDK API changed substantially between v2 and v4 (`trace()` and
`generation()` became `start_observation(as_type=...)`). The wrapper isolates
that: a version bump touches one file.

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

| Section | Source material | Model | Stages | Typical cost (real-time) |
|---|---|---|---|---|
| `one_sentence` | Title + abstract | Haiku 4.5 | 1 | $0.003 |
| `sixty_second` | Title + abstract | Haiku 4.5 | 1 | $0.005 |
| `deep_dive` | Full parsed markdown | Sonnet 4.6 | 1 | $0.179 |
| `figures` | Extracted PDF images | Sonnet 4.6 (Vision) | 1 per figure | $0.139 |
| `vocabulary` | `deep_dive` output | Haiku 4.5 | 2 | $0.010 |
| `analogies` | `deep_dive` output | Haiku 4.5 | 3 | $0.036 |

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

## Explanation modes

The signature feature. Five ways to understand the same paper: `math`,
`analogy`, `story`, `diagram`, `code`.

These differ from the six decoded sections in a way that changes the
architecture. Sections are generated in bulk and served to everyone. Modes are
generated **on demand**, because nobody wants all five — an engineer wants math
and code, a journalist wants story. Generating every mode for every paper would
be mostly waste.

That makes the design cache-first, asynchronous, and credit-metered.

### Source and model routing

| Mode | Source material | Model | Why |
|---|---|---|---|
| `math` | Full parsed paper | Sonnet | Equations live in the body, not the abstract |
| `analogy` | Deep dive | GPT-5.6 Luna | Creative work over already-clean text |
| `story` | Deep dive | Sonnet | Chronological reasoning across cited work |
| `diagram` | Deep dive | Sonnet | Valid Mermaid demands structural precision |
| `code` | Full parsed paper | Sonnet | The algorithm is in the method section |

`analogy` runs on OpenAI rather than Anthropic. At $0.20/$1.20 per million
tokens, Luna is roughly 5× cheaper on input than Haiku, and analogy generation
over pre-cleaned text is the one mode where the cheaper model holds quality.
The generator holds two clients and routes per mode; if `OPENAI_API_KEY` is
absent, everything falls back to Anthropic.

Every mode receives the deep dive even when the full paper is also sent. The
deep dive is already distilled and structured — it costs few extra tokens and
anchors the generation in the paper's main narrative before the model wades
into raw PDF text.

### Per-mode schemas

Each mode has its own Pydantic model rather than a generic `content: str`.
`math` returns a list of equations, each with LaTeX, a plain-language reading,
a symbol glossary, and why it matters. `diagram` returns Mermaid source plus a
typed diagram kind, caption, and step-by-step walkthrough. `analogy` returns
explicit mapping pairs and a `where_it_breaks` field.

Structure in the schema is structure in the UI: the frontend knows `equations`
is a list to render individually through KaTeX, that `mermaid` is source to
hand to a renderer, that `mapping` is pairs to display side by side. A generic
string would throw all of that away.

Two schemas carry validators that strip markdown fences — models wrap code and
Mermaid in triple backticks reflexively, and it breaks both renderers.

### Atomic claim

Two users clicking the same mode on the same paper at the same moment is a real
race. Check-then-insert means both see "not present," both generate, and the
bill is doubled.

`ExplanationModesRepository.claim()` uses `ON CONFLICT DO NOTHING` on the
`(paper_id, mode, schema_version, prompt_version)` constraint. The insert is
atomic in the database: one caller gets the row and `is_new_claim=True`, the
other gets `False` and waits. The loser also increments `request_count`, which
accumulates demand data — after a month, which modes get asked for and on which
papers, and therefore which papers are worth pre-generating.

### Asynchronous generation

The first implementation was synchronous: POST, wait 20-60 seconds, get the
content. It broke immediately with `socket hang up` — Next.js's dev proxy times
out well before that, and Vercel's hobby tier caps at 60 seconds. No timeout
setting fixes a request that is fundamentally too long for the transport.

The current flow:

```
POST /modes/{mode}/generate
  ├─ cached and ready?  → return content, no charge
  ├─ already generating? → return status, no charge
  └─ otherwise           → spend credit, schedule background task,
                           return status=generating + poll_after_ms
                                        │
GET /modes/{mode}  ← client polls every 3s until status changes
```

The background task runs on its own database session — the request session is
already closed by then — and handles refunds for both failure and exception.

This is what the atomic claim was built for. The POST returns in milliseconds
and the transport never sees a long-lived request.

### Mermaid validation

Mermaid has a cruel property: one wrong character inside a node label breaks the
entire diagram. `A[Sample (temp=0.9)]` fails to parse, and models write that
constantly because it is how a person would write it.

`modes/mermaid.py` checks for the failures that actually occur — problem
characters inside labels, missing or invalid header, zero edges, too few nodes —
and `sanitize()` strips the offending characters automatically. The detail that
gets cut lands in the `walkthrough`, which is free text.

The Pydantic schema guarantees a string under 4000 characters. It cannot
guarantee the string renders. Validating server-side turns a visible failure —
after the user already spent a credit — into a silent correction.

Critically, the evaluation harness runs the **same** validator. If they diverged,
a diagram could pass the gate and break on screen.

## Credits

`credits_remaining` sat unused on the user table since Week 3. Week 4 gave it a
job.

**Free tier:** 3 on-demand generations per week, reset on a rolling window.
**Pro:** unlimited, logged to the ledger with `delta: 0` so usage is still
visible.

### The compounding mechanic

**Cache hits never charge.** The first user to request a mode pays for it;
everyone after reads it free. This aligns three things at once: the business
model, the mission, and SEO. Each credit spent creates a permanent public
artefact — one more page of original content for Google to index.

### Append-only ledger

`credit_ledger` records every movement: spend, weekly reset, refund, with the
reason, the paper, the mode, and the resulting balance.

A bare `credits_remaining` column answers "how many are left" and nothing else.
When a user asks why their balance dropped, the ledger has the answer. It also
makes failure rate per mode measurable, since refunds carry a reason.

Credits are spent **before** generation, not after. Charging afterwards would
let a user fire ten concurrent generations on one credit. Reserve-then-refund is
the standard shape.

## Caching and rate limiting

Redis was in `compose.yaml` from day one and unused until Week 4.

### Design constraint: graceful degradation

Every cache and rate-limit path returns a safe default when Redis is
unreachable. `cache_get` returns `None`, so the request falls through to
Postgres. `check_rate_limit` returns `allowed=True`, so requests pass.

A cache that takes down the application is worse than no cache. Redis
unavailability degrades performance; it must never degrade availability.

### What is cached

| Surface | TTL | What a hit saves |
|---|---|---|
| Feed | 5 min | One Postgres query plus a batched decoded-content lookup |
| Search | 15 min | Two query embeddings (the collections use different models) plus one Cohere rerank call |

Search keys normalize the query first — collapsed whitespace, lowercased — so
`"RLHF"` and `"  rlhf "` share an entry.

Empty search results are deliberately not cached. A typo returning nothing
should not be served for fifteen minutes, and neither should a genuine miss
that a reindex would have fixed.

The feed's 5-minute TTL matches the frontend's ISR window, so the two layers
expire together rather than serving inconsistent snapshots.

### Sliding window rate limiting

Fixed windows allow double the limit at the boundary — ten requests at 11:59:59
and ten more at 12:00:01. The sliding window uses a Redis sorted set keyed by
timestamp: expired entries are trimmed, the remainder counted, the new request
added, all in one pipeline.

Buckets are per-route because the traffic shapes differ:

| Bucket | Limit | Reasoning |
|---|---|---|
| `search` | 30 / min | Each miss costs embeddings plus a rerank |
| `mode_generate` | 10 / hour | Each one is a real LLM generation |
| `mode_poll` | 120 / min | Polling is frequent by design |
| `default` | 100 / min | Feed and paper reads |

Identity is `user:{id}` when authenticated, `ip:{addr}` otherwise, read from
`X-Forwarded-For` since the API sits behind a proxy. Responses carry
`X-RateLimit-Limit` and `X-RateLimit-Remaining`; a 429 adds `Retry-After`.

## Prompt optimization

`optimization/` holds a DSPy setup for compiling the analogy generator against
labelled examples.

### The approach

DSPy inverts prompt engineering. Instead of writing a prompt, you declare a
**signature** — typed inputs and outputs with field descriptions — supply
labelled examples, and define a metric. The framework searches for the prompt
that maximizes that metric.

Two optimizers were tested. `BootstrapFewShot` selects few-shot demos:
it runs the program on the training set, keeps outputs that pass the metric, and
injects the best as examples. `MIPROv2` also **rewrites the instruction**,
proposing alternative phrasings and searching the combination of instruction and
demos with Bayesian optimization.

Worth noting: the demos that end up in the compiled prompt are not the
hand-written examples. They are outputs the model itself produced that passed
the metric — phrased in the register that model naturally generates, which is
what makes them effective few-shot for that model.

### The metric

Composite, weighted 60/40 between deterministic checks and an LLM judge.

Deterministic: setup length, AI jargon inside the analogy, mapping line count,
circular mappings (`attention → attention`), `where_it_breaks` substance, domain
brevity, and whether the setup restates the concept it is meant to explain.

The judge uses an anchored rubric where 3 is the stated default and 5 is
reserved for exceptional, and is required to name the analogy's weakest element
**before** scoring. Forcing that admission first is what stops the model
returning 5 for everything — it cannot justify top marks immediately after
writing down a genuine flaw.

During bootstrapping the judge is skipped entirely. DSPy calls the metric
hundreds of times while searching; routing that through an LLM would make
compilation cost tens of dollars instead of cents.

### Measuring the instrument first

The first version of the metric returned 1.0 for every example. A metric that
never fails measures nothing. The anchored rubric and two additional
deterministic checks brought the baseline down to ~0.87, where it discriminates.

The second problem was subtler. Five identical runs returned identical scores to
four decimal places, in 150 milliseconds total — DSPy caches LM responses to
disk by default, so runs two through five were served from cache. With
`cache=False`, the same five runs took seven minutes and produced a standard
deviation of 0.0257, giving a **noise floor of ±0.0514 at two sigma**.

That number is the whole point. The baseline alone swung from 0.822 to 0.889
between identical runs — a spread wider than any delta measured between
different programs.

### The result

| Optimizer | Delta vs baseline | Inside noise floor? |
|---|---|---|
| `BootstrapFewShot` | −0.0083 | Yes, comfortably |
| `MIPROv2` | −0.0277 | Yes |

Neither optimizer beat the hand-written signature. The conclusion is that
detailed per-field descriptions already do the work demos would do — the
declarative specification was itself the prompt engineering.

This is a null result, measured correctly. Had the sampling gone the other way,
MIPRO might have shown +0.04 and looked like a 4% win. It would have been noise.
Measuring the noise floor before comparing is what separates a number from a
finding.

The infrastructure stays versioned: 22 labelled examples reusable for any future
evaluation, a composite metric that serves as the pattern for other modes, and a
compilation pipeline that recompiles in minutes when the production model
changes.

## Experiment tracking

MLflow, added once comparing experiments by hand stopped scaling.

`observability/experiments.py` wraps the SDK with the same graceful-degradation
pattern as Langfuse — if MLflow is absent or throws, the experiment runs anyway.

Two experiments:

- **`decoded-evals`** — every section and mode evaluation, with per-metric values plus `overall.pass_rate` and `overall.faithfulness` aggregates
- **`decoded-dspy`** — compilations and variance measurements

Every run carries `git_sha` and `git_dirty` as tags. A run with uncommitted
changes is not reproducible — the state that produced it does not exist
anywhere. Recording that at the time avoids the painful discovery three weeks
later that the best result came from a tree nobody can reconstruct.

Artefacts are attached: summary JSON, the compiled DSPy program, and the
resulting prompt as plain text. Reading the actual prompt an optimizer produced,
in the UI, next to its score, is how you understand *why* one version won.

MLflow 3.x splits the UI into **GenAI** (production traces — Langfuse territory
here) and **Model training** (classic runs). Everything logged through
`log_metric` lives under the latter.

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

- *Faithfulness* — counts supported vs unsupported claims against the source paper, returns a ratio. This is the only metric that catches hallucination.
- *Heading quality* — 1-5 rubric penalizing generic section titles.
- *Analogy quality* — 1-5 rubric penalizing shallow analogies and AI jargon used to explain AI.

Ragas was evaluated and skipped. Its metrics assume a QA-over-retrieved-context
shape that doesn't match multi-section generative decoding, and a purpose-built
judge is cheaper and more legible.

**Cost and latency** — already recorded per section in `decoded_contents`, so
regressions in cost are visible alongside regressions in quality.

### Mode metrics: executable verification

The five modes fail differently from the six sections, so they get their own
evaluators in `evals/metrics/modes.py`.

Three of them produce **objectively verifiable** artefacts, which is rare in
LLM evaluation and worth exploiting fully:

| Mode | Verification | Cost | Noise |
|---|---|---|---|
| `code` | `ast.parse()` — it compiles or it doesn't | free | none |
| `diagram` | The production Mermaid validator | free | none |
| `math` | Balanced braces, no KaTeX-unsupported commands | free | none |

`ast.parse` is the most valuable metric in the harness. No judge, no threshold,
no ruído. The code either is Python or it is not.

Beyond parsing, the code evaluator walks the AST for forbidden heavy imports
(`torch`, `transformers`, `sklearn` — the prompt asks for standard library plus
numpy), counts function definitions, measures comment density against the
prompt's requirement to explain *why*, and flags generic caveats like "this is
simplified."

Content checks catch what parsing cannot: `analogy` verifies domains are
distinct across the set and mappings are not circular; `story` flags generic
headings and implausible years; `math` cross-references symbols appearing in
the LaTeX against the glossary entries, tolerating 40% uncovered because the
regex extraction is approximate — a stricter threshold would produce constant
false positives, and a check you learn to ignore is worse than no check.

Two judges cover what only an LLM can assess: whether the code implements the
paper's actual method rather than something adjacent, and whether the narrative
invented history the source doesn't support.

The summary reports `top_failures` per mode — the checks that fail most often
across the golden set. `pass_rate: 0.78` says something is wrong;
`node_count × 4` says which prompt rule is being ignored.

### Regression gate

`evals/gate.py` compares current results against committed baselines and fails
on either condition:

- **Absolute floor breached** — `pass_rate < 0.70`, `faithfulness < 0.80`, judge scores `< 3.0`
- **Regression beyond tolerance** — a drop larger than 0.05, or 0.3 on the 1-5 judge scale

The gate covers both surfaces, with separate baselines (`baseline.json` for
sections, `baseline-modes.json` for modes) so a prompt change to one cannot
silently reset the other. It also prints the top failing checks per surface,
which is diagnostic rather than gating — it tells you what to fix, not just
that something broke.

Improvements are reported but never block. Promoting a baseline is an explicit
action (`gate.py --promote`), so quality standards only move deliberately.

### CI

`.github/workflows/evals.yml` runs on any PR touching `decoding/`, `modes/`, or
`evals/`. CI restores a SQL dump of the decoded golden set
(`evals/golden/fixtures.sql`, which now includes `explanation_modes`) and runs
deterministic metrics only — no API calls, so a PR costs nothing. LLM-based
metrics run locally before opening the PR.

## Query pipeline (online)

Everything above is offline work. This is what runs when someone visits.

### Read API

Two schemas for papers, deliberately different:

- **`PaperCard`** — feed-sized. Title, one-sentence, author names, signals. No abstract.
- **`PaperDetail`** — page-sized. Full abstract, author affiliations, every decoded section.

The feed loads twenty papers at a time. Shipping twenty full abstracts to render
cards nobody reads is waste. Separate schemas make that boundary explicit
instead of leaving it to a `fields` parameter.

Decoded sections load in one batched query per request
(`_decoded_map_for`), not one query per paper. The N+1 shows up immediately at
twenty cards.

Endpoints:

| Route | Purpose |
|---|---|
| `GET /v1/papers` | Feed, paginated, filterable by category and decoded status |
| `GET /v1/papers/{arxiv_id}` | Full detail with all decoded sections |
| `GET /v1/papers/sitemap/entries` | Lean list for sitemap generation |
| `GET /v1/search` | Semantic search |
| `GET /v1/me` | Profile, plan, credits |
| `GET/POST /v1/me/saved` | Saved papers |
| `POST /v1/me/read` | Read event |

### Search: retrieve, rerank, hydrate

```
query → embed → Qdrant (40 candidates) → Cohere Rerank (top 10) → Postgres hydrate
```

**Retrieval** hits both collections. Abstracts give coverage — every embedded
paper has exactly one. Chunks give precision — the specific paragraph that
answers the question.

The two collections use different embedding models (3072 vs 1536 dimensions),
so the query is embedded twice. Vectors of different dimensionality aren't
comparable; each collection needs a query vector from its own model.

**Deduplication** happens before reranking, since a paper can surface through
both paths. Chunk evidence wins over abstract evidence: "this paragraph answers
your question" beats "this paper is about that topic."

**Reranking** is where quality comes from. Embedding search compresses a
paragraph into 1536 floats — it finds the right neighborhood, not the right
item. Cohere Rerank v3.5 is a cross-encoder: it reads query and document
together in one forward pass and scores actual relevance. Far more accurate,
far more expensive. Running it on 40 candidates is cheap; running it on 100k
documents is impossible. That asymmetry is the entire reason retrieve-then-rerank
exists as a pattern.

**Fallback is silent.** Cohere's free tier rate-limits at 10 requests/minute.
On failure, results fall back to vector score ordering and `reranked: false`
appears in the response. Search degrades in quality, never in availability.

**Hydration** is two batched queries: papers by `arxiv_id`, then their
`one_sentence` sections. Never per-result.

## Frontend

Next.js 15, App Router, TypeScript, Tailwind, shadcn/ui. Deployed on Vercel.

### Why not Streamlit

IBS/CBS used Streamlit and that was correct: internal tool, one user, no SEO.

Decoded is the opposite. Every decoded paper is a public URL that needs to rank.
Streamlit renders client-side — a crawler sees an empty page. At ten thousand
papers, that's the difference between free organic traffic and no discovery at
all. Next.js server-renders, so the HTML is complete on first byte.

### Type generation

FastAPI publishes an OpenAPI spec. `openapi-typescript` turns it into TypeScript:

```
Pydantic model → OpenAPI JSON → TypeScript types
```

One definition, two derived representations. Add a field to a Pydantic schema,
run `npm run gen:types`, and TypeScript immediately flags every place that
needs updating. Hand-written interfaces drift silently and the bug surfaces as
`undefined` in production.

A side effect worth knowing: Pydantic fields with `default_factory=list` become
optional in the generated types, so `paper.authors` is `T[] | undefined` on the
frontend even though the API always sends an array. Handled with `?? []` at the
top of each component rather than optional chaining scattered through JSX.

### Rendering strategy

| Route | Strategy | Reason |
|---|---|---|
| `/` (feed) | ISR, 5 min | New papers arrive hourly; 5 minutes of staleness is invisible |
| `/paper/[id]` | ISR, 1 hour | Decoded content is immutable until regenerated |
| `/search` | Dynamic | Query-dependent, nothing to cache |
| `/library` | Client + server guard | Per-user, never cached, never indexed |

ISR means: serve from cache, regenerate in background after the window. Nobody
waits for regeneration. Without it, a thousand visits means a thousand Postgres
queries; with it, twelve per hour.

The feed's first page is server-rendered for SEO, then handed to TanStack Query
as `initialData`. Subsequent pages load client-side via `useInfiniteQuery`, with
an `IntersectionObserver` firing 400px before the sentinel enters the viewport.
The user rarely sees a skeleton.

### API access from the browser

The browser calls `/api/v1/*` on its own origin. A Next.js rewrite forwards to
the FastAPI backend. Same-origin means no CORS, no public API port.

Server components can't use relative URLs — Node's `fetch` has no page to
resolve against — so the API client branches:

```ts
typeof window !== "undefined"
  ? NEXT_PUBLIC_API_URL   // "/api", goes through the rewrite
  : API_INTERNAL_URL      // absolute, direct to the backend
```

The same shape works in production: `API_INTERNAL_URL` becomes the Fly.io
internal address, and the rewrite is unchanged.

### Design system

OKLCH color tokens rather than hex. In OKLCH, lightness is *perceptual* — two
colors at `L: 0.55` look equally bright regardless of hue. Generating a hover
state means adjusting one number and getting a predictable result. In hex, the
same operation washes out warm colors and barely moves cool ones. Dark mode was
built by shifting lightness values, not by re-picking every color.

Three typefaces with distinct jobs: Instrument Serif for titles, Inter for body,
JetBrains Mono for metadata and labels. The visual target is a technical
document, not a social feed — hence borders instead of card shadows, tabular
numerals for metrics, and generous whitespace.

### Vocabulary tooltips

The vocabulary section isn't just a glossary at the bottom. Terms are matched
inside the 60-second read and deep dive text and wrapped in a popover showing
the paper-specific definition.

Two details make it work. Terms are sorted longest-first before regex
alternation, so "chain-of-thought" matches before "chain" can break it. And only
the *first* occurrence of each term is marked — underlining "RAG" twelve times
is noise, not teaching.

## Auth and users

Clerk for identity, Postgres for product data. `clerk_user_id` is the join key.

Building auth in-house means password hashing, email verification, reset flows,
OAuth for three providers, sessions, refresh tokens, CSRF, login rate limiting,
2FA. Two weeks of work where one mistake leaks accounts. Clerk's free tier
covers 10,000 monthly active users.

### Token verification

The frontend sends Clerk's JWT as a bearer token. The backend validates it
locally against Clerk's JWKS endpoint — public-key math, no network call per
request. `PyJWKClient` caches the keys.

The alternative, calling Clerk's API on every request, would add 50-200ms and an
external failure point to every authenticated route.

### Lazy user sync

Webhooks require a public URL, which a Codespace doesn't have. Instead, the user
row is created on first authenticated request and enriched from Clerk's API at
that moment. Same consistency, zero infrastructure. Webhooks move in during Week 6.

### Tables

| Table | Purpose |
|---|---|
| `users` | Clerk ID, profile snapshot, plan, credit balance |
| `saved_papers` | Many-to-many, unique per (user, paper) |
| `read_events` | Append-only log of reads, per section |

`read_events` is a log rather than a boolean because a user can read the same
paper multiple times, across different sections, at different moments. Week 5's
personalized digest reads this history.

`credits_remaining` exists with no consumption logic yet. Adding a column to a
populated table later means a migration; adding it now is free. Consumption
lands in Week 4 with on-demand decoding.

### Route protection

Clerk deprecated `createRouteMatcher` — path matching can diverge from how
Next.js actually routes requests, leaving protected resources reachable. The
middleware now only populates auth context. Protection lives with the resource:
`/library` has a server-side layout that calls `auth()` and redirects. Move the
folder, and the guard moves with it.

## SEO and distribution

The growth strategy is a direct consequence of the architecture: a pipeline that
produces unique content daily, on pages that rank.

Each decoded paper page carries original text — deep dive, analogies, vocabulary
— that exists nowhere else. Multiply by thousands of papers and it competes for
long-tail queries: "what is GRPO", "GSM8K benchmark meaning", "robot handwriting
paper explained."

### Dynamic OpenGraph images

Each paper generates its own social card via `ImageResponse`: title,
one-sentence, arXiv ID, categories, in the site's visual identity. A static
image would show "Decoded" for every link; a dynamic one shows what the paper
actually says. The difference in click-through when someone shares on LinkedIn
is not marginal.

### Structured data

`ScholarlyArticle` JSON-LD per paper, with authors, affiliations, the arXiv
identifier, and citation count. Google treats scholarly articles specially —
generic `Article` doesn't enable the same rich results.

### Sitemap

Generated from a dedicated backend endpoint returning only `arxiv_id` and
`updated_at`. Paginating `/v1/papers` to build a 5,000-entry sitemap would be
250 requests; one lean endpoint is one query.

Decoded papers get priority `0.8`, undecoded `0.3`. Undecoded papers only carry
the abstract, which Google already indexed on arXiv. Signaling that difference
directs crawl budget where original content actually lives.

### Deferred: GEO

Generative Engine Optimization — being citable by ChatGPT, Perplexity, and AI
Overviews — is a natural fit, since decoded text is cleaner and more quotable
than a source PDF. Two cheap additions are planned: a plain-markdown endpoint
per paper (`/paper/{id}.md`) for LLM crawlers that choke on heavy HTML, and an
`llms.txt` index. Structured FAQ blocks land in Week 4 alongside the explanation
modes.

## Deployment

```
                    ┌──────────────┐
   browser ────────▶│    Vercel    │  Next.js — SSR, ISR, OG images
                    └──────┬───────┘
                           │ /api/* rewrite
                           ▼
                    ┌──────────────┐
                    │   FastAPI    │  Codespace today, Fly.io in Week 6
                    └──┬────┬────┬─┘
                       │    │    │
              ┌────────┘    │    └────────┐
              ▼             ▼             ▼
        ┌──────────┐  ┌──────────┐  ┌──────────┐
        │   Neon   │  │  Qdrant  │  │ Upstash  │
        │ Postgres │  │  Cloud   │  │  Redis   │
        └──────────┘  └──────────┘  └──────────┘
                                     (not yet wired)
```

Neon for Postgres — serverless, scale-to-zero, generous free tier. Qdrant Cloud
free tier holds roughly 50k vectors, well past current needs.

**A driver gotcha worth recording:** connection strings from Neon include
`?sslmode=require&channel_binding=require`. Those are `psycopg` parameters;
`asyncpg` rejects them outright. The app's `DATABASE_URL` drops the query string
entirely — asyncpg negotiates TLS on its own — while `psql` commands for dumps
and restores use the original string unchanged.

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
| Decoded content storage | One row per section, versioned by schema + prompt | Single JSON blob per paper | Partial regeneration, independent evaluation, A/B prompt versions |
| Structured LLM output | Instructor + Pydantic (real-time), raw tool schemas (batch) | Raw JSON parsing, regex extraction | Validation and retry for free; descriptions double as prompt engineering |
| Decoder model routing | Haiku for extractive, Sonnet for judgment | One model everywhere | 10x cost difference; extractive tasks don't need Sonnet's reasoning |
| Deep dive context | Full parsed paper | Abstract only, RAG within paper | Cross-section reasoning needs the whole document; abstract-only invents specifics |
| Bulk decoding | Anthropic Batch API | Real-time for everything | 50% cost cut for a 24h SLA we don't care about |
| Multi-stage sections | Vocabulary (2 stages), analogies (3 stages with judge) | One mega-prompt per section | Each prompt does one job; failure modes stay isolated |
| Figure extraction | PyMuPDF in-memory, size-filtered, capped at 6 | Docling, store all figures | Zero storage cost; filters drop logos before paying for Vision |
| Eval metrics | Custom deterministic + purpose-built LLM judge | Ragas, DeepEval, promptfoo | Ragas assumes QA-over-context shape; custom judge is cheaper and more legible |
| Eval gate | Absolute floors + regression tolerance vs committed baseline | Manual review, floors only | Catches slow drift that per-run review misses |
| CI eval strategy | SQL fixtures + deterministic metrics only | Regenerate golden set per PR | Zero API cost per PR; LLM metrics run locally before opening |
| Frontend framework | Next.js 15 App Router | Streamlit, Vite SPA, Remix | Server rendering is the SEO strategy; ISR fits content that changes hourly |
| Type sharing | Generated from OpenAPI spec | Hand-written interfaces, tRPC | One source of truth; drift becomes a compile error instead of a production bug |
| Feed rendering | ISR first page + client infinite scroll | Full SSR, full CSR | Crawler gets HTML, user gets instant pagination |
| Browser → API | Same-origin rewrite through Next.js | Direct calls with CORS | No CORS, no public API port, identical shape in production |
| Color system | OKLCH tokens | Hex, HSL | Perceptual lightness makes hover states and dark mode predictable |
| Search architecture | Retrieve 40 → rerank → return 10 | Pure vector search, pure BM25 | Cross-encoder precision at a cost that only works on a small candidate set |
| Reranker | Cohere Rerank v3.5, silent fallback | BGE self-hosted, no reranker | Managed and accurate; fallback means rate limits degrade quality, not availability |
| Auth provider | Clerk | NextAuth, Supabase Auth, custom | Two weeks of security-critical work avoided; free to 10k MAU |
| Token verification | Local JWKS validation | Call Clerk API per request | Offline, no added latency, no external dependency in the hot path |
| User sync | Lazy on first authenticated request | Clerk webhooks | Webhooks need a public URL; lazy sync is equivalent with zero infrastructure |
| Route protection | Server-side guard colocated with the resource | Middleware path matching | Clerk deprecated matchers; guards that live with the route can't drift from it |
| Social images | Generated per paper via ImageResponse | Static image, no OG image | Shows the paper's actual content; materially better click-through |
| Structured data | ScholarlyArticle JSON-LD | Generic Article, none | Enables scholarly rich results that generic Article doesn't |
| LLM observability | Langfuse with no-op fallback | LangSmith, Helicone, logs only | Open source, generous free tier; never a dependency of request success |
| Mode generation | On demand, cached forever, credit-metered | Pre-generate all modes for all papers | Nobody wants all five; pre-generating four unread modes per paper is mostly waste |
| Mode schemas | One Pydantic model per mode | Generic `content: str` | Structure in the schema is structure in the UI — equations render individually, Mermaid goes to a renderer |
| Concurrent claims | `ON CONFLICT DO NOTHING` on the version key | Check-then-insert, advisory lock | Atomic in the database; two simultaneous requests produce one generation |
| Generation transport | Async: POST schedules, client polls | Synchronous request | 60-second requests don't survive proxies; Vercel hobby caps at 60s |
| Analogy model | GPT-5.6 Luna | Claude Haiku | 5× cheaper input, quality holds on pre-cleaned text |
| Credit accounting | Append-only ledger + balance column | Balance column alone | Answers *why* a balance moved; makes refund rate per mode measurable |
| Credit timing | Spend before generation, refund on failure | Charge after success | Charging after lets one credit fire ten concurrent generations |
| Cache-hit pricing | Free | Charge every request | Each paid generation becomes a permanent public artefact; aligns business model with SEO |
| Rate limiting | Sliding window over a Redis sorted set | Fixed window, token bucket | Fixed windows allow 2× the limit at the boundary |
| Cache/limit failure mode | Fail open — Redis down means no cache, not no service | Fail closed | A cache that takes down the app is worse than no cache |
| Mermaid validation | Custom checks + auto-sanitize, shared with evals | Trust the schema, render and hope | One bad character breaks the whole diagram after the user already paid |
| Code quality metric | `ast.parse` plus AST walk for imports | LLM judge only | Objectively verifiable: zero cost, zero noise, zero subjectivity |
| Prompt optimization | DSPy, tested and documented as a null result | Ship an unmeasured "improvement" | Measuring the noise floor first is what makes the comparison mean anything |
| Experiment tracking | MLflow with no-op fallback | Weights & Biases, JSON files | Open source, local SQLite backend, no infrastructure |

## Roadmap

- ~~**Week 1** — Continuous ingestion (arXiv → enrichment → parsing → embedding), Prefect orchestration~~ **done**
- ~~**Week 2** — Decoding engine (6 sections, Batch API, Claude Vision), evaluation harness with regression gate~~ **done**
- ~~**Week 3** — Next.js 15 frontend, semantic search with reranking, Clerk auth, SEO, Langfuse, production deploy~~ **done**
- ~~**Week 4** — Five explanation modes on demand, credits and ledger, Redis caching and rate limiting, DSPy optimization, MLflow, mode evaluation~~ **done**
- **Week 5** — Field Pulse dashboards, BERTopic clustering, weekly email digest, PostHog analytics
- **Week 6** — Podcast mode (ElevenLabs), Fly.io deploy, custom domain, launch

## What's not built yet (intentional)

- **`so_what` section** — schema'd but never generated; folds into the launch content pass
- **Batch API for modes** — modes are on-demand and need a synchronous claim; worth building only if pre-generating at scale
- **Figure storage (R2)** — figures are extracted, analyzed, and discarded; persisting them matters when the frontend displays them alongside explanations
- **GEO endpoints** (`.md` per paper, `llms.txt`) — cheap and well-suited to the product; deferred to Week 6
- **Structured FAQ per paper** — the format AI Overviews favours; folds into the launch content pass
- **Nightly auto-decode job** — Week 6, when there's a product to serve
- **Stripe billing** — the Pro tier exists in the credit logic but has no payment path
- **Clerk webhooks** — lazy sync covers it until there's a public domain
- **`packages/shared` as a real workspace** — Week 6, alongside the Fly deploy
- **Analytics (PostHog)** — Week 5
- **Voice** — Week 6
- **Kubernetes** — deferred indefinitely; may never be justified

## Known issues

- **Prompt caching not activating.** Implementation is correct and verified against the raw SDK at 2488 tokens (past Haiku's 2048 minimum); Anthropic returns zero cache tokens regardless. Account- or model-side. Revisit Week 6.
- **Golden set undersized.** Meaningful evaluation needs 15-30 papers across types; the set is smaller than that, which makes `pass_rate` a sample rather than a measurement. Expanding it is the cheapest available quality win.
- **API not independently deployed.** FastAPI still runs from the Codespace with port 8000 public, and Vercel's `API_INTERNAL_URL` points there. Fly.io lands Day 40.
- **Background tasks die with the process.** Mode generation runs via FastAPI `BackgroundTasks`, which is in-process. A restart mid-generation leaves a row stuck in `GENERATING` with the credit already spent. A stale-claim reaper — or moving generation to the Prefect worker — is the Week 6 fix.
- **Batch figure results incomplete.** Early runs returned 1 of 6 figures; root cause was `max_length=800` on `FigureExplained.plain_language` rejecting longer explanations at validation. Limit raised to 2000; needs a confirming regeneration.
- **DSPy cache masked variance.** Initial variance runs returned zero standard deviation across five executions — DSPy caches LM responses to disk by default, so runs 2-5 were served from cache. Fixed with `cache=False` in the experiment scripts. The cache stays enabled on the production path, where it is desirable.
- **Edge runtime deprecation.** OG image routes declare `runtime = "edge"`, which Next.js 16 deprecates in favour of `"nodejs"`. Cosmetic; one line per file.