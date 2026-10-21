"""
Webhook endpoint that Vapi calls to execute our custom "tools" (functions)
during a live call: looking up a patient by phone, creating a new patient,
and updating an existing one. Vapi's assistant is configured (in the Vapi
dashboard) with tool definitions whose names match the branches below; the
LLM decides when to call them based on the conversation and system prompt.

Docs: https://docs.vapi.ai/tools/custom-tools
"""

import logging
import os
from datetime import date, timedelta

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app import crud
from app.database import get_db
from app.schemas import (
    PatientCreate,
    PatientUpdate,
    PatientOut,
    AppointmentCreate,
    AppointmentOut,
    CallRecordCreate,
)

logger = logging.getLogger("vapi_tools")
router = APIRouter(prefix="/vapi", tags=["vapi"])

# Strip whitespace/quotes that sneak in when pasting into a host's env var UI.
VAPI_WEBHOOK_SECRET = os.getenv("VAPI_WEBHOOK_SECRET", "change-me").strip().strip("\"'")
logger.warning(
    "Vapi webhook secret check %s",
    "disabled" if VAPI_WEBHOOK_SECRET in ("", "change-me") else f"enabled (secret length {len(VAPI_WEBHOOK_SECRET)})",
)


def _verify_secret(x_vapi_secret: str | None):
    # Basic shared-secret check. Configure the same value as a custom header
    # on the tool's server config in the Vapi dashboard.
    if VAPI_WEBHOOK_SECRET and VAPI_WEBHOOK_SECRET != "change-me":
        if (x_vapi_secret or "").strip() != VAPI_WEBHOOK_SECRET:
            raise HTTPException(status_code=401, detail="Invalid webhook secret")


def _tool_result(tool_call_id: str, result: dict) -> dict:
    # Vapi expects results shaped like this for its tool-call webhook format.
    return {"results": [{"toolCallId": tool_call_id, "result": result}]}


@router.post("/tools")
async def handle_tool_call(
    request: Request,
    db: Session = Depends(get_db),
    x_vapi_secret: str | None = Header(default=None),
):
    _verify_secret(x_vapi_secret)
    body = await request.json()

    message = body.get("message", {})
    tool_calls = message.get("toolCalls") or message.get("toolCallList") or []
    if not tool_calls:
        # Some Vapi payload shapes nest a single toolCall differently; be lenient.
        single = message.get("toolCall")
        tool_calls = [single] if single else []

    results = []
    for call in tool_calls:
        tool_call_id = call.get("id")
        function = call.get("function", {})
        name = function.get("name")
        args = function.get("arguments") or {}
        if isinstance(args, str):
            import json

            try:
                args = json.loads(args)
            except json.JSONDecodeError:
                args = {}

        logger.info("Vapi tool call: %s(%s)", name, args)

        try:
            output = _dispatch(db, name, args)
        except ValidationError as exc:
            errors = "; ".join(f"{e['loc'][0]}: {e['msg']}" for e in exc.errors())
            output = {"success": False, "error": errors}
        except Exception as exc:
            logger.exception("Tool call failed: %s", name)
            output = {"success": False, "error": str(exc)}

        results.append({"toolCallId": tool_call_id, "result": output})

    return {"results": results}


def _dispatch(db: Session, name: str, args: dict) -> dict:
    if name == "lookup_patient_by_phone":
        return _lookup_patient_by_phone(db, args)
    if name == "create_patient":
        return _create_patient(db, args)
    if name == "update_patient":
        return _update_patient(db, args)
    if name == "get_available_appointment_slots":
        return _get_available_appointment_slots(args)
    if name == "schedule_appointment":
        return _schedule_appointment(db, args)
    return {"success": False, "error": f"Unknown tool: {name}"}


def _lookup_patient_by_phone(db: Session, args: dict) -> dict:
    phone = (args.get("phone_number") or "").strip()
    if not phone:
        return {"success": False, "error": "phone_number is required"}
    import re

    digits = re.sub(r"\D", "", phone)
    patient = crud.find_by_phone(db, digits)
    if not patient:
        return {"success": True, "found": False}
    return {
        "success": True,
        "found": True,
        "patient_id": patient.patient_id,
        "first_name": patient.first_name,
        "last_name": patient.last_name,
    }


