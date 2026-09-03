from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Patient, Appointment, CallRecord
from app.schemas import PatientCreate, PatientUpdate, AppointmentCreate, CallRecordCreate


def create_patient(db: Session, payload: PatientCreate) -> Patient:
    patient = Patient(**payload.model_dump())
    db.add(patient)
    db.commit()
    db.refresh(patient)
    return patient


def get_patient(db: Session, patient_id: str) -> Optional[Patient]:
    stmt = select(Patient).where(Patient.patient_id == patient_id, Patient.deleted_at.is_(None))
    return db.scalar(stmt)


def find_by_phone(db: Session, phone_number: str) -> Optional[Patient]:
    stmt = select(Patient).where(Patient.phone_number == phone_number, Patient.deleted_at.is_(None))
    return db.scalar(stmt)


def list_patients(
    db: Session,
    last_name: Optional[str] = None,
    date_of_birth: Optional[str] = None,
    phone_number: Optional[str] = None,
) -> list[Patient]:
    stmt = select(Patient).where(Patient.deleted_at.is_(None))
    if last_name:
        stmt = stmt.where(Patient.last_name.ilike(last_name))
    if date_of_birth:
        stmt = stmt.where(Patient.date_of_birth == date_of_birth)
    if phone_number:
        stmt = stmt.where(Patient.phone_number == phone_number)
    stmt = stmt.order_by(Patient.created_at.desc())
    return list(db.scalars(stmt))


def update_patient(db: Session, patient: Patient, payload: PatientUpdate) -> Patient:
    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(patient, field, value)
    patient.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(patient)
    return patient


def soft_delete_patient(db: Session, patient: Patient) -> Patient:
    patient.deleted_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(patient)
    return patient


def create_appointment(db: Session, payload: AppointmentCreate) -> Appointment:
    appointment = Appointment(**payload.model_dump())
    db.add(appointment)
    db.commit()
    db.refresh(appointment)
    return appointment


def list_appointments_for_patient(db: Session, patient_id: str) -> list[Appointment]:
    stmt = (
        select(Appointment)
        .where(Appointment.patient_id == patient_id)
        .order_by(Appointment.appointment_date, Appointment.appointment_time)
    )
    return list(db.scalars(stmt))


def list_all_patients_including_deleted(db: Session) -> list[Patient]:
    stmt = select(Patient).order_by(Patient.created_at.desc())
    return list(db.scalars(stmt))


def create_call_record(db: Session, payload: CallRecordCreate) -> CallRecord:
    record = CallRecord(**payload.model_dump())
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def list_call_records_for_patient(db: Session, patient_id: str) -> list[CallRecord]:
    stmt = (
        select(CallRecord)
        .where(CallRecord.patient_id == patient_id)
        .order_by(CallRecord.created_at.desc())
    )
    return list(db.scalars(stmt))


def get_appointment_count(db: Session) -> int:
    return len(list(db.scalars(select(Appointment))))
