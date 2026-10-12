import json
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from app.database import get_connection
from app.routers.auth import require_admin
from app.schemas.admin import AppointmentOffersCreate
from app.schemas.user import UserResponse
from app.time_utils import parse_timestamp, scheduling_resource, utc_now, utc_timestamp

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/consultations")
def consultation_queue(admin: UserResponse = Depends(require_admin)):
	with get_connection() as connection:
		rows = connection.execute(
			"""
			SELECT consultations.*, users.name AS patient_name, users.email AS patient_email
			FROM consultations JOIN users ON users.id = consultations.patient_id
			ORDER BY consultations.created_at DESC
			"""
		).fetchall()
		results = []
		for row in rows:
			images = connection.execute(
				"SELECT id, filename FROM consultation_images WHERE consultation_id = ? ORDER BY created_at",
				(row["id"],),
			).fetchall()
			offers = connection.execute(
				"SELECT id, starts_at, department, location, status FROM appointment_offers WHERE consultation_id = ? ORDER BY starts_at",
				(row["id"],),
			).fetchall()
			appointment = connection.execute(
				"SELECT id, starts_at, department, location, status FROM appointments "
				"WHERE consultation_id = ? ORDER BY created_at DESC LIMIT 1",
				(row["id"],),
			).fetchone()
			results.append(
				{
					"id": row["id"],
					"patient": {"name": row["patient_name"], "email": row["patient_email"]},
					"symptoms": json.loads(row["symptoms"]),
					"duration": row["duration"],
					"impact": row["impact"],
					"history": row["history"],
					"medicines": row["medicines"],
					"notes": row["notes"],
					"created_at": row["created_at"],
					"images": [dict(image) for image in images],
					"offers": [dict(offer) for offer in offers],
					"appointment": dict(appointment) if appointment else None,
				}
			)
	return results


@router.post("/consultations/{consultation_id}/offers")
def create_offers(
	consultation_id: str,
	payload: AppointmentOffersCreate,
	admin: UserResponse = Depends(require_admin),
):
	starts = []
	resources = []
	for offer in payload.offers:
		try:
			start = parse_timestamp(offer.starts_at)
		except ValueError as error:
			raise HTTPException(status_code=422, detail=str(error)) from error
		if start <= utc_now():
			raise HTTPException(status_code=422, detail="Appointment options must be in the future.")
		starts.append(start)
		resources.append(scheduling_resource(offer.department, offer.location))
	if len(set(zip(starts, resources))) != len(starts):
		raise HTTPException(status_code=422, detail="Appointment options must have different resource and time combinations.")
	with get_connection() as connection:
		connection.execute("BEGIN IMMEDIATE")
		consultation = connection.execute(
			"SELECT id FROM consultations WHERE id = ?", (consultation_id,)
		).fetchone()
		if not consultation:
			raise HTTPException(status_code=404, detail="Consultation not found.")
		booked = connection.execute(
			"SELECT id FROM appointments WHERE consultation_id = ? "
			"AND status IN ('confirmed', 'reschedule_requested')",
			(consultation_id,),
		).fetchone()
		previous = connection.execute(
			"SELECT status FROM appointments WHERE consultation_id = ? "
			"AND status IN ('cancelled', 'completed') LIMIT 1",
			(consultation_id,),
		).fetchone() if not booked else None
		if previous:
			raise HTTPException(
				status_code=409,
				detail="This consultation already has a finished appointment. The patient must submit a new pre-consultation for another visit.",
			)
		for start, resource_key in zip(starts, resources):
			if connection.execute(
				"SELECT id FROM appointments WHERE resource_key = ? AND starts_at = ? "
				"AND status != 'cancelled' AND (? IS NULL OR id != ?)",
				(
					resource_key,
					utc_timestamp(start),
					booked["id"] if booked else None,
					booked["id"] if booked else None,
				),
			).fetchone():
				raise HTTPException(status_code=409, detail="One or more offered resources are already booked at that time.")
		connection.execute(
			"UPDATE appointment_offers SET status = 'superseded' "
			"WHERE consultation_id = ? AND status != 'superseded'",
			(consultation_id,),
		)
		if booked:
			connection.execute(
				"UPDATE appointments SET status = 'reschedule_requested' WHERE id = ?",
				(booked["id"],),
			)
		offer_ids = []
		for offer, start, resource_key in zip(payload.offers, starts, resources):
			offer_id = str(uuid.uuid4())
			offer_ids.append(offer_id)
			connection.execute(
				"""
				INSERT INTO appointment_offers (id, consultation_id, starts_at, department, location, resource_key)
				VALUES (?, ?, ?, ?, ?, ?)
				""",
				(offer_id, consultation_id, utc_timestamp(start), offer.department, offer.location, resource_key),
			)
	return {"consultation_id": consultation_id, "offers": offer_ids}


@router.post("/appointments/{appointment_id}/cancel")
def cancel_admin_appointment(
	appointment_id: str,
	admin: UserResponse = Depends(require_admin),
):
	with get_connection() as connection:
		connection.execute("BEGIN IMMEDIATE")
		appointment = connection.execute(
			"SELECT id, consultation_id, status FROM appointments WHERE id = ?",
			(appointment_id,),
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
	return {"id": appointment_id, "status": "cancelled"}


@router.post("/appointments/{appointment_id}/complete")
def complete_admin_appointment(
	appointment_id: str,
	admin: UserResponse = Depends(require_admin),
):
	with get_connection() as connection:
		connection.execute("BEGIN IMMEDIATE")
		appointment = connection.execute(
			"SELECT id, starts_at, status FROM appointments WHERE id = ?",
			(appointment_id,),
		).fetchone()
		if not appointment:
			raise HTTPException(status_code=404, detail="Appointment not found.")
		if appointment["status"] != "confirmed":
			raise HTTPException(status_code=409, detail="Only confirmed appointments can be completed.")
		if parse_timestamp(appointment["starts_at"]) > utc_now():
			raise HTTPException(status_code=409, detail="An appointment cannot be completed before its scheduled time.")
		connection.execute(
			"UPDATE appointments SET status = 'completed' WHERE id = ?",
			(appointment_id,),
		)
	return {"id": appointment_id, "status": "completed"}


@router.get("/consultations/{consultation_id}/images/{image_id}")
def view_image(
	consultation_id: str,
	image_id: str,
	admin: UserResponse = Depends(require_admin),
):
	with get_connection() as connection:
		row = connection.execute(
			"SELECT path, content_type FROM consultation_images WHERE id = ? AND consultation_id = ?",
			(image_id, consultation_id),
		).fetchone()
	if not row:
		raise HTTPException(status_code=404, detail="Image not found.")
	path = Path(row["path"])
	if not path.is_file():
		raise HTTPException(status_code=404, detail="Image file is missing.")
	return FileResponse(path, media_type=row["content_type"])
