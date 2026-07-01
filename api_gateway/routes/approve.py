"""POST /api/leads/approve — human-in-the-loop decision on generated leads.

"Approve" means the email is final and ready; "reject" marks the lead as not
wanted. No email is sent — that is out of scope for this service.

If edited_emails is provided for a lead, the subject/body is overwritten before
the decision is recorded. The original model metadata (personalization_hooks,
model_used) is preserved.

Every decided lead gets a decided_at timestamp for auditing.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, TypeAdapter
from sqlalchemy.ext.asyncio import AsyncSession

from api_gateway.db import RunRow, get_session
from shared.schemas import GeneratedEmail, Lead

router = APIRouter(prefix="/api/leads")

_leads_ta: TypeAdapter[list[Lead]] = TypeAdapter(list[Lead])


# ── Request / Response schemas ────────────────────────────────────────────────


class EditedEmail(BaseModel):
    model_config = ConfigDict(strict=True)

    subject: Annotated[str, StringConstraints(max_length=100)]
    body: Annotated[str, StringConstraints(max_length=1500)]


class ApproveRequest(BaseModel):
    model_config = ConfigDict(strict=True)

    run_id: str
    lead_ids: Annotated[list[str], Field(min_length=1, max_length=50)]
    action: Literal["approved", "rejected"]
    edited_emails: dict[str, EditedEmail] = {}


class ApproveResponse(BaseModel):
    updated: int


# ── Route ─────────────────────────────────────────────────────────────────────


@router.post("/approve", response_model=ApproveResponse)
async def approve_leads(
    body: ApproveRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ApproveResponse:
    """Bulk approve or reject leads. Optionally overwrite email content."""
    row: RunRow | None = await session.get(RunRow, body.run_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Run not found")
    if not row.leads_json:
        raise HTTPException(status_code=404, detail="No leads found for this run")

    leads = _leads_ta.validate_json(row.leads_json)
    target_ids = set(body.lead_ids)
    now = datetime.utcnow()
    updated = 0

    for i, lead in enumerate(leads):
        if lead.place.id not in target_ids:
            continue
        edit = body.edited_emails.get(lead.place.id)
        new_email = lead.email
        if edit is not None and lead.email is not None:
            new_email = GeneratedEmail(
                subject=edit.subject,
                body=edit.body,
                personalization_hooks=lead.email.personalization_hooks,
                model_used=lead.email.model_used,
            )
        leads[i] = lead.model_copy(
            update={"email": new_email, "decision": body.action, "decided_at": now}
        )
        updated += 1

    row.leads_json = json.dumps([json.loads(lead.model_dump_json()) for lead in leads])
    await session.commit()
    return ApproveResponse(updated=updated)
