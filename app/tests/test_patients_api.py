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
