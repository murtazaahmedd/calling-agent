import os

# Tests exercise /vapi/tools without needing a real shared secret; must be set
# before app.main (and app.routers.vapi_tools) import os.getenv() at module load.
os.environ["VAPI_WEBHOOK_SECRET"] = "change-me"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app

engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(autouse=True)
def _reset_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)

VALID_PATIENT = {
    "first_name": "Jane",
    "last_name": "Doe",
    "date_of_birth": "1990-04-12",
    "sex": "Female",
    "phone_number": "5551234567",
    "email": "jane@example.com",
    "address_line_1": "123 Main St",
    "city": "Austin",
    "state": "TX",
    "zip_code": "78701",
}


def test_create_patient_success():
    resp = client.post("/patients", json=VALID_PATIENT)
    assert resp.status_code == 201
    body = resp.json()
    assert body["error"] is None
    assert body["data"]["first_name"] == "Jane"
    assert body["data"]["patient_id"]


def test_create_patient_invalid_dob_future():
    payload = {**VALID_PATIENT, "date_of_birth": "2999-01-01"}
    resp = client.post("/patients", json=payload)
    assert resp.status_code == 422
    assert resp.json()["error"] is not None


def test_create_patient_invalid_phone():
    payload = {**VALID_PATIENT, "phone_number": "123"}
    resp = client.post("/patients", json=payload)
    assert resp.status_code == 422


def test_create_patient_invalid_state():
    payload = {**VALID_PATIENT, "state": "ZZ"}
    resp = client.post("/patients", json=payload)
    assert resp.status_code == 422


def test_get_patient_by_id():
    created = client.post("/patients", json=VALID_PATIENT).json()["data"]
    resp = client.get(f"/patients/{created['patient_id']}")
    assert resp.status_code == 200
    assert resp.json()["data"]["patient_id"] == created["patient_id"]


def test_get_patient_not_found():
    resp = client.get("/patients/does-not-exist")
    assert resp.status_code == 404


def test_list_patients_filter_by_last_name():
    client.post("/patients", json=VALID_PATIENT)
    client.post("/patients", json={**VALID_PATIENT, "last_name": "Smith", "phone_number": "5550001111"})
    resp = client.get("/patients", params={"last_name": "Doe"})
    data = resp.json()["data"]
    assert len(data) == 1
    assert data[0]["last_name"] == "Doe"


def test_update_patient_partial():
    created = client.post("/patients", json=VALID_PATIENT).json()["data"]
    resp = client.put(f"/patients/{created['patient_id']}", json={"city": "Dallas"})
    assert resp.status_code == 200
    assert resp.json()["data"]["city"] == "Dallas"
    assert resp.json()["data"]["last_name"] == "Doe"


def test_soft_delete_patient():
    created = client.post("/patients", json=VALID_PATIENT).json()["data"]
    resp = client.delete(f"/patients/{created['patient_id']}")
    assert resp.status_code == 200
    resp = client.get(f"/patients/{created['patient_id']}")
    assert resp.status_code == 404


def test_persistence_across_query():
    client.post("/patients", json=VALID_PATIENT)
    resp = client.get("/patients", params={"phone_number": "5551234567"})
    assert len(resp.json()["data"]) == 1


def test_duplicate_phone_lookup_tool():
    client.post("/patients", json=VALID_PATIENT)
    resp = client.post(
        "/vapi/tools",
        json={
            "message": {
                "toolCalls": [
                    {
                        "id": "call_1",
                        "function": {
                            "name": "lookup_patient_by_phone",
                            "arguments": {"phone_number": "5551234567"},
                        },
                    }
                ]
            }
        },
    )
    assert resp.status_code == 200
    result = resp.json()["results"][0]["result"]
    assert result["found"] is True
    assert result["last_name"] == "Doe"


def test_lookup_patient_by_phone_not_found():
    resp = client.post(
        "/vapi/tools",
        json={
            "message": {
                "toolCalls": [
                    {
                        "id": "call_1",
                        "function": {
                            "name": "lookup_patient_by_phone",
                            "arguments": {"phone_number": "5550000000"},
                        },
                    }
                ]
            }
        },
    )
    assert resp.status_code == 200
    result = resp.json()["results"][0]["result"]
    assert result["success"] is True
    assert result["found"] is False


def test_create_patient_tool_call_invalid_dob_does_not_crash():
    """Agent submits a future DOB; webhook must return success:false, not 500 or raise."""
    args = {**VALID_PATIENT, "date_of_birth": "2999-01-01", "phone_number": "5551112222"}
    resp = client.post(
        "/vapi/tools",
        json={"message": {"toolCalls": [{"id": "c1", "function": {"name": "create_patient", "arguments": args}}]}},
    )
    assert resp.status_code == 200
    result = resp.json()["results"][0]["result"]
    assert result["success"] is False
    assert "date_of_birth" in result["error"]
    # confirm nothing was persisted
    assert len(client.get("/patients", params={"phone_number": "5551112222"}).json()["data"]) == 0