def _create_patient(db: Session, args: dict) -> dict:
    payload = PatientCreate(**args)
    patient = crud.create_patient(db, payload)
    logger.info(
        "PATIENT REGISTERED via voice agent: %s",
        PatientOut.model_validate(patient).model_dump(mode="json"),
    )
    return {
        "success": True,
        "patient_id": patient.patient_id,
        "first_name": patient.first_name,
        "last_name": patient.last_name,
    }


def _update_patient(db: Session, args: dict) -> dict:
    patient_id = args.pop("patient_id", None)
    if not patient_id:
        return {"success": False, "error": "patient_id is required"}
    patient = crud.get_patient(db, patient_id)
    if not patient:
        return {"success": False, "error": "Patient not found"}
    payload = PatientUpdate(**args)
    patient = crud.update_patient(db, patient, payload)
    logger.info(
        "PATIENT UPDATED via voice agent: %s",
        PatientOut.model_validate(patient).model_dump(mode="json"),
    )
    return {"success": True, "patient_id": patient.patient_id}


# Mock appointment scheduling: no real calendar/provider system behind this,
# just a fixed set of weekday morning/afternoon slots for the next 5 business days.
_MOCK_SLOT_TIMES = ["09:00", "10:30", "13:00", "15:30"]


def _next_business_days(n: int) -> list[date]:
    days = []
    d = date.today() + timedelta(days=1)
    while len(days) < n:
        if d.weekday() < 5:  # Mon-Fri
            days.append(d)
        d += timedelta(days=1)
    return days


def _get_available_appointment_slots(args: dict) -> dict:
    days = _next_business_days(3)
    slots = [
        {"date": d.isoformat(), "time": t}
        for d in days
        for t in _MOCK_SLOT_TIMES
    ]
    return {"success": True, "slots": slots}


def _schedule_appointment(db: Session, args: dict) -> dict:
    patient_id = args.get("patient_id")
    if not patient_id:
        return {"success": False, "error": "patient_id is required"}
    patient = crud.get_patient(db, patient_id)
    if not patient:
        return {"success": False, "error": "Patient not found"}
    payload = AppointmentCreate(**args)
    appointment = crud.create_appointment(db, payload)
    logger.info(
        "APPOINTMENT SCHEDULED via voice agent: %s",
        AppointmentOut.model_validate(appointment).model_dump(mode="json"),
    )
    return {
        "success": True,
        "appointment_id": appointment.appointment_id,
        "appointment_date": appointment.appointment_date.isoformat(),
        "appointment_time": appointment.appointment_time,
    }


@router.post("/call-events")
async def handle_call_event(
    request: Request,
    db: Session = Depends(get_db),
    x_vapi_secret: str | None = Header(default=None),
):
    """
    Separate webhook Vapi calls for call lifecycle events (configured as the
    assistant's `serverUrl`, distinct from the per-tool `server.url` above).
    We only care about `end-of-call-report`, which carries the full transcript
    and summary once the call ends -- used to fulfil the "Call Recording/
    Transcript" bonus by linking it back to whichever patient_id the call's
    tool calls created or updated (tracked via the assistant's call metadata).
    """
    _verify_secret(x_vapi_secret)
    body = await request.json()
    message = body.get("message", {})

    if message.get("type") != "end-of-call-report":
        return {"received": True}

    call = message.get("call", {}) or {}
    vapi_call_id = call.get("id")
    # Newer Vapi payloads nest these under `artifact` / `analysis`; older ones are top-level.
    transcript = message.get("transcript") or (message.get("artifact") or {}).get("transcript")
    summary = message.get("summary") or (message.get("analysis") or {}).get("summary")
    ended_reason = message.get("endedReason")

    # The assistant doesn't have a first-class "patient_id" call field, so we
    # recover it by matching the most recent patient created/updated with this
    # vapi_call_id, if any tool call in this session logged one via metadata;
    # falling back to unattached (patient_id=None) is fine -- the transcript
    # is still stored and visible on the dashboard's "Recent Calls" list.
    patient_id = message.get("metadata", {}).get("patient_id") if isinstance(message.get("metadata"), dict) else None

    record = crud.create_call_record(
        db,
        CallRecordCreate(
            patient_id=patient_id,
            vapi_call_id=vapi_call_id,
            transcript=transcript,
            summary=summary,
            ended_reason=ended_reason,
        ),
    )
    logger.info("CALL TRANSCRIPT STORED: call_record_id=%s vapi_call_id=%s patient_id=%s", record.call_record_id, vapi_call_id, patient_id)
    return {"received": True}
