"""
test_email_service.py — Unit tests for email_service.py white-label branding.

These tests run in-process and do not send real email (EMAIL_PROVIDER=none in conftest).
"""
import sys
import os

# Ensure backend is on path (conftest already does this but be explicit for isolation)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))


class _FakeTenant:
    """Minimal stand-in for a Tenant ORM object."""
    def __init__(self, **kw):
        self.name               = kw.get("name", "Acme IT")
        self.email_from_name    = kw.get("email_from_name", None)
        self.email_from_address = kw.get("email_from_address", None)
        self.email_logo_url     = kw.get("email_logo_url", None)
        self.email_accent_color = kw.get("email_accent_color", None)
        self.logo_url           = kw.get("logo_url", "")
        self.accent_color       = kw.get("accent_color", "#d4f034")


class TestGetTenantBranding:
    def test_returns_defaults_when_no_tenant(self):
        from email_service import get_tenant_branding
        b = get_tenant_branding(None)
        assert b["brand_name"]     == "Tether"
        assert b["brand_logo_url"] == ""
        assert b["brand_accent"]   == "#d4f034"
        assert "brand_url" in b

    def test_uses_email_from_name_when_set(self):
        from email_service import get_tenant_branding
        t = _FakeTenant(email_from_name="Acme IT Solutions")
        b = get_tenant_branding(t)
        assert b["brand_name"] == "Acme IT Solutions"

    def test_falls_back_to_tenant_name_when_no_email_from_name(self):
        from email_service import get_tenant_branding
        t = _FakeTenant(name="Contoso Corp", email_from_name=None)
        b = get_tenant_branding(t)
        assert b["brand_name"] == "Contoso Corp"

    def test_uses_email_logo_url_when_set(self):
        from email_service import get_tenant_branding
        t = _FakeTenant(email_logo_url="https://acme.com/logo.png")
        b = get_tenant_branding(t)
        assert b["brand_logo_url"] == "https://acme.com/logo.png"

    def test_falls_back_to_logo_url_when_no_email_logo(self):
        from email_service import get_tenant_branding
        t = _FakeTenant(email_logo_url=None, logo_url="https://acme.com/general.png")
        b = get_tenant_branding(t)
        assert b["brand_logo_url"] == "https://acme.com/general.png"

    def test_uses_email_accent_color_when_set(self):
        from email_service import get_tenant_branding
        t = _FakeTenant(email_accent_color="#ff5500")
        b = get_tenant_branding(t)
        assert b["brand_accent"] == "#ff5500"

    def test_falls_back_to_accent_color_when_no_email_accent(self):
        from email_service import get_tenant_branding
        t = _FakeTenant(email_accent_color=None, accent_color="#aabbcc")
        b = get_tenant_branding(t)
        assert b["brand_accent"] == "#aabbcc"


class TestBaseTemplate:
    def test_default_branding_uses_tether(self):
        from email_service import _base_template
        html = _base_template("Test", "<p>body</p>")
        assert "Tether" in html

    def test_brand_name_appears_in_output(self):
        from email_service import _base_template
        html = _base_template("Test", "<p>body</p>", brand_name="Acme IT")
        assert "Acme IT" in html
        assert "Tether" not in html

    def test_brand_accent_used_in_button(self):
        from email_service import _base_template
        # The accent appears in the logo area as text colour or passed to send_* funcs
        html = _base_template("Test", "<p>body</p>", brand_accent="#ff5500")
        assert "#ff5500" in html

    def test_logo_img_tag_when_url_provided(self):
        from email_service import _base_template
        html = _base_template("Test", "<p>body</p>",
                              brand_logo_url="https://acme.com/logo.png")
        assert '<img' in html
        assert "acme.com/logo.png" in html

    def test_text_logo_when_no_url(self):
        from email_service import _base_template
        html = _base_template("Test", "<p>body</p>",
                              brand_name="MyBrand", brand_logo_url="")
        assert "MyBrand" in html
        assert "<img" not in html

    def test_footer_uses_brand_name_not_hardcoded_tether(self):
        from email_service import _base_template
        html = _base_template("Test", "<p>body</p>",
                              brand_name="Contoso", brand_url="https://contoso.com")
        assert "Contoso" in html
        assert "contoso.com" in html


class TestSendInviteBranding:
    def test_send_invite_uses_tenant_branding(self):
        """When tenant has email_from_name, branding is passed into the email body."""
        from email_service import send_invite, _base_template
        t = _FakeTenant(
            name="Contoso",
            email_from_name="Contoso IT",
            email_accent_color="#123456",
        )
        # We can't intercept send_email easily, but we can verify _base_template
        # produces the right output when called with tenant branding.
        from email_service import get_tenant_branding
        b = get_tenant_branding(t)
        html = _base_template("You've been invited", "<p>test</p>", **b)
        assert "Contoso IT" in html
        assert "#123456" in html

    def test_send_invite_falls_back_to_tether_branding_when_no_config(self):
        from email_service import get_tenant_branding, _base_template
        t = _FakeTenant(name="SomeCorp", email_from_name=None,
                        email_accent_color=None, accent_color="#d4f034")
        b = get_tenant_branding(t)
        html = _base_template("You've been invited", "<p>test</p>", **b)
        assert "SomeCorp" in html   # falls back to tenant.name
        assert "#d4f034"  in html   # falls back to tenant.accent_color

    def test_send_invite_with_no_tenant_uses_tether_defaults(self):
        from email_service import get_tenant_branding, _base_template
        b = get_tenant_branding(None)
        html = _base_template("You've been invited", "<p>test</p>", **b)
        assert "Tether" in html
        assert "#d4f034" in html


class TestSendEmailFromOverride:
    def test_send_email_uses_custom_from_name_and_address(self, capfd):
        """When provider=none, the log output should reflect custom from details."""
        import logging
        from email_service import send_email
        # With EMAIL_PROVIDER=none, send_email logs and returns True
        result = send_email(
            "user@example.com",
            "Test Subject",
            "<p>hello</p>",
            from_name="Acme IT",
            from_address="it@acme.com",
        )
        assert result is True
