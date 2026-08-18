import asyncio
import os
import sys

from openai import AsyncOpenAI
from qdrant_client import AsyncQdrantClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from decoded.config import settings  # noqa: E402
from decoded.embeddings.qdrant_setup import ABSTRACTS_COLLECTION  # noqa: E402


async def main() -> None:
    query = " ".join(sys.argv[1:]) or "efficient fine-tuning of large language models"

    openai_client = AsyncOpenAI(api_key=settings.openai_api_key)
    qdrant = AsyncQdrantClient(url=settings.qdrant_url)

    resp = await openai_client.embeddings.create(
        model=settings.embedding_model_large,
        input=[query],
    )
    query_vec = resp.data[0].embedding

    hits_resp = await qdrant.query_points(
        collection_name=ABSTRACTS_COLLECTION,
        query=query_vec,
        limit=5,
    )
    hits = hits_resp.points

    print(f"\nQuery: {query}\n")
    for hit in hits:
        print(f"  [{hit.score:.3f}] {hit.payload['title']}")
        print(f"          arxiv_id={hit.payload['arxiv_id']}")

    await openai_client.close()
    await qdrant.close()


if __name__ == "__main__":
    asyncio.run(main())