from __future__ import annotations

import structlog
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import Distance, VectorParams, PayloadSchemaType

logger = structlog.get_logger()

ABSTRACTS_COLLECTION = "paper_abstracts"
CHUNKS_COLLECTION = "paper_chunks"

ABSTRACT_DIMS = 3072  # text-embedding-3-large
CHUNK_DIMS = 1536     # text-embedding-3-small


async def ensure_collections(client: AsyncQdrantClient) -> None:
    """Create both collections if they don't exist. Idempotent."""
    existing = {c.name for c in (await client.get_collections()).collections}

    if ABSTRACTS_COLLECTION not in existing:
        logger.info("qdrant.creating", collection=ABSTRACTS_COLLECTION, dims=ABSTRACT_DIMS)
        await client.create_collection(
            collection_name=ABSTRACTS_COLLECTION,
            vectors_config=VectorParams(size=ABSTRACT_DIMS, distance=Distance.COSINE),
        )
        # Payload indexes for fast filtering
        await client.create_payload_index(
            collection_name=ABSTRACTS_COLLECTION,
            field_name="arxiv_id",
            field_schema=PayloadSchemaType.KEYWORD,
        )
        await client.create_payload_index(
            collection_name=ABSTRACTS_COLLECTION,
            field_name="published_at",
            field_schema=PayloadSchemaType.DATETIME,
        )
        await client.create_payload_index(
            collection_name=ABSTRACTS_COLLECTION,
            field_name="categories",
            field_schema=PayloadSchemaType.KEYWORD,
        )
    else:
        logger.info("qdrant.exists", collection=ABSTRACTS_COLLECTION)

    if CHUNKS_COLLECTION not in existing:
        logger.info("qdrant.creating", collection=CHUNKS_COLLECTION, dims=CHUNK_DIMS)
        await client.create_collection(
            collection_name=CHUNKS_COLLECTION,
            vectors_config=VectorParams(size=CHUNK_DIMS, distance=Distance.COSINE),
        )
        await client.create_payload_index(
            collection_name=CHUNKS_COLLECTION,
            field_name="paper_id",
            field_schema=PayloadSchemaType.INTEGER,
        )
        await client.create_payload_index(
            collection_name=CHUNKS_COLLECTION,
            field_name="arxiv_id",
            field_schema=PayloadSchemaType.KEYWORD,
        )
    else:
        logger.info("qdrant.exists", collection=CHUNKS_COLLECTION)