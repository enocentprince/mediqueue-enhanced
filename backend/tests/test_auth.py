from app import database


def test_admin_login_accepts_admin_password_and_rejects_incorrect_password(api, monkeypatch):
	monkeypatch.setenv("MEDIQUEUE_ADMIN_EMAIL", "admin@mediqueue.local")
	monkeypatch.setenv("MEDIQUEUE_ADMIN_PASSWORD", "Admin1")
	monkeypatch.setenv("MEDIQUEUE_COOKIE_SECURE", "false")
	database.initialize_database()

	response = api.post(
		"/auth/admin-login",
		json={"email": "admin@mediqueue.local", "password": "Admin1"},
	)

	assert response.status_code == 200
	assert response.json()["user"]["role"] == "admin"
	assert response.cookies.get("mediqueue_session")

	response = api.post(
		"/auth/admin-login",
		json={"email": "admin@mediqueue.local", "password": "incorrect"},
	)
	assert response.status_code == 401


def test_admin_accounts_are_created_by_admin_and_keep_their_own_password(
	api, monkeypatch
):
	monkeypatch.setenv("MEDIQUEUE_ADMIN_EMAIL", "admin@mediqueue.local")
	monkeypatch.setenv("MEDIQUEUE_ADMIN_PASSWORD", "Admin1")
	monkeypatch.setenv("MEDIQUEUE_COOKIE_SECURE", "false")
	database.initialize_database()
	payload = {
		"name": "New Admin",
		"email": "new-admin@example.com",
		"mobile": "0712345678",
		"password": "unique-password",
	}
	assert api.post("/admin/accounts", json=payload).status_code == 401

	admin_login = api.post(
		"/auth/admin-login",
		json={"email": "admin@mediqueue.local", "password": "Admin1"},
	)
	assert admin_login.status_code == 200
	created = api.post("/admin/accounts", json=payload)
	assert created.status_code == 201
	assert created.json()["name"] == "New Admin"
	assert created.json()["role"] == "admin"

	with database.get_connection() as connection:
		row = connection.execute(
			"SELECT mobile, password_hash FROM users WHERE email = ?",
			("new-admin@example.com",),
		).fetchone()
	assert row["mobile"] == "0712345678"
	assert row["password_hash"] != payload["password"]

	database.initialize_database()
	api.post("/auth/logout")
	login = api.post(
		"/auth/admin-login",
		json={"email": payload["email"], "password": payload["password"]},
	)
	assert login.status_code == 200
	assert login.json()["user"]["name"] == "New Admin"


def test_patient_cannot_create_admin_account(api, monkeypatch):
	monkeypatch.setenv("MEDIQUEUE_COOKIE_SECURE", "false")
	response = api.post(
		"/auth/register",
		json={
			"name": "Test Patient",
			"email": "patient-cannot-create-admin@example.com",
			"password": "test-password",
		},
	)
	assert response.status_code == 201
	response = api.post(
		"/admin/accounts",
		json={
			"name": "Unauthorized Admin",
			"email": "unauthorized@example.com",
			"mobile": "0712345678",
			"password": "unique-password",
		},
	)
	assert response.status_code == 403