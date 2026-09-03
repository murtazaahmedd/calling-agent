from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import crud
from app.database import get_db
from app.schemas import AppointmentOut, CallRecordOut

router = APIRouter(tags=["appointments"])


def envelope(data=None, error=None):
    return {"data": data, "error": error}


@router.get("/patients/{patient_id}/appointments")
def list_appointments(patient_id: str, db: Session = Depends(get_db)):
    patient = crud.get_patient(db, patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    appts = crud.list_appointments_for_patient(db, patient_id)
    return envelope(data=[AppointmentOut.model_validate(a).model_dump(mode="json") for a in appts])


@router.get("/patients/{patient_id}/calls")
def list_calls(patient_id: str, db: Session = Depends(get_db)):
    patient = crud.get_patient(db, patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    calls = crud.list_call_records_for_patient(db, patient_id)
    return envelope(data=[CallRecordOut.model_validate(c).model_dump(mode="json") for c in calls])
