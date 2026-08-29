from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import numpy as np
import structlog
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert

from decoded.db.base import async_session_factory
from decoded.db.models import (
    ClusteringRun,
    Paper,
    Topic,
    TopicSnapshot,
    paper_topics,
)
from decoded.topics.naming import TopicNamer, slugify
from decoded.topics.vectors import fetch_paper_vectors

logger = structlog.get_logger()

# HDBSCAN descarta pontos que não pertencem a nenhum cluster — vira -1
OUTLIER_LABEL = -1


@dataclass
class ClusterResult:
    labels: np.ndarray
    keywords_per_cluster: dict[int, list[str]]
    n_clusters: int
    n_outliers: int


def run_bertopic(
    vectors: np.ndarray,
    documents: list[str],
    min_cluster_size: int = 5,
    random_state: int = 42,
) -> ClusterResult:
    """
    Roda BERTopic com embeddings pré-calculados.

    Importado aqui dentro porque a importação é lenta (~10s) e carrega
    dependências pesadas que nenhum outro caminho precisa.
    """
    from bertopic import BERTopic
    from bertopic.vectorizers import ClassTfidfTransformer
    from hdbscan import HDBSCAN
    from sklearn.feature_extraction.text import CountVectorizer
    from umap import UMAP

    logger.info("clustering.start", n_docs=len(documents), dims=vectors.shape[1])

    # UMAP reduz 3072 dimensões para 5. HDBSCAN não funciona bem em alta dimensão.
    umap_model = UMAP(
        n_neighbors=min(15, max(5, len(documents) // 30)),
        n_components=5,
        min_dist=0.0,
        metric="cosine",
        random_state=random_state,
    )

    effective_min = max(3, min(min_cluster_size, len(documents) // 25))

    hdbscan_model = HDBSCAN(
        min_cluster_size=effective_min,
        min_samples=max(2, effective_min // 2),
        metric="euclidean",
        cluster_selection_method="eom",
        prediction_data=True,
    )

    logger.info(
        "clustering.params",
        n_docs=len(documents),
        min_cluster_size=effective_min,
        n_neighbors=umap_model.n_neighbors,
    )

    # Stop words em inglês mais termos que aparecem em todo paper de IA
    # e portanto não distinguem nada
    vectorizer = CountVectorizer(
        stop_words="english",
        min_df=2,
        ngram_range=(1, 2),
    )

    topic_model = BERTopic(
        umap_model=umap_model,
        hdbscan_model=hdbscan_model,
        vectorizer_model=vectorizer,
        ctfidf_model=ClassTfidfTransformer(reduce_frequent_words=True),
        calculate_probabilities=False,
        verbose=False,
    )

    labels, _ = topic_model.fit_transform(documents, embeddings=vectors)
    labels = np.array(labels)

    keywords: dict[int, list[str]] = {}
    for topic_id in set(labels):
        if topic_id == OUTLIER_LABEL:
            continue
        words = topic_model.get_topic(topic_id) or []
        keywords[int(topic_id)] = [w for w, _score in words[:15]]

    n_outliers = int((labels == OUTLIER_LABEL).sum())
    n_docs = len(labels)

    for cid in list(keywords.keys()):
        share = (labels == cid).sum() / n_docs
        if share > 0.4:
            logger.warning(
                "clustering.degenerate_cluster",
                cluster=cid,
                share=round(share, 2),
                hint="amostra pequena ou min_cluster_size mal calibrado",
            )
            
    logger.info(
        "clustering.done",
        n_clusters=len(keywords),
        n_outliers=n_outliers,
    )

    return ClusterResult(
        labels=labels,
        keywords_per_cluster=keywords,
        n_clusters=len(keywords),
        n_outliers=n_outliers,
    )


async def cluster_and_store(
    qdrant_url: str,
    qdrant_api_key: str | None,
    anthropic_api_key: str,
    naming_model: str,
    min_cluster_size: int = 5,
    limit: int = 5000,
) -> dict:
    """
    Pipeline completo: busca vetores, clusteriza, nomeia, persiste.
    """
    started = datetime.now(timezone.utc)
    log = logger.bind(source="clustering")

    # --- 1. Vetores ---
    pv = await fetch_paper_vectors(qdrant_url, qdrant_api_key, limit=limit)

    if len(pv.vectors) < min_cluster_size * 2:
        log.warning("clustering.too_few_papers", count=len(pv.vectors))
        return {"error": "too_few_papers", "count": len(pv.vectors)}

    # --- 2. Documentos para o c-TF-IDF ---
    # BERTopic precisa de texto para extrair palavras-chave. Título mais
    # abstract dá vocabulário melhor que só o título.
    async with async_session_factory() as session:
        stmt = select(Paper.id, Paper.title, Paper.abstract).where(
            Paper.id.in_(pv.paper_ids)
        )
        rows = {r.id: f"{r.title}. {r.abstract}" for r in (await session.execute(stmt)).all()}

    documents = [rows.get(pid, pv.titles[i]) for i, pid in enumerate(pv.paper_ids)]

    # --- 3. Clustering ---
    result = run_bertopic(
        vectors=pv.vectors,
        documents=documents,
        min_cluster_size=min_cluster_size,
    )

    if result.n_clusters == 0:
        log.warning("clustering.no_clusters")
        return {"error": "no_clusters_found"}

    # --- 4. Nomeação ---
    naming_cost = 0.0
    named: dict[int, tuple[str, str]] = {}

    async with TopicNamer(anthropic_api_key, naming_model) as namer:
        for cluster_id, keywords in result.keywords_per_cluster.items():
            sample_titles = [
                pv.titles[i]
                for i, label in enumerate(result.labels)
                if label == cluster_id
            ][:8]

            try:
                topic_name = await namer.name_topic(keywords, sample_titles)
                named[cluster_id] = (topic_name.name, topic_name.description)
                log.info("clustering.named", cluster=cluster_id, name=topic_name.name)
            except Exception as e:
                log.warning("clustering.naming_failed", cluster=cluster_id, error=str(e))
                named[cluster_id] = (
                    " ".join(keywords[:3]).title(),
                    f"Papers about {', '.join(keywords[:5])}",
                )

        naming_cost = namer.total_cost

    # --- 5. Persistência ---
    async with async_session_factory() as session:
        run = ClusteringRun(
            started_at=started,
            papers_clustered=len(pv.paper_ids),
            topics_found=result.n_clusters,
            outliers=result.n_outliers,
            min_cluster_size=min_cluster_size,
        )
        session.add(run)
        await session.flush()

        # Desativa tópicos antigos. Não deleta — snapshots históricos
        # apontam para eles.
        existing = (await session.execute(select(Topic))).scalars().all()
        for t in existing:
            t.is_active = False

        now = datetime.now(timezone.utc)
        topic_by_cluster: dict[int, Topic] = {}

        for cluster_id, (name, description) in named.items():
            slug = slugify(name)
            keywords = result.keywords_per_cluster[cluster_id]
            count = int((result.labels == cluster_id).sum())

            stmt = (
                insert(Topic)
                .values(
                    slug=slug,
                    name=name,
                    description=description,
                    cluster_id=cluster_id,
                    keywords=keywords,
                    paper_count=count,
                    last_clustered_at=now,
                    is_active=True,
                )
                .on_conflict_do_update(
                    index_elements=["slug"],
                    set_={
                        "name": name,
                        "description": description,
                        "cluster_id": cluster_id,
                        "keywords": keywords,
                        "paper_count": count,
                        "last_clustered_at": now,
                        "is_active": True,
                    },
                )
                .returning(Topic)
            )
            topic = (await session.execute(stmt)).scalar_one()
            topic_by_cluster[cluster_id] = topic

        await session.flush()

        # Reatribui papers. Limpa as ligações antigas primeiro.
        await session.execute(delete(paper_topics))

        assignments = []
        for i, label in enumerate(result.labels):
            if label == OUTLIER_LABEL:
                continue
            topic = topic_by_cluster.get(int(label))
            if topic is None:
                continue
            assignments.append(
                {
                    "paper_id": pv.paper_ids[i],
                    "topic_id": topic.id,
                    "confidence": 1.0,
                }
            )

        if assignments:
            await session.execute(insert(paper_topics), assignments)

        run.finished_at = datetime.now(timezone.utc)
        run.naming_cost_usd = naming_cost
        run.log = {
            "topics": {
                str(cid): {"name": n, "count": int((result.labels == cid).sum())}
                for cid, (n, _) in named.items()
            }
        }

        await session.commit()

    duration = (datetime.now(timezone.utc) - started).total_seconds()
    log.info(
        "clustering.stored",
        topics=result.n_clusters,
        outliers=result.n_outliers,
        naming_cost_usd=round(naming_cost, 4),
        duration_s=round(duration, 1),
    )

    return {
        "papers_clustered": len(pv.paper_ids),
        "topics_found": result.n_clusters,
        "outliers": result.n_outliers,
        "naming_cost_usd": round(naming_cost, 4),
        "duration_s": round(duration, 1),
        "topics": [
            {"name": n, "count": int((result.labels == cid).sum())}
            for cid, (n, _) in sorted(
                named.items(), key=lambda x: -int((result.labels == x[0]).sum())
            )
        ],
    }