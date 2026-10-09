from app import database


def test_admin_login_accepts_admin_password_and_rejects_incorrect_password(api, monkeypatch):
	monkeypatch.delenv("MEDIQUEUE_ADMIN_EMAIL", raising=False)
	monkeypatch.delenv("MEDIQUEUE_ADMIN_PASSWORD", raising=False)
	database.initialize_database()

	response = api.post("/auth/admin-login", json={"password": "Admin1"})

	assert response.status_code == 200
	assert response.json()["user"]["role"] == "admin"
	assert response.cookies.get("mediqueue_session")

	response = api.post("/auth/admin-login", json={"password": "incorrect"})
	assert response.status_code == 401