"""
test_signup.py — Self-serve MSP signup tests.

Covers:
  - Successful signup returns token + trial info
  - Signed-up user can immediately log in
  - Billing row initialised on trial
  - Duplicate email rejected
  - Short password rejected
  - Terms not agreed rejected
  - Signup rate limiting
"""
import time


def _signup_payload(**overrides):
    uid = int(time.time() * 1000) % 999999
    base = {
        "name":        "Test Owner",
        "email":       f"owner{uid}@testmsp.com",
        "password":    "testpassword123",
        "msp_name":    f"Test MSP {uid}",
        "agree_terms": True,
    }
    base.update(overrides)
    return base


class TestSignup:
    def test_successful_signup(self, client):
        payload = _signup_payload()
        r = client.post("/api/auth/signup", json=payload)
        assert r.status_code == 200, r.text
        data = r.json()
        assert "access_token" in data
        assert data["trial_days"] == 30
        assert data["user"]["email"] == payload["email"]
        assert data["user"]["is_msp_staff"] is True

    def test_signed_up_user_can_login(self, client):
        payload = _signup_payload()
        client.post("/api/auth/signup", json=payload)
        r = client.post("/api/auth/login",
                        data={"username": payload["email"],
                              "password": payload["password"]})
        assert r.status_code == 200

    def test_billing_initialised(self, client):
        """Billing row exists after signup. Tier is trial in saas mode, selfhosted otherwise."""
        payload = _signup_payload()
        r   = client.post("/api/auth/signup", json=payload)
        tok = r.json()["access_token"]
        mh  = {"Authorization": f"Bearer {tok}"}
        s   = client.get("/api/billing/status", headers=mh).json()
        assert "tier" in s
        assert s["tier"] in ("trial", "selfhosted")  # depends on DEPLOYMENT_MODE

    def test_duplicate_email_rejected(self, client):
        payload = _signup_payload()
        client.post("/api/auth/signup", json=payload)
        r = client.post("/api/auth/signup", json=payload)
        assert r.status_code == 400
        assert "already exists" in r.json()["detail"].lower()

    def test_short_password_rejected(self, client):
        r = client.post("/api/auth/signup", json=_signup_payload(password="short"))
        assert r.status_code == 422

    def test_terms_not_agreed_rejected(self, client):
        r = client.post("/api/auth/signup",
                        json=_signup_payload(agree_terms=False))
        assert r.status_code == 422

    def test_missing_msp_name_rejected(self, client):
        r = client.post("/api/auth/signup",
                        json=_signup_payload(msp_name=""))
        assert r.status_code == 422

    def test_invalid_email_rejected(self, client):
        r = client.post("/api/auth/signup",
                        json=_signup_payload(email="notanemail"))
        assert r.status_code == 422

    def test_signup_rate_limiting(self, client):
        """5 signups per IP per hour — 6th gets 429."""
        for i in range(5):
            client.post("/api/auth/signup",
                        json=_signup_payload(email=f"rl{i}{int(time.time())}@test.com"))
        r = client.post("/api/auth/signup",
                        json=_signup_payload(email=f"rlfinal{int(time.time())}@test.com"))
        assert r.status_code == 429
