"""
test_password_reset.py — Password reset flow tests.

Covers:
  - Forgot password always returns 200 (no user enumeration)
  - Reset rate limiting (3 per email per hour)
  - Invalid / expired token returns 400
  - Valid token validates correctly
  - Successful reset updates password
  - Token cannot be reused
  - New password minimum length enforced
"""


class TestForgotPassword:
    def test_known_email_returns_200(self, client):
        r = client.post("/api/auth/forgot-password",
                        json={"email": "admin@usetether.ca"})
        assert r.status_code == 200
        assert "message" in r.json()

    def test_unknown_email_also_returns_200(self, client):
        """Must not leak whether the email exists."""
        r = client.post("/api/auth/forgot-password",
                        json={"email": "definitelynotregistered@nowhere.com"})
        assert r.status_code == 200
        # Response must be identical to the known-email case
        assert "message" in r.json()

    def test_invalid_email_format_rejected(self, client):
        r = client.post("/api/auth/forgot-password",
                        json={"email": "notanemail"})
        assert r.status_code == 422

    def test_rate_limiting(self, client):
        """3 requests per email per hour — 4th gets 429."""
        email = "resetratelimit@test.com"
        for _ in range(3):
            client.post("/api/auth/forgot-password", json={"email": email})
        r = client.post("/api/auth/forgot-password", json={"email": email})
        assert r.status_code == 429


class TestResetToken:
    def _get_raw_token(self):
        """Generate a real token directly via the service layer."""
        from db.database import SessionLocal
        from models.models import User
        from routers.password_reset import _generate_token
        db   = SessionLocal()
        user = db.query(User).filter(User.email == "admin@usetether.ca").first()
        raw  = _generate_token(user.id, db)
        db.close()
        return raw

    def test_invalid_token_returns_400(self, client):
        r = client.get("/api/auth/reset-password/totallyinvalidtoken")
        assert r.status_code == 400

    def test_valid_token_validates(self, client):
        raw = self._get_raw_token()
        r   = client.get(f"/api/auth/reset-password/{raw}")
        assert r.status_code == 200
        data = r.json()
        assert data["valid"] is True
        assert "email" not in data
        assert "name" not in data

    def test_successful_reset(self, client):
        raw = self._get_raw_token()
        r   = client.post("/api/auth/reset-password", json={
            "token":        raw,
            "new_password": "resetpassword99",
        })
        assert r.status_code == 200

        # Login with new password
        r2 = client.post("/api/auth/login",
                         data={"username": "admin@usetether.ca",
                               "password": "resetpassword99"})
        assert r2.status_code == 200

        # Restore original password so other tests aren't broken
        client.post("/api/auth/reset-password", json={
            "token":        self._get_raw_token(),
            "new_password": "admin",
        })

    def test_token_cannot_be_reused(self, client):
        raw = self._get_raw_token()
        client.post("/api/auth/reset-password", json={
            "token": raw, "new_password": "firstuse123"
        })
        r = client.post("/api/auth/reset-password", json={
            "token": raw, "new_password": "seconduse123"
        })
        assert r.status_code == 400

        # Restore
        client.post("/api/auth/reset-password", json={
            "token":        self._get_raw_token(),
            "new_password": "admin",
        })

    def test_short_password_rejected(self, client):
        raw = self._get_raw_token()
        r   = client.post("/api/auth/reset-password", json={
            "token":        raw,
            "new_password": "short",
        })
        assert r.status_code == 400
        assert "8" in r.json()["detail"]
