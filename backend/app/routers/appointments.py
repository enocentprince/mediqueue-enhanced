import uuid
import sqlite3

from fastapi import APIRouter, Depends, HTTPException, status

from app.database import get_connection
from app.routers.auth import get_current_user
from app.schemas.appointment import AppointmentResponse
from app.schemas.user import UserResponse
from app.time_utils import parse_timestamp, utc_now

router = APIRouter(prefix="/appointments", tags=["appointments"])


def to_response(row) -> AppointmentResponse:
	return AppointmentResponse(
		id=row["id"],
		consultation_id=row["consultation_id"],
		slot_id=row["slot_id"],
		starts_at=row["starts_at"],
		department=row["department"],
		location=row["location"],
		status=row["status"],
	)


@router.get("/offers")
def list_patient_offers(
	consultation_id: str,
	user: UserResponse = Depends(get_current_user),
):
	with get_connection() as connection:
		consultation = connection.execute(
			"SELECT id FROM consultations WHERE id = ? AND patient_id = ?",
			(consultation_id, user.id),
		).fetchone()
		if not consultation:
			raise HTTPException(status_code=404, detail="Consultation not found.")
		rows = connection.execute(
			"SELECT id, starts_at, department, location FROM appointment_offers "
			"WHERE consultation_id = ? AND status = 'offered' ORDER BY starts_at",
			(consultation_id,),
		).fetchall()
	return [dict(row) for row in rows if parse_timestamp(row["starts_at"]) > utc_now()]


@router.post("/offers/{offer_id}/select", response_model=AppointmentResponse, status_code=status.HTTP_201_CREATED)
def select_appointment_offer(
	offer_id: str,
	user: UserResponse = Depends(get_current_user),
):
	with get_connection() as connection:
		connection.execute("BEGIN IMMEDIATE")
		offer = connection.execute(
			"""
			SELECT appointment_offers.* FROM appointment_offers
			JOIN consultations ON consultations.id = appointment_offers.consultation_id
			WHERE appointment_offers.id = ? AND consultations.patient_id = ?
			""",
			(offer_id, user.id),
		).fetchone()
		if not offer or offer["status"] != "offered":
			if not offer:
				raise HTTPException(status_code=404, detail="Appointment option not found.")
			if offer["status"] == "selected":
				raise HTTPException(status_code=409, detail="That appointment option has already been selected.")
			raise HTTPException(status_code=409, detail="That appointment option is no longer available.")
		if parse_timestamp(offer["starts_at"]) <= utc_now():
			raise HTTPException(status_code=410, detail="That appointment option has expired. Ask your care team for another option.")
		current = connection.execute(
			"SELECT id FROM appointments WHERE consultation_id = ? "
			"AND status IN ('confirmed', 'reschedule_requested')",
			(offer["consultation_id"],),
		).fetchone()
		if not current:
			previous = connection.execute(
				"SELECT status FROM appointments WHERE consultation_id = ? "
				"AND status IN ('cancelled', 'completed') LIMIT 1",
				(offer["consultation_id"],),
			).fetchone()
			if previous:
				raise HTTPException(
					status_code=409,
					detail="This consultation already has a finished appointment. Submit a new pre-consultation to book another visit.",
				)
		if connection.execute(
			"SELECT id FROM appointments WHERE resource_key = ? AND starts_at = ? "
			"AND status != 'cancelled' AND (? IS NULL OR id != ?)",
			(
				offer["resource_key"],
				offer["starts_at"],
				current["id"] if current else None,
				current["id"] if current else None,
			),
		).fetchone():
			raise HTTPException(status_code=409, detail="That scheduling resource was just booked. Ask your care team for another option.")
		appointment_id = current["id"] if current else str(uuid.uuid4())
		try:
			if current:
				connection.execute(
					"""
					UPDATE appointments
					SET slot_id = ?, starts_at = ?, department = ?, location = ?,
						resource_key = ?, status = 'confirmed'
					WHERE id = ?
					""",
					(
						f"offer:{offer_id}",
						offer["starts_at"],
						offer["department"],
						offer["location"],
						offer["resource_key"],
						appointment_id,
					),
				)
			else:
				connection.execute(
					"""
					INSERT INTO appointments
					(id, patient_id, consultation_id, slot_id, starts_at, department, location, resource_key)
					VALUES (?, ?, ?, ?, ?, ?, ?, ?)
					""",
					(
						appointment_id,
						user.id,
						offer["consultation_id"],
						f"offer:{offer_id}",
						offer["starts_at"],
						offer["department"],
						offer["location"],
						offer["resource_key"],
					),
				)
		except sqlite3.IntegrityError as error:
			raise HTTPException(
				status_code=409,
				detail="That appointment is no longer available.",
			) from error
		connection.execute(
			"UPDATE appointment_offers SET status = 'selected' WHERE id = ?",
			(offer_id,),
		)
		connection.execute(
			"UPDATE appointment_offers SET status = 'withdrawn' WHERE consultation_id = ? AND id != ? AND status = 'offered'",
			(offer["consultation_id"], offer_id),
		)
		row = connection.execute(
			"SELECT * FROM appointments WHERE id = ?", (appointment_id,)
		).fetchone()
	return to_response(row)


