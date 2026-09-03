import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, Date, DateTime, Enum as SAEnum, ForeignKey, Text
from sqlalchemy.orm import relationship
import enum

from app.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Sex(str, enum.Enum):
    MALE = "Male"
    FEMALE = "Female"
    OTHER = "Other"
    DECLINE = "Decline to Answer"


class Patient(Base):
    __tablename__ = "patients"

    patient_id = Column(String, primary_key=True, default=_uuid)

    first_name = Column(String(50), nullable=False)
    last_name = Column(String(50), nullable=False)
    date_of_birth = Column(Date, nullable=False)
    sex = Column(SAEnum(Sex), nullable=False)
    phone_number = Column(String(10), nullable=False, index=True)
    email = Column(String, nullable=True)

    address_line_1 = Column(String, nullable=False)
    address_line_2 = Column(String, nullable=True)
    city = Column(String(100), nullable=False)
    state = Column(String(2), nullable=False)
    zip_code = Column(String(10), nullable=False)

    insurance_provider = Column(String, nullable=True)
    insurance_member_id = Column(String, nullable=True)
    preferred_language = Column(String, nullable=False, default="English")
    emergency_contact_name = Column(String, nullable=True)
    emergency_contact_phone = Column(String(10), nullable=True)

    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=False)
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    appointments = relationship("Appointment", back_populates="patient", cascade="all, delete-orphan")
    calls = relationship("CallRecord", back_populates="patient", cascade="all, delete-orphan")


class Appointment(Base):
    """Mock appointment scheduling -- no real calendar/provider system behind this."""

    __tablename__ = "appointments"

    appointment_id = Column(String, primary_key=True, default=_uuid)
    patient_id = Column(String, ForeignKey("patients.patient_id"), nullable=False, index=True)
    appointment_date = Column(Date, nullable=False)
    appointment_time = Column(String(5), nullable=False)  # "HH:MM", 24h
    reason = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)

    patient = relationship("Patient", back_populates="appointments")


class CallRecord(Base):
    """Transcript/summary of a Vapi call, linked to the patient it registered/updated."""

    __tablename__ = "call_records"

    call_record_id = Column(String, primary_key=True, default=_uuid)
    patient_id = Column(String, ForeignKey("patients.patient_id"), nullable=True, index=True)
    vapi_call_id = Column(String, nullable=True, index=True)
    transcript = Column(Text, nullable=True)
    summary = Column(Text, nullable=True)
    ended_reason = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utcnow, nullable=False)

    patient = relationship("Patient", back_populates="calls")
