from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Patient, Sex


def seed_if_empty(db: Session) -> None:
    if db.scalar(select(Patient).limit(1)) is not None:
        return

    seed_patients = [
        Patient(
            first_name="Jane",
            last_name="Doe",
            date_of_birth=date(1990, 4, 12),
            sex=Sex.FEMALE,
            phone_number="5551234567",
            email="jane.doe@example.com",
            address_line_1="123 Main St",
            city="Austin",
            state="TX",
            zip_code="78701",
            preferred_language="English",
        ),
        Patient(
            first_name="Carlos",
            last_name="Martinez",
            date_of_birth=date(1985, 11, 2),
            sex=Sex.MALE,
            phone_number="5559876543",
            address_line_1="456 Oak Ave",
            city="San Diego",
            state="CA",
            zip_code="92101",
            preferred_language="Spanish",
        ),
    ]
    db.add_all(seed_patients)
    db.commit()