@router.post("/{appointment_id}/cancel", response_model=AppointmentResponse)
def cancel_patient_appointment(
	appointment_id: str,
	user: UserResponse = Depends(get_current_user),
):
	with get_connection() as connection:
		connection.execute("BEGIN IMMEDIATE")
		appointment = connection.execute(
			"SELECT * FROM appointments WHERE id = ? AND patient_id = ?",
			(appointment_id, user.id),
		).fetchone()
		if not appointment:
			raise HTTPException(status_code=404, detail="Appointment not found.")
		if appointment["status"] == "cancelled":
			raise HTTPException(status_code=409, detail="This appointment has already been cancelled.")
		if appointment["status"] not in {"confirmed", "reschedule_requested"}:
			raise HTTPException(status_code=409, detail="This appointment can no longer be cancelled.")
		connection.execute(
			"UPDATE appointments SET status = 'cancelled' WHERE id = ?",
			(appointment_id,),
		)
		connection.execute(
			"UPDATE appointment_offers SET status = 'withdrawn' "
			"WHERE consultation_id = ? AND status = 'offered'",
			(appointment["consultation_id"],),
		)
		row = connection.execute(
			"SELECT * FROM appointments WHERE id = ?", (appointment_id,)
		).fetchone()
	return to_response(row)


@router.post("/{appointment_id}/reschedule-request", response_model=AppointmentResponse)
def request_patient_reschedule(
	appointment_id: str,
	user: UserResponse = Depends(get_current_user),
):
	with get_connection() as connection:
		connection.execute("BEGIN IMMEDIATE")
		appointment = connection.execute(
			"SELECT * FROM appointments WHERE id = ? AND patient_id = ?",
			(appointment_id, user.id),
		).fetchone()
		if not appointment:
			raise HTTPException(status_code=404, detail="Appointment not found.")
		if appointment["status"] != "confirmed":
			raise HTTPException(status_code=409, detail="This appointment cannot be rescheduled.")
		connection.execute(
			"UPDATE appointments SET status = 'reschedule_requested' WHERE id = ?",
			(appointment_id,),
		)
		row = connection.execute(
			"SELECT * FROM appointments WHERE id = ?", (appointment_id,)
		).fetchone()
	return to_response(row)


@router.get("", response_model=list[AppointmentResponse])
def list_appointments(user: UserResponse = Depends(get_current_user)):
	with get_connection() as connection:
		rows = connection.execute(
			"SELECT * FROM appointments WHERE patient_id = ? ORDER BY starts_at",
			(user.id,),
		).fetchall()
	return [to_response(row) for row in rows]
