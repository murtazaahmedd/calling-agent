import re
from datetime import date, datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, EmailStr, Field, field_validator, ConfigDict

NAME_RE = re.compile(r"^[A-Za-z]+([-' ][A-Za-z]+)*$")
US_STATES = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", "HI", "ID", "IL", "IN",
    "IA", "KS", "KY", "LA", "ME", "MD", "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV",
    "NH", "NJ", "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC", "SD", "TN",
    "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY", "DC",
}
ZIP_RE = re.compile(r"^\d{5}(-\d{4})?$")


class Sex(str, Enum):
    MALE = "Male"
    FEMALE = "Female"
    OTHER = "Other"
    DECLINE = "Decline to Answer"


def _validate_name(v: str, field: str) -> str:
    v = v.strip()
    if not (1 <= len(v) <= 50):
        raise ValueError(f"{field} must be 1-50 characters")
    if not NAME_RE.match(v):
        raise ValueError(f"{field} must contain only letters, hyphens, or apostrophes")
    return v


def _validate_phone(v: str, field: str) -> str:
    digits = re.sub(r"\D", "", v)
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    if len(digits) != 10:
        raise ValueError(f"{field} must be a valid U.S. 10-digit phone number")
    return digits


def _validate_dob(v: date) -> date:
    if v > date.today():
        raise ValueError("date_of_birth cannot be in the future")
    return v


def _validate_state(v: str) -> str:
    v = v.strip().upper()
    if v not in US_STATES:
        raise ValueError("state must be a valid 2-letter U.S. state abbreviation")
    return v


def _validate_zip(v: str) -> str:
    v = v.strip()
    if not ZIP_RE.match(v):
        raise ValueError("zip_code must be 5-digit or ZIP+4 U.S. format")
    return v


class PatientBase(BaseModel):
    first_name: str = Field(..., min_length=1, max_length=50)
    last_name: str = Field(..., min_length=1, max_length=50)
    date_of_birth: date
    sex: Sex
    phone_number: str
    email: Optional[EmailStr] = None
    address_line_1: str = Field(..., min_length=1)
    address_line_2: Optional[str] = None
    city: str = Field(..., min_length=1, max_length=100)
    state: str
    zip_code: str
    insurance_provider: Optional[str] = None
    insurance_member_id: Optional[str] = None
    preferred_language: Optional[str] = "English"
    emergency_contact_name: Optional[str] = None
    emergency_contact_phone: Optional[str] = None

    @field_validator("first_name")
    @classmethod
    def v_first_name(cls, v):
        return _validate_name(v, "first_name")

    @field_validator("last_name")
    @classmethod
    def v_last_name(cls, v):
        return _validate_name(v, "last_name")

    @field_validator("date_of_birth")
    @classmethod
    def v_dob(cls, v):
        return _validate_dob(v)

    @field_validator("phone_number")
    @classmethod
    def v_phone(cls, v):
        return _validate_phone(v, "phone_number")

    @field_validator("emergency_contact_phone")
    @classmethod
    def v_ec_phone(cls, v):
        if v is None or v == "":
            return None
        return _validate_phone(v, "emergency_contact_phone")

    @field_validator("state")
    @classmethod
    def v_state(cls, v):
        return _validate_state(v)

    @field_validator("zip_code")
    @classmethod
    def v_zip(cls, v):
        return _validate_zip(v)


class PatientCreate(PatientBase):
    pass


class PatientUpdate(BaseModel):
    """All fields optional for PUT partial updates."""

    first_name: Optional[str] = None
    last_name: Optional[str] = None
    date_of_birth: Optional[date] = None
    sex: Optional[Sex] = None
    phone_number: Optional[str] = None
    email: Optional[EmailStr] = None
    address_line_1: Optional[str] = None
    address_line_2: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    zip_code: Optional[str] = None
    insurance_provider: Optional[str] = None
    insurance_member_id: Optional[str] = None
    preferred_language: Optional[str] = None
    emergency_contact_name: Optional[str] = None
    emergency_contact_phone: Optional[str] = None

    @field_validator("first_name")
    @classmethod
    def v_first_name(cls, v):
        return None if v is None else _validate_name(v, "first_name")

    @field_validator("last_name")
    @classmethod
    def v_last_name(cls, v):
        return None if v is None else _validate_name(v, "last_name")

    @field_validator("date_of_birth")
    @classmethod
    def v_dob(cls, v):
        return None if v is None else _validate_dob(v)

    @field_validator("phone_number")
    @classmethod
    def v_phone(cls, v):
        return None if v is None else _validate_phone(v, "phone_number")

    @field_validator("emergency_contact_phone")
    @classmethod
    def v_ec_phone(cls, v):
        if v is None or v == "":
            return None
        return _validate_phone(v, "emergency_contact_phone")

    @field_validator("state")
    @classmethod
    def v_state(cls, v):
        return None if v is None else _validate_state(v)

    @field_validator("zip_code")
    @classmethod
    def v_zip(cls, v):
        return None if v is None else _validate_zip(v)


class PatientOut(PatientBase):
    model_config = ConfigDict(from_attributes=True)

    patient_id: str
    created_at: datetime
    updated_at: datetime
    deleted_at: Optional[datetime] = None


class Envelope(BaseModel):
    data: Optional[object] = None
    error: Optional[str] = None


TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


class AppointmentCreate(BaseModel):
    patient_id: str
    appointment_date: date
    appointment_time: str = Field(..., description="24h HH:MM")
    reason: Optional[str] = None

    @field_validator("appointment_time")
    @classmethod
    def v_time(cls, v):
        if not TIME_RE.match(v):
            raise ValueError("appointment_time must be 24h HH:MM format")
        return v

    @field_validator("appointment_date")
    @classmethod
    def v_date(cls, v):
        if v < date.today():
            raise ValueError("appointment_date cannot be in the past")
        return v


class AppointmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    appointment_id: str
    patient_id: str
    appointment_date: date
    appointment_time: str
    reason: Optional[str] = None
    created_at: datetime


class CallRecordCreate(BaseModel):
    patient_id: Optional[str] = None
    vapi_call_id: Optional[str] = None
    transcript: Optional[str] = None
    summary: Optional[str] = None
    ended_reason: Optional[str] = None


class CallRecordOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    call_record_id: str
    patient_id: Optional[str] = None
    vapi_call_id: Optional[str] = None
    transcript: Optional[str] = None
    summary: Optional[str] = None
    ended_reason: Optional[str] = None
    created_at: datetime
