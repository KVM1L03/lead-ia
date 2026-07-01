"""Temporal worker — registers the 'leads' task queue."""

import asyncio
import logging
import os

from temporalio.client import Client
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.worker import Worker

from ai_worker.activities import (
    generate_email_activity,
    get_place_details_activity,
    persist_phase_result_activity,
    qualify_lead_activity,
    search_places_activity,
)
from ai_worker.observability import setup_telemetry
from ai_worker.workflows import SANDBOXED_RUNNER, LeadGenerationWorkflow

TASK_QUEUE = "leads"

logger = logging.getLogger(__name__)


async def main() -> None:
    setup_telemetry()
    address = os.getenv("TEMPORAL_ADDRESS", "localhost:7233")
    client = await Client.connect(address, data_converter=pydantic_data_converter)
    logger.info("connected to temporal")
    async with Worker(
        client,
        task_queue=TASK_QUEUE,
        workflows=[LeadGenerationWorkflow],
        workflow_runner=SANDBOXED_RUNNER,
        activities=[
            search_places_activity,
            get_place_details_activity,
            qualify_lead_activity,
            generate_email_activity,
            persist_phase_result_activity,
        ],
    ):
        await asyncio.Event().wait()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
