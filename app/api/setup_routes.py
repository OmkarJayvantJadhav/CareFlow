"""Hospital setup for admins (phase 7B): the hospital's details, departments, doctors and their timetables."""

from datetime import date, time

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import Auth, get_auth, get_db, run_and_commit
from app.tools import hospital

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


class Profile(BaseModel):
    name: dict[str, str] = Field(default_factory=dict)
    address: str = Field("", max_length=200)
    phone: str = Field("", max_length=30)
    reception_opens: time
    reception_closes: time
    emergency_note: dict[str, str] = Field(default_factory=dict)


class NewDepartment(BaseModel):
    name: str = Field(max_length=80)
    floor: int
    opd_start: time
    opd_end: time
    aliases: list[str] = Field(default_factory=list, max_length=40)


class DepartmentChange(BaseModel):
    name: str | None = Field(None, max_length=80)
    floor: int | None = None
    opd_start: time | None = None
    opd_end: time | None = None
    aliases: list[str] | None = Field(None, max_length=40)


class NewDoctor(BaseModel):
    name: str = Field(max_length=120)
    department_id: int
    languages: list[str] = Field(max_length=3)
    opd_days: list[int] = Field(max_length=7)
    slot_minutes: int


class DoctorChange(BaseModel):
    name: str | None = Field(None, max_length=120)
    department_id: int | None = None
    languages: list[str] | None = Field(None, max_length=3)
    opd_days: list[int] | None = Field(None, max_length=7)
    slot_minutes: int | None = None


class LastDay(BaseModel):
    last_day: date | None = None


@router.get("/hospital")
def setup(auth: Auth = Depends(get_auth), db: Session = Depends(get_db)) -> dict:
    return hospital.hospital_setup(db, auth.actor)


@router.put("/hospital/profile")
def update_profile(body: Profile, auth: Auth = Depends(get_auth), db: Session = Depends(get_db)) -> dict:
    return run_and_commit(
        db,
        lambda: hospital.update_profile(
            db,
            auth.actor,
            body.name,
            body.address,
            body.phone,
            body.reception_opens,
            body.reception_closes,
            body.emergency_note,
        ),
    )


@router.post("/departments", status_code=201)
def create_department(body: NewDepartment, auth: Auth = Depends(get_auth), db: Session = Depends(get_db)) -> dict:
    return run_and_commit(
        db,
        lambda: hospital.create_department(
            db, auth.actor, body.name, body.floor, body.opd_start, body.opd_end, body.aliases
        ),
    )


@router.patch("/departments/{department_id}")
def update_department(
    department_id: int, body: DepartmentChange, auth: Auth = Depends(get_auth), db: Session = Depends(get_db)
) -> dict:
    return run_and_commit(
        db,
        lambda: hospital.update_department(
            db, auth.actor, department_id, body.name, body.floor, body.opd_start, body.opd_end, body.aliases
        ),
    )


@router.delete("/departments/{department_id}")
def delete_department(department_id: int, auth: Auth = Depends(get_auth), db: Session = Depends(get_db)) -> dict:
    return run_and_commit(db, lambda: hospital.delete_department(db, auth.actor, department_id))


@router.post("/doctors", status_code=201)
def create_doctor(body: NewDoctor, auth: Auth = Depends(get_auth), db: Session = Depends(get_db)) -> dict:
    return run_and_commit(
        db,
        lambda: hospital.create_doctor(
            db, auth.actor, body.name, body.department_id, body.languages, body.opd_days, body.slot_minutes
        ),
    )


@router.patch("/doctors/{doctor_id}")
def update_doctor(
    doctor_id: int, body: DoctorChange, auth: Auth = Depends(get_auth), db: Session = Depends(get_db)
) -> dict:
    return run_and_commit(
        db,
        lambda: hospital.update_doctor(
            db,
            auth.actor,
            doctor_id,
            body.name,
            body.department_id,
            body.languages,
            body.opd_days,
            body.slot_minutes,
        ),
    )


@router.put("/doctors/{doctor_id}/last-day")
def set_last_day(doctor_id: int, body: LastDay, auth: Auth = Depends(get_auth), db: Session = Depends(get_db)) -> dict:
    return run_and_commit(db, lambda: hospital.set_last_day(db, auth.actor, doctor_id, body.last_day))


@router.delete("/doctors/{doctor_id}")
def delete_doctor(doctor_id: int, auth: Auth = Depends(get_auth), db: Session = Depends(get_db)) -> dict:
    return run_and_commit(db, lambda: hospital.delete_doctor(db, auth.actor, doctor_id))
