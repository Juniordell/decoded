# decoded# Decoded

Every AI paper, explained for humans.

Decoded monitors arXiv continuously, enriches new papers with citation and
community signals, and turns each one into layered explanations — a
twenty-word summary, a sixty-second read, a five-minute deep dive, plain-language
interpretations of every figure, contextual vocabulary, and analogies. Five
further explanation modes are generated on demand: the mathematics, extended
analogies, the field's history, an architecture diagram, and the core algorithm
as runnable Python.

Research topics are discovered by clustering rather than assigned by hand, and
tracked week over week. A personalized email goes out on Tuesdays.

**Live:** [readdecoded.com](https://readdecoded.com)

---

## What it does

```
arXiv ──▶ enrich ──▶ parse ──▶ embed ──▶ decode ──▶ serve
          OpenAlex   Llama-    Qdrant    Claude     Next.js
          S2, HN     Parse               Haiku/     ISR + SEO
                                         Sonnet
```

**Ingestion** runs hourly. New papers are scored by citations, Hacker News
activity, and author affiliation, and that score decides what gets decoded
first.

**Decoding** produces six sections per paper through Claude, using the Batch API
where latency does not matter. Cost lands around $0.19 per fully decoded paper.

**Explanation modes** are generated when a reader asks for one, cached
permanently, and free for everyone afterwards. The first person to request a
mode pays a credit; everyone after reads it at no cost.

**Topics** come from clustering the paper embeddings with UMAP and HDBSCAN, then
naming each cluster with an LLM. Weekly snapshots turn "this topic exists" into
"this topic grew 40% in a month."

**The digest** ranks by personal relevance — followed authors weigh more than
followed topics — with a hard diversity cap so no email is six papers on one
subject.

Full rationale for every decision is in [ARCHITECTURE.md](./ARCHITECTURE.md).

---

## Stack

| Layer | Choice |
|---|---|
| Backend | FastAPI, SQLAlchemy 2.x async, Alembic |
| Frontend | Next.js 15 App Router, TypeScript, Tailwind, shadcn/ui |
| Database | PostgreSQL (Neon in production) |
| Vectors | Qdrant, two collections at different embedding dimensions |
| Cache | Redis — response cache and sliding-window rate limiting |
| LLM | Anthropic Claude (Haiku, Sonnet, Vision), OpenAI for embeddings and one mode |
| Retrieval | Hybrid search plus Cohere Rerank v3.5 |
| Orchestration | Prefect 3 — hourly, nightly, and weekly flows |
| Auth | Clerk, JWT verified locally against JWKS |
| Email | Resend with SPF, DKIM, DMARC |
| Observability | Langfuse for LLM traces, PostHog for product, MLflow for experiments |
| Evaluation | Custom harness — deterministic checks, LLM judges, regression gate |
| Optimization | DSPy for prompt compilation |

---

## Running locally

**Requires:** Python 3.12, Node 22, Docker, Poetry.

```bash
git clone https://github.com/Juniordell/decoded.git
cd decoded

# Infrastructure
docker compose -f infra/compose.yaml up -d postgres redis qdrant

# Backend
cd apps/api
cp .env.example .env          # fill in API keys
poetry install
poetry run alembic upgrade head

# Frontend
cd ../web
cp .env.example .env.local    # fill in Clerk and API URLs
npm install
```

Then, in separate terminals:

```bash
make api      # FastAPI on :8000
make web      # Next.js on :3000
```

### Populating data

```bash
cd apps/api

poetry run python -m decoded.cli.ingest       # pull recent papers
poetry run python -m decoded.cli.enrich       # citations, TL;DRs, HN
poetry run python -m decoded.cli.parse        # PDF → markdown
poetry run python -m decoded.cli.embed        # vectors → Qdrant

poetry run python -m decoded.cli.decode --arxiv-id 2608.06221
poetry run python -m decoded.cli.modes --arxiv-id 2608.06221

poetry run python -m decoded.cli.topics cluster
poetry run python -m decoded.cli.topics snapshots
poetry run python -m decoded.cli.people backfill
```

Topic clustering needs several hundred embedded papers to find real structure.
Below that it produces one large incoherent cluster.

### Orchestration

```bash
make prefect-server     # UI on :4200
make prefect-deploy
make prefect-worker

make run-weekly-dry     # full weekly cycle, sends nothing
```

---

## Quality

Prompt changes are gated on measured quality, not judgment.

```bash
make eval-sections      # 30+ checks over the six decoded sections
make eval-modes         # per-mode checks, including executable verification
make gate               # fails on floor breach or regression
```

Three of the five modes produce objectively verifiable output: generated Python
must pass `ast.parse`, Mermaid must pass the same validator used in production,
and LaTeX must have balanced braces and no KaTeX-unsupported commands. Those
checks are free and have no variance, which is rare in LLM evaluation.

The rest is covered by deterministic content checks and LLM judges with anchored
rubrics — faithfulness against the source, code fidelity to the paper's method,
and whether a narrative invented history.

The gate compares against committed baselines and fails on either an absolute
floor breach or a regression beyond tolerance. CI runs the deterministic half
against SQL fixtures, so a pull request costs nothing.

---

## Layout

```
apps/
  api/                  FastAPI backend
    src/decoded/
      api/              routers, response schemas, dependencies
      auth/             Clerk JWT verification
      cache/            Redis client, rate limiting
      cli/              one command per pipeline stage
      db/               models and repositories
      decoding/         six-section generation, Batch API
      digest/           selection, subject, templates, sending
      embeddings/       Qdrant, chunking, OpenAI
      external/         arXiv, OpenAlex, Semantic Scholar, HN
      flows/            Prefect flows
      ingestion/        poller, enricher, priority scoring
      modes/            five explanation modes
      observability/    Langfuse, MLflow, PostHog
      parsing/          PDF parser abstraction
      people/           author and institution backfill
      search/           retrieval and reranking
      topics/           clustering, naming, snapshots
    evals/              golden set, metrics, judges, gate
    optimization/       DSPy programs and compiled artefacts
  web/                  Next.js frontend
infra/                  docker-compose
```

---

## Notes

**Cost.** A fully decoded paper runs about $0.19 through the Batch API. Nothing
decodes automatically during development — generation is triggered explicitly by
arXiv ID, and the nightly flow enforces a daily budget checked before submitting
rather than after.

**Types.** The frontend's API types are generated from the FastAPI OpenAPI spec
(`npm run gen:types`). Adding a field to a Pydantic model and forgetting the
frontend becomes a compile error rather than an `undefined` in production.

**Async.** Every I/O path is async — Postgres, Qdrant, Redis, and all four LLM
providers. The workload is entirely I/O bound; a synchronous version would need
far more workers for the same concurrency.

**Degradation.** Redis, Langfuse, MLflow, and PostHog all fall back to no-ops
when unavailable. Observability that can take down the application is worse than
none.

---

Built by [Nelson Dell](https://github.com/Juniordell).