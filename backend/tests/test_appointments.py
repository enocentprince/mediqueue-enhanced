from datetime import timedelta
import uuid

from fastapi.testclient import TestClient

from app.database import get_connection
from app.time_utils import scheduling_resource, utc_now, utc_timestamp
from conftest import create_consultation, register


def add_offer(consultation_id, starts_at, status="offered", department="General medicine", location="Block B"):
	offer_id = str(uuid.uuid4())
	with get_connection() as connection:
		connection.execute(
			"INSERT INTO appointment_offers (id, consultation_id, starts_at, department, location, resource_key, status) "
			"VALUES (?, ?, ?, ?, ?, ?, ?)",
			(
				offer_id,
				consultation_id,
				utc_timestamp(starts_at),
				department,
				location,
				scheduling_resource(department, location),
				status,
			),
		)
	return offer_id


def test_future_offer_books_and_withdraws_alternatives(api):
	register(api)
	consultation, _ = create_consultation(api)
	selected = add_offer(consultation["id"], utc_now() + timedelta(days=2))
	alternative = add_offer(consultation["id"], utc_now() + timedelta(days=3))

	response = api.post(f"/appointments/offers/{selected}/select")
	assert response.status_code == 201
	assert response.json()["starts_at"].endswith("Z")
	assert api.get("/consultations/mine/latest").json()["appointment"]["id"] == response.json()["id"]
	with get_connection() as connection:
		statuses = {
			row["id"]: row["status"]
			for row in connection.execute(
				"SELECT id, status FROM appointment_offers WHERE id IN (?, ?)",
				(selected, alternative),
			)
		}
	assert statuses == {selected: "selected", alternative: "withdrawn"}


def test_expired_offer_is_rejected_without_withdrawing_alternative(api):
	register(api)
	consultation, _ = create_consultation(api)
	expired = add_offer(consultation["id"], utc_now() - timedelta(minutes=1))
	alternative = add_offer(consultation["id"], utc_now() + timedelta(days=1))

	response = api.post(f"/appointments/offers/{expired}/select")
	assert response.status_code == 410
	with get_connection() as connection:
		assert connection.execute("SELECT COUNT(*) FROM appointments").fetchone()[0] == 0
		assert connection.execute(
			"SELECT status FROM appointment_offers WHERE id = ?", (alternative,)
		).fetchone()["status"] == "offered"


def test_selected_and_withdrawn_offers_are_unavailable(api):
	register(api)
	consultation, _ = create_consultation(api)
	for offer_status, expected_message in (
		("selected", "already been selected"),
		("withdrawn", "no longer available"),
	):
		offer_id = add_offer(
			consultation["id"], utc_now() + timedelta(days=2), status=offer_status,
			location=f"{offer_status} room",
		)
		response = api.post(f"/appointments/offers/{offer_id}/select")
		assert response.status_code == 409
		assert expected_message in response.json()["detail"]


def test_offer_for_another_patient_is_hidden(api):
	register(api, "owner")
	consultation, _ = create_consultation(api)
	offer_id = add_offer(consultation["id"], utc_now() + timedelta(days=2))
	other = TestClient(api.app)
	register(other, "other")
	assert other.post(f"/appointments/offers/{offer_id}/select").status_code == 404


def test_independent_resources_can_share_a_timestamp(api):
	shared_time = utc_now() + timedelta(days=2)
	appointments = []
	for prefix, department, location in (
		("one", "General medicine", "Block B"),
		("two", "Dermatology", "Block C"),
	):
		client = TestClient(api.app)
		register(client, prefix)
		consultation, _ = create_consultation(client)
		offer_id = add_offer(consultation["id"], shared_time, department=department, location=location)
		response = client.post(f"/appointments/offers/{offer_id}/select")
		assert response.status_code == 201, response.text
		appointments.append(response.json()["id"])
	assert len(set(appointments)) == 2


def test_same_resource_cannot_be_double_booked(api):
	shared_time = utc_now() + timedelta(days=2)
	clients_and_offers = []
	for prefix in ("first", "second"):
		client = TestClient(api.app)
		register(client, prefix)
		consultation, _ = create_consultation(client)
		clients_and_offers.append(
			(client, add_offer(consultation["id"], shared_time))
		)
	assert clients_and_offers[0][0].post(
		f"/appointments/offers/{clients_and_offers[0][1]}/select"
	).status_code == 201
	conflict = clients_and_offers[1][0].post(
		f"/appointments/offers/{clients_and_offers[1][1]}/select"
	)
	assert conflict.status_code == 409
	with get_connection() as connection:
		assert connection.execute(
			"SELECT status FROM appointment_offers WHERE id = ?",
			(clients_and_offers[1][1],),
		).fetchone()["status"] == "offered"


def test_patient_cancellation_releases_appointment_time(api):
	patient = register(api, "cancelling")
	consultation, _ = create_consultation(api)
	shared_time = utc_now() + timedelta(days=4)
	offer_id = add_offer(consultation["id"], shared_time)
	booking = api.post(f"/appointments/offers/{offer_id}/select")
	assert booking.status_code == 201

	cancelled = api.post(f"/appointments/{booking.json()['id']}/cancel")
	assert cancelled.status_code == 200
	assert api.get("/appointments").json()[0]["status"] == "cancelled"
	assert cancelled.json()["status"] == "cancelled"
	assert api.post(f"/appointments/{booking.json()['id']}/cancel").status_code == 409

	other = TestClient(api.app)
	register(other, "replacement")
	other_consultation, _ = create_consultation(other)
	rebook_offer = add_offer(other_consultation["id"], shared_time)
	rebooked = other.post(f"/appointments/offers/{rebook_offer}/select")
	assert rebooked.status_code == 201, rebooked.text


def test_patient_reschedule_request_and_offer_selection_update_existing_booking(api):
	register(api, "reschedule")
	consultation, _ = create_consultation(api)
	original_time = utc_now() + timedelta(days=4)
	original_offer = add_offer(consultation["id"], original_time)
	booking = api.post(f"/appointments/offers/{original_offer}/select")
	assert booking.status_code == 201

	requested = api.post(
		f"/appointments/{booking.json()['id']}/reschedule-request"
	)
	assert requested.status_code == 200
	assert requested.json()["status"] == "reschedule_requested"
	with get_connection() as connection:
		connection.execute(
			"UPDATE users SET role = 'admin' WHERE email = ?",
			("reschedule-" + api.cookies.get("mediqueue_session", "") + "@example.com",),
		)
		# Promote the signed-in patient using their consultation's owner ID.
		connection.execute(
			"UPDATE users SET role = 'admin' WHERE id = "
			"(SELECT patient_id FROM consultations WHERE id = ?)",
			(consultation["id"],),
		)

	replacement_time = utc_now() + timedelta(days=7)
	following_time = utc_now() + timedelta(days=8)
	published = api.post(
		f"/admin/consultations/{consultation['id']}/offers",
		json={
			"offers": [
				{
					"starts_at": utc_timestamp(replacement_time),
					"department": "General medicine",
					"location": "Block B",
				},
				{
					"starts_at": utc_timestamp(following_time),
					"department": "General medicine",
					"location": "Block B",
				},
			]
		},
	)
	assert published.status_code == 200, published.text
	rebooked = api.post(f"/appointments/offers/{published.json()['offers'][0]}/select")
	assert rebooked.status_code == 201, rebooked.text
	assert rebooked.json()["id"] == booking.json()["id"]
	assert rebooked.json()["status"] == "confirmed"
	assert rebooked.json()["starts_at"] == utc_timestamp(replacement_time)
	with get_connection() as connection:
		assert connection.execute(
			"SELECT COUNT(*) FROM appointments WHERE consultation_id = ?",
			(consultation["id"],),
		).fetchone()[0] == 1


def test_admin_can_cancel_appointment(api):
	patient = register(api, "admin-cancel")
	consultation, _ = create_consultation(api)
	offer_id = add_offer(consultation["id"], utc_now() + timedelta(days=3))
	booking = api.post(f"/appointments/offers/{offer_id}/select")
	assert booking.status_code == 201
	with get_connection() as connection:
		connection.execute("UPDATE users SET role = 'admin' WHERE id = ?", (patient["id"],))

	cancelled = api.post(f"/admin/appointments/{booking.json()['id']}/cancel")
	assert cancelled.status_code == 200
	assert cancelled.json()["status"] == "cancelled"


