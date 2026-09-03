import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app import crud
from app.database import get_db
from app.schemas import PatientCreate, PatientOut, PatientUpdate

logger = logging.getLogger("patients")
router = APIRouter(prefix="/patients", tags=["patients"])


def envelope(data=None, error=None):
    return {"data": data, "error": error}


@router.get("")
def list_patients(
    last_name: Optional[str] = Query(None),
    date_of_birth: Optional[str] = Query(None),
    phone_number: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    patients = crud.list_patients(db, last_name, date_of_birth, phone_number)
    return envelope(data=[PatientOut.model_validate(p).model_dump(mode="json") for p in patients])


@router.get("/{patient_id}")
def get_patient(patient_id: str, db: Session = Depends(get_db)):
    patient = crud.get_patient(db, patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    return envelope(data=PatientOut.model_validate(patient).model_dump(mode="json"))


@router.post("", status_code=201)
def create_patient(payload: PatientCreate, db: Session = Depends(get_db)):
    try:
        patient = crud.create_patient(db, payload)
    except Exception as exc:
        logger.exception("Failed to create patient")
        raise HTTPException(status_code=500, detail=f"Failed to save patient: {exc}")
    logger.info("Created patient %s %s (%s)", patient.first_name, patient.last_name, patient.patient_id)
    return envelope(data=PatientOut.model_validate(patient).model_dump(mode="json"))


@router.put("/{patient_id}")
def update_patient(patient_id: str, payload: PatientUpdate, db: Session = Depends(get_db)):
    patient = crud.get_patient(db, patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    try:
        patient = crud.update_patient(db, patient, payload)
    except Exception as exc:
        logger.exception("Failed to update patient")
        raise HTTPException(status_code=500, detail=f"Failed to update patient: {exc}")
    return envelope(data=PatientOut.model_validate(patient).model_dump(mode="json"))


@router.delete("/{patient_id}")
def delete_patient(patient_id: str, db: Session = Depends(get_db)):
    patient = crud.get_patient(db, patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    crud.soft_delete_patient(db, patient)
    return envelope(data={"patient_id": patient_id, "deleted": True})