def test_create_patient_tool_call_missing_required_field():
    args = {k: v for k, v in VALID_PATIENT.items() if k != "state"}
    resp = client.post(
        "/vapi/tools",
        json={"message": {"toolCalls": [{"id": "c1", "function": {"name": "create_patient", "arguments": args}}]}},
    )
    assert resp.status_code == 200
    result = resp.json()["results"][0]["result"]
    assert result["success"] is False


def test_create_patient_tool_call_invalid_phone_does_not_crash():
    args = {**VALID_PATIENT, "phone_number": "123"}
    resp = client.post(
        "/vapi/tools",
        json={"message": {"toolCalls": [{"id": "c1", "function": {"name": "create_patient", "arguments": args}}]}},
    )
    assert resp.status_code == 200
    result = resp.json()["results"][0]["result"]
    assert result["success"] is False
    assert "phone_number" in result["error"]


def test_update_patient_tool_call_unknown_patient_id():
    resp = client.post(
        "/vapi/tools",
        json={
            "message": {
                "toolCalls": [
                    {
                        "id": "c1",
                        "function": {
                            "name": "update_patient",
                            "arguments": {"patient_id": "does-not-exist", "city": "Dallas"},
                        },
                    }
                ]
            }
        },
    )
    assert resp.status_code == 200
    result = resp.json()["results"][0]["result"]
    assert result["success"] is False
    assert "not found" in result["error"].lower()


def test_update_patient_tool_call_missing_patient_id():
    resp = client.post(
        "/vapi/tools",
        json={
            "message": {
                "toolCalls": [
                    {"id": "c1", "function": {"name": "update_patient", "arguments": {"city": "Dallas"}}}
                ]
            }
        },
    )
    assert resp.status_code == 200
    result = resp.json()["results"][0]["result"]
    assert result["success"] is False


def test_update_patient_tool_call_success():
    created = client.post("/patients", json=VALID_PATIENT).json()["data"]
    resp = client.post(
        "/vapi/tools",
        json={
            "message": {
                "toolCalls": [
                    {
                        "id": "c1",
                        "function": {
                            "name": "update_patient",
                            "arguments": {"patient_id": created["patient_id"], "city": "Dallas"},
                        },
                    }
                ]
            }
        },
    )
    assert resp.status_code == 200
    result = resp.json()["results"][0]["result"]
    assert result["success"] is True
    updated = client.get(f"/patients/{created['patient_id']}").json()["data"]
    assert updated["city"] == "Dallas"


def test_unknown_tool_name_does_not_crash():
    resp = client.post(
        "/vapi/tools",
        json={"message": {"toolCalls": [{"id": "c1", "function": {"name": "delete_everything", "arguments": {}}}]}},
    )
    assert resp.status_code == 200
    result = resp.json()["results"][0]["result"]
    assert result["success"] is False


def test_malformed_empty_toolcalls_body_does_not_crash():
    resp = client.post("/vapi/tools", json={"message": {}})
    assert resp.status_code == 200
    assert resp.json()["results"] == []


def test_multiple_tool_calls_in_one_request():
    """A single Vapi webhook call can carry multiple toolCalls; each must resolve independently."""
    resp = client.post(
        "/vapi/tools",
        json={
            "message": {
                "toolCalls": [
                    {
                        "id": "c1",
                        "function": {
                            "name": "lookup_patient_by_phone",
                            "arguments": {"phone_number": "5559999999"},
                        },
                    },
                    {
                        "id": "c2",
                        "function": {"name": "lookup_patient_by_phone", "arguments": {"phone_number": "123"}},
                    },
                ]
            }
        },
    )
    assert resp.status_code == 200
    results = resp.json()["results"]
    assert len(results) == 2
    assert results[0]["toolCallId"] == "c1"
    assert results[1]["toolCallId"] == "c2"


def test_get_available_appointment_slots():
    resp = client.post(
        "/vapi/tools",
        json={
            "message": {
                "toolCalls": [
                    {"id": "c1", "function": {"name": "get_available_appointment_slots", "arguments": {}}}
                ]
            }
        },
    )
    assert resp.status_code == 200
    result = resp.json()["results"][0]["result"]
    assert result["success"] is True
    assert len(result["slots"]) > 0
    assert "date" in result["slots"][0] and "time" in result["slots"][0]


