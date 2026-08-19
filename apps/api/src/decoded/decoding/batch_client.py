from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

import structlog
from anthropic import AsyncAnthropic

logger = structlog.get_logger()

# Batch API pricing = 50% of standard rates
BATCH_DISCOUNT = 0.5

POLL_INTERVAL_SECONDS = 20
MAX_POLL_MINUTES = 60  # give up after an hour (batches usually finish in minutes)


@dataclass
class BatchResult:
    """One result from a completed batch."""
    custom_id: str
    succeeded: bool
    content_blocks: list[Any] = field(default_factory=list)
    usage: dict = field(default_factory=dict)
    error: str | None = None


class BatchClient:
    def __init__(self, api_key: str) -> None:
        self._client = AsyncAnthropic(api_key=api_key)

    async def close(self) -> None:
        await self._client.close()

    async def __aenter__(self) -> "BatchClient":
        return self

    async def __aexit__(self, *args) -> None:
        await self.close()

    async def submit(self, requests: list[dict]) -> str:
        """
        Submit a batch. Each request is {"custom_id": str, "params": {...}}.
        Returns the batch ID.
        """
        batch = await self._client.messages.batches.create(requests=requests)
        logger.info(
            "batch.submitted",
            batch_id=batch.id,
            request_count=len(requests),
            status=batch.processing_status,
        )
        return batch.id

    async def wait_for_completion(self, batch_id: str) -> str:
        """Poll until the batch finishes. Returns the final status."""
        elapsed = 0
        max_elapsed = MAX_POLL_MINUTES * 60

        while elapsed < max_elapsed:
            batch = await self._client.messages.batches.retrieve(batch_id)
            status = batch.processing_status
            counts = batch.request_counts

            logger.info(
                "batch.polling",
                batch_id=batch_id,
                status=status,
                succeeded=counts.succeeded,
                errored=counts.errored,
                processing=counts.processing,
                elapsed_s=elapsed,
            )

            if status == "ended":
                return status

            await asyncio.sleep(POLL_INTERVAL_SECONDS)
            elapsed += POLL_INTERVAL_SECONDS

        logger.error("batch.timeout", batch_id=batch_id, elapsed_s=elapsed)
        return "timeout"

    async def retrieve_results(self, batch_id: str) -> list[BatchResult]:
        """Stream results from a completed batch."""
        results: list[BatchResult] = []

        stream = await self._client.messages.batches.results(batch_id)

        async for entry in stream:
            custom_id = entry.custom_id
            result_type = entry.result.type

            if result_type == "succeeded":
                message = entry.result.message
                usage = (
                    message.usage.model_dump()
                    if hasattr(message.usage, "model_dump")
                    else dict(message.usage)
                )
                results.append(
                    BatchResult(
                        custom_id=custom_id,
                        succeeded=True,
                        content_blocks=message.content,
                        usage=usage,
                    )
                )
            else:
                error_detail = getattr(entry.result, "error", None)
                error_msg = str(error_detail) if error_detail else result_type
                logger.warning("batch.result_failed", custom_id=custom_id, error=error_msg)
                results.append(
                    BatchResult(
                        custom_id=custom_id,
                        succeeded=False,
                        error=error_msg,
                    )
                )

        logger.info(
            "batch.retrieved",
            batch_id=batch_id,
            total=len(results),
            succeeded=sum(1 for r in results if r.succeeded),
        )
        return results