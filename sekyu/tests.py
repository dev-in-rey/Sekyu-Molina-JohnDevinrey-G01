import importlib
import os
import re
from pathlib import Path
from unittest.mock import patch

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.management import call_command
from django.test import Client, TestCase
from django.urls import reverse

import manage
import sekyu.asgi as sekyu_asgi
import sekyu.settings as sekyu_settings
import sekyu.wsgi as sekyu_wsgi
from accounts.models import CustomUser


class ProjectConfigurationAndStructureTests(TestCase):
    def test_settings_postgresql_and_security_defaults(self):
        self.assertEqual(settings.DATABASES["default"]["ENGINE"], "django.db.backends.postgresql")
        self.assertNotIn("sqlite", settings.DATABASES["default"]["ENGINE"].lower())
        self.assertEqual(settings.AUTH_USER_MODEL, "accounts.CustomUser")
        self.assertEqual(settings.TIME_ZONE, "Asia/Manila")
        self.assertEqual(settings.LOGIN_URL, "login")
        self.assertEqual(settings.LOGIN_REDIRECT_URL, "dashboard")
        self.assertEqual(settings.LOGOUT_REDIRECT_URL, "login")
        self.assertIn("accounts.backends.EmailOrUsernameModelBackend", settings.AUTHENTICATION_BACKENDS)
        self.assertTrue(settings.STATICFILES_DIRS)

    def test_sqlite_rejection_and_env_fallback_in_settings(self):
        # Verify SQLite is blocked when DB_ENGINE points to sqlite
        with patch.dict(os.environ, {"DB_ENGINE": "django.db.backends.sqlite3"}):
            with self.assertRaises(ImproperlyConfigured):
                importlib.reload(sekyu_settings)

        # Verify fallback .env parser branch when dotenv import fails (both with and without .env)
        import sys

        with patch.dict(os.environ, {"DB_ENGINE": "django.db.backends.postgresql"}):
            with patch.dict(sys.modules, {"dotenv": None}):
                importlib.reload(sekyu_settings)
                with patch("pathlib.Path.exists", return_value=False):
                    importlib.reload(sekyu_settings)

        # Restore clean module state
        with patch.dict(os.environ, {"DB_ENGINE": "django.db.backends.postgresql"}):
            importlib.reload(sekyu_settings)

    def test_asgi_wsgi_and_manage_entrypoint(self):
        self.assertTrue(callable(sekyu_wsgi.application))
        self.assertTrue(callable(sekyu_asgi.application))

        with patch("django.core.management.execute_from_command_line") as mock_exec:
            with patch("sys.argv", ["manage.py", "check"]):
                manage.main()
                mock_exec.assert_called_once_with(["manage.py", "check"])

        # Reload urls with DEBUG=True and DEBUG=False to cover static media branch
        import sekyu.urls as sekyu_urls

        with self.settings(DEBUG=True):
            importlib.reload(sekyu_urls)
        with self.settings(DEBUG=False):
            importlib.reload(sekyu_urls)
        importlib.reload(sekyu_urls)

    def test_project_files_static_branding_and_bootstrap_cdn(self):
        base_dir = Path(settings.BASE_DIR)

        for rel in (
            "README.md",
            "PRODUCT.md",
            "requirements.txt",
            ".gitignore",
            ".coveragerc",
            ".env.example",
            "static/css/sekyu.css",
            "static/img/sekyu-logo.png",
            "static/img/favicon.ico",
            "static/img/favicon.png",
            "static/img/apple-touch-icon.png",
        ):
            self.assertTrue((base_dir / rel).exists(), f"Missing expected project file: {rel}")

        gi = (base_dir / ".gitignore").read_text(encoding="utf-8")
        for entry in ("__pycache__/", ".venv/", "venv/", ".env", ".coverage", "htmlcov/"):
            self.assertIn(entry, gi)
        self.assertNotIn("requirements.txt", gi)

        readme = (base_dir / "README.md").read_text(encoding="utf-8")
        self.assertIn("John Devinrey A. Molina", readme)
        self.assertIn("manage.py migrate", readme)
        self.assertIn("manage.py runserver", readme)

        base_html = (base_dir / "templates" / "base.html").read_text(encoding="utf-8")
        self.assertIn("cdn.jsdelivr.net/npm/bootstrap@5", base_html)
        self.assertIn("bootstrap.min.css", base_html)
        self.assertIn("bootstrap.bundle.min.js", base_html)
        self.assertIn("img/favicon.ico", base_html)
        self.assertIn("img/sekyu-logo.png", base_html)
        self.assertIn("css/sekyu.css", base_html)

        local_bootstrap = [
            p for p in base_dir.rglob("*bootstrap*") if ".venv" not in p.parts and "venv" not in p.parts
        ]
        self.assertEqual(local_bootstrap, [])

        template_files = [
            "403.html",
            "registration/login.html",
            "registration/signup.html",
            "accounts/profile.html",
            "accounts/profile_edit.html",
            "dashboard/resident_dashboard.html",
            "dashboard/guard_dashboard.html",
            "dashboard/admin_dashboard.html",
            "households/household_list.html",
            "households/household_form.html",
            "households/household_confirm_delete.html",
            "households/admin_household_list.html",
            "passes/pass_list.html",
            "passes/pass_form.html",
            "passes/pass_detail.html",
            "passes/pass_confirm_delete.html",
            "passes/guard_validate.html",
            "passes/gate_logs.html",
        ]
        for rel_path in template_files:
            text = (base_dir / "templates" / rel_path).read_text(encoding="utf-8")
            self.assertIn('{% extends "base.html" %}', text)
            self.assertNotRegex(text, r"\{\{\s*form(\.as_p|\.as_table|\.as_ul)?\s*\}\}")

        # Verify Bootstrap form-control styling on rendered forms
        client = Client()
        user = CustomUser.objects.create_user(
            username="ui_check_res",
            email="uicheck@sekyu.ph",
            password="SecurePassword123!",
            role=CustomUser.Role.RESIDENT,
        )
        client.force_login(user)
        for url in (reverse("login"), reverse("signup"), reverse("profile_edit")):
            html = client.get(url).content.decode("utf-8")
            inputs = [inp for inp in re.findall(r"<input[^>]+>", html) if 'type="hidden"' not in inp]
            self.assertTrue(len(inputs) > 0)
            for inp in inputs:
                if 'id="guardResidentSearch"' not in inp:
                    self.assertIn("form-control", inp)

        # Admin site reachable for superuser
        su = CustomUser.objects.create_superuser(
            username="su_check",
            email="su.check@sekyu.ph",
            password="SecurePassword123!",
        )
        client.force_login(su)
        self.assertEqual(client.get("/admin/").status_code, 200)

        call_command("check")