def test_appointment_history_and_admin_completion(api):
	patient = register(api, "history")
	consultation, _ = create_consultation(api)
	offer_id = add_offer(consultation["id"], utc_now() + timedelta(days=2))
	booking = api.post(f"/appointments/offers/{offer_id}/select")
	assert booking.status_code == 201
	assert api.get("/appointments").json() == [booking.json()]

	with get_connection() as connection:
		connection.execute(
			"UPDATE users SET role = 'admin' WHERE id = ?", (patient["id"],)
		)
	assert api.post(
		f"/admin/appointments/{booking.json()['id']}/complete"
	).status_code == 409
	with get_connection() as connection:
		connection.execute(
			"UPDATE appointments SET starts_at = ? WHERE id = ?",
			(utc_timestamp(utc_now() - timedelta(minutes=1)), booking.json()["id"]),
		)

	completed = api.post(f"/admin/appointments/{booking.json()['id']}/complete")
	assert completed.status_code == 200
	assert completed.json()["status"] == "completed"
	assert api.get("/appointments").json()[0]["status"] == "completed"
	assert api.post(f"/admin/appointments/{booking.json()['id']}/cancel").status_code == 409


def test_completed_or_cancelled_consultation_requires_a_new_preconsultation(api):
	register(api, "independent")
	consultation, _ = create_consultation(api)
	first_offer = add_offer(consultation["id"], utc_now() + timedelta(days=2))
	booking = api.post(f"/appointments/offers/{first_offer}/select")
	assert booking.status_code == 201
	cancelled = api.post(f"/appointments/{booking.json()['id']}/cancel")
	assert cancelled.status_code == 200

	second_offer = add_offer(consultation["id"], utc_now() + timedelta(days=3))
	rebook = api.post(f"/appointments/offers/{second_offer}/select")
	assert rebook.status_code == 409
	assert "new pre-consultation" in rebook.json()["detail"]
	assert len(api.get("/appointments").json()) == 1
	new_consultation, _ = create_consultation(api)
	independent_offer = add_offer(
		new_consultation["id"], utc_now() + timedelta(days=4)
	)
	independent_booking = api.post(
		f"/appointments/offers/{independent_offer}/select"
	)
	assert independent_booking.status_code == 201
	assert independent_booking.json()["consultation_id"] == new_consultation["id"]
	assert len(api.get("/appointments").json()) == 2


def test_admin_offer_normalizes_offset_to_utc(api):
	patient = register(api)
	consultation, _ = create_consultation(api)
	with get_connection() as connection:
		connection.execute("UPDATE users SET role = 'admin' WHERE id = ?", (patient["id"],))
	payload = {
		"offers": [
			{"starts_at": "2035-06-01T12:00:00+02:00", "department": "General medicine", "location": "Block B"},
			{"starts_at": "2035-06-02T12:00:00+02:00", "department": "General medicine", "location": "Block B"},
		]
	}
	response = api.post(f"/admin/consultations/{consultation['id']}/offers", json=payload)
	assert response.status_code == 200, response.text
	with get_connection() as connection:
		stored = connection.execute(
			"SELECT starts_at FROM appointment_offers WHERE consultation_id = ? ORDER BY starts_at",
			(consultation["id"],),
		).fetchall()
	assert [row["starts_at"] for row in stored] == ["2035-06-01T10:00:00Z", "2035-06-02T10:00:00Z"]


def test_admin_rejects_timezone_naive_offer(api):
	patient = register(api)
	consultation, _ = create_consultation(api)
	with get_connection() as connection:
		connection.execute("UPDATE users SET role = 'admin' WHERE id = ?", (patient["id"],))
	response = api.post(
		f"/admin/consultations/{consultation['id']}/offers",
		json={"offers": [
			{"starts_at": "2035-06-01T12:00:00", "department": "General medicine", "location": "Block B"},
			{"starts_at": "2035-06-02T12:00:00Z", "department": "General medicine", "location": "Block B"},
		]},
	)
	assert response.status_code == 422
	assert "timezone" in response.json()["detail"]