def test_schedule_appointment_tool_call_success():
    created = client.post("/patients", json=VALID_PATIENT).json()["data"]
    from datetime import date, timedelta

    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    resp = client.post(
        "/vapi/tools",
        json={
            "message": {
                "toolCalls": [
                    {
                        "id": "c1",
                        "function": {
                            "name": "schedule_appointment",
                            "arguments": {
                                "patient_id": created["patient_id"],
                                "appointment_date": tomorrow,
                                "appointment_time": "09:00",
                                "reason": "Annual checkup",
                            },
                        },
                    }
                ]
            }
        },
    )
    assert resp.status_code == 200
    result = resp.json()["results"][0]["result"]
    assert result["success"] is True
    assert result["appointment_id"]

    appts = client.get(f"/patients/{created['patient_id']}/appointments").json()["data"]
    assert len(appts) == 1
    assert appts[0]["reason"] == "Annual checkup"


def test_schedule_appointment_unknown_patient():
    resp = client.post(
        "/vapi/tools",
        json={
            "message": {
                "toolCalls": [
                    {
                        "id": "c1",
                        "function": {
                            "name": "schedule_appointment",
                            "arguments": {
                                "patient_id": "does-not-exist",
                                "appointment_date": "2099-01-01",
                                "appointment_time": "09:00",
                            },
                        },
                    }
                ]
            }
        },
    )
    assert resp.status_code == 200
    result = resp.json()["results"][0]["result"]
    assert result["success"] is False


def test_schedule_appointment_invalid_time_format():
    created = client.post("/patients", json=VALID_PATIENT).json()["data"]
    resp = client.post(
        "/vapi/tools",
        json={
            "message": {
                "toolCalls": [
                    {
                        "id": "c1",
                        "function": {
                            "name": "schedule_appointment",
                            "arguments": {
                                "patient_id": created["patient_id"],
                                "appointment_date": "2099-01-01",
                                "appointment_time": "9am",
                            },
                        },
                    }
                ]
            }
        },
    )
    assert resp.status_code == 200
    result = resp.json()["results"][0]["result"]
    assert result["success"] is False


def test_call_event_end_of_call_report_stores_transcript():
    created = client.post("/patients", json=VALID_PATIENT).json()["data"]
    resp = client.post(
        "/vapi/call-events",
        json={
            "message": {
                "type": "end-of-call-report",
                "call": {"id": "call_abc123"},
                "transcript": "AI: Hi... User: Hi, I'd like to register...",
                "summary": "Registered new patient Jane Doe.",
                "endedReason": "assistant-ended-call",
                "metadata": {"patient_id": created["patient_id"]},
            }
        },
    )
    assert resp.status_code == 200

    calls = client.get(f"/patients/{created['patient_id']}/calls").json()["data"]
    assert len(calls) == 1
    assert calls[0]["vapi_call_id"] == "call_abc123"
    assert "Jane Doe" in calls[0]["summary"]


def test_call_event_links_transcript_to_patient_from_tool_calls():
    # Real Vapi end-of-call reports carry no patient_id; the link comes from
    # the create_patient tool call made earlier in the same call.
    created = client.post(
        "/vapi/tools",
        json={
            "message": {
                "call": {"id": "call_live_1"},
                "toolCalls": [
                    {
                        "id": "tc_1",
                        "function": {"name": "create_patient", "arguments": VALID_PATIENT},
                    }
                ],
            }
        },
    ).json()["results"][0]["result"]
    assert created["success"] is True

    resp = client.post(
        "/vapi/call-events",
        json={
            "message": {
                "type": "end-of-call-report",
                "call": {"id": "call_live_1"},
                "artifact": {"transcript": "AI: Hi... User: I'd like to register."},
                "analysis": {"summary": "Registered Jane Doe."},
                "endedReason": "assistant-ended-call",
            }
        },
    )
    assert resp.status_code == 200

    calls = client.get(f"/patients/{created['patient_id']}/calls").json()["data"]
    assert len(calls) == 1
    assert calls[0]["vapi_call_id"] == "call_live_1"
    assert calls[0]["transcript"].startswith("AI: Hi")
    assert calls[0]["summary"] == "Registered Jane Doe."
    assert calls[0]["ended_reason"] == "assistant-ended-call"


def test_call_event_ignores_non_end_of_call_messages():
    resp = client.post(
        "/vapi/call-events",
        json={"message": {"type": "speech-update"}},
    )
    assert resp.status_code == 200


def test_dashboard_renders_html():
    client.post("/patients", json=VALID_PATIENT)
    resp = client.get("/dashboard")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "Jane" in resp.text
    assert "Doe" in resp.text


def test_dashboard_empty_state():
    resp = client.get("/dashboard")
    assert resp.status_code == 200
    assert "No patients registered yet" in resp.text
