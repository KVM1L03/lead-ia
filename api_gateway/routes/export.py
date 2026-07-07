"""POST /api/leads/export — serialize approved leads to CSV.

POST instead of GET: sync/demo mode must send leads in the request body (no server
state). GET with a body is non-standard and rejected by many HTTP clients. Using POST
for both modes gives the frontend a single code path regardless of PERSISTENCE_ENABLED.
In DB mode the server ignores body.leads; in sync mode it ignores body.run_id.
"""

from __future__ import annotations

import csv
import io
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, ConfigDict, TypeAdapter
from sqlalchemy.ext.asyncio import AsyncSession

from api_gateway.db import RunRow, get_session_maybe
from shared.schemas import Lead

router = APIRouter(prefix="/api/leads")

_leads_ta: TypeAdapter[list[Lead]] = TypeAdapter(list[Lead])

COLUMNS: list[str] = [
    "business_name",
    "address",
    "website",
    "phone",
    "category",
    "rating",
    "review_count",
    "qualifier_score",
    "qualifier_reasoning",
    "email_subject",
    "email_body",
    "personalization_hooks",
]


def leads_to_csv(leads: list[Lead]) -> str:
    """Serialize approved leads to CSV string.

    Uses csv.DictWriter (QUOTE_MINIMAL) — handles commas, newlines, and quotes
    in email bodies without corruption. No BOM: add .encode('utf-8-sig') at the
    call site if Excel on Windows misreads Polish characters.
    """
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=COLUMNS, quoting=csv.QUOTE_MINIMAL)
    writer.writeheader()
    for lead in leads:
        if lead.decision != "approved":
            continue
        writer.writerow(
            {
                "business_name": lead.place.name,
                "address": lead.place.address,
                "website": lead.place.website or "",
                "phone": lead.place.phone or "",
                "category": lead.place.category,
                "rating": f"{lead.place.rating:g}",
                "review_count": str(lead.place.review_count),
                "qualifier_score": f"{lead.verdict.score:g}" if lead.verdict else "",
                "qualifier_reasoning": lead.verdict.reasoning if lead.verdict else "",
                "email_subject": lead.email.subject if lead.email else "",
                "email_body": lead.email.body if lead.email else "",
                "personalization_hooks": "; ".join(lead.email.personalization_hooks)
                if lead.email
                else "",
            }
        )
    return buf.getvalue()


class ExportRequest(BaseModel):
    model_config = ConfigDict(strict=True)

    # DB mode (PERSISTENCE_ENABLED=true): identifies the cohort in Postgres.
    run_id: str | None = None
    # Sync/demo mode (PERSISTENCE_ENABLED=false): client holds leads from sync response.
    leads: list[Lead] | None = None


@router.post("/export")
async def export_leads(
    body: ExportRequest,
    session: Annotated[AsyncSession | None, Depends(get_session_maybe)],
) -> Response:
    if session is not None:
        # DB mode: load from Postgres
        if body.run_id is None:
            raise HTTPException(
                status_code=422, detail="run_id required when PERSISTENCE_ENABLED=true"
            )
        row: RunRow | None = await session.get(RunRow, body.run_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Run not found")
        leads = _leads_ta.validate_json(row.leads_json or "[]")
    else:
        # Sync/demo mode: no DB — use leads from request body
        if body.leads is None:
            raise HTTPException(
                status_code=422, detail="leads required when PERSISTENCE_ENABLED=false"
            )
        leads = body.leads

    filename = f"leadia-export-{date.today().isoformat()}.csv"
    return Response(
        content=leads_to_csv(leads).encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
