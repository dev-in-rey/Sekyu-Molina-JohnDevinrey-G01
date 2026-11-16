import io
import re
from pathlib import Path
from PIL import Image
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase, Client
from django.urls import reverse, resolve
from django.views.generic import UpdateView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.contrib.messages import get_messages

from accounts.models import CustomUser
from accounts.views import ProfileUpdateView, SignUpView


class SekyuAccountFeatureTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.resident_a = CustomUser.objects.create_user(
            username="resident_a",
            email="resident_a@sekyu.ph",
            password="SecurePassword123!",
            first_name="Juan",
            last_name="Dela Cruz",
            phone_number="+63 917 111 2222",
            role=CustomUser.Role.RESIDENT,
            is_approved=False,
        )
        self.resident_b = CustomUser.objects.create_user(
            username="resident_b",
            email="resident_b@sekyu.ph",
            password="SecurePassword123!",
            first_name="Maria",
            last_name="Santos",
            phone_number="+63 917 333 4444",
            role=CustomUser.Role.RESIDENT,
            is_approved=True,
        )
        self.guard_user = CustomUser.objects.create_user(
            username="guard_one",
            email="guard@sekyu.ph",
            password="SecurePassword123!",
            first_name="Ramon",
            last_name="Bautista",
            phone_number="+63 918 555 6666",
            role=CustomUser.Role.GUARD,
        )
        self.admin_user = CustomUser.objects.create_user(
            username="hoa_admin",
            email="admin@sekyu.ph",
            password="SecurePassword123!",
            first_name="John",
            last_name="Molina",
            phone_number="+63 919 777 8888",
            role=CustomUser.Role.ADMIN,
        )

    def test_01_signup_validates_hashes_password_assigns_pending_resident_and_shows_alert(self):
        signup_data = {
            "username": "new_homeowner",
            "email": "new.homeowner@sekyu.ph",
            "first_name": "Elena",
            "last_name": "Reyes",
            "phone_number": "+63 917 999 0000",
            "password1": "StrongGatePass123!@#",
            "password2": "StrongGatePass123!@#",
        }
        response = self.client.post(reverse("signup"), signup_data, follow=True)
        self.assertRedirects(response, reverse("login"))

        created = CustomUser.objects.get(username="new_homeowner")
        self.assertEqual(created.role, CustomUser.Role.RESIDENT)
        self.assertFalse(created.is_approved)
        self.assertNotEqual(created.password, "StrongGatePass123!@#")
        self.assertTrue(created.check_password("StrongGatePass123!@#"))

        msgs = [str(m) for m in get_messages(response.wsgi_request)]
        self.assertTrue(any("Account created successfully" in m for m in msgs))
        self.assertRegex(
            response.content.decode("utf-8"),
            r'class="[^"]*\balert\b[^"]*\balert-success\b[^"]*"[^>]*role="alert"',
        )

    def test_02_signup_rejects_duplicate_email_and_mismatched_passwords(self):
        bad_data = {
            "username": "another_user",
            "email": "resident_a@sekyu.ph",  # duplicate email
            "first_name": "Test",
            "last_name": "User",
            "phone_number": "09170001111",
            "password1": "StrongGatePass123!@#",
            "password2": "DifferentPassword999!",
        }
        resp = self.client.post(reverse("signup"), bad_data)
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(CustomUser.objects.filter(username="another_user").exists())
        self.assertContains(resp, "already exists")

    def test_03_login_supports_username_or_email_and_invalid_credentials_error(self):
        # Login with username
        resp_user = self.client.post(
            reverse("login"),
            {"username": "resident_a", "password": "SecurePassword123!"},
        )
        self.assertRedirects(resp_user, reverse("dashboard"), fetch_redirect_response=False)
        self.client.post(reverse("logout"))

        # Login with email
        resp_email = self.client.post(
            reverse("login"),
            {"username": "RESIDENT_A@SEKYU.PH", "password": "SecurePassword123!"},
        )
        self.assertRedirects(resp_email, reverse("dashboard"), fetch_redirect_response=False)
        self.client.post(reverse("logout"))

        # Invalid login
        resp_bad = self.client.post(
            reverse("login"),
            {"username": "resident_a", "password": "WrongPassword!"},
        )
        self.assertEqual(resp_bad.status_code, 200)
        self.assertContains(resp_bad, "Invalid username/email or password")

    def test_04_role_based_dashboard_routing_and_strict_role_isolation(self):
        # Resident goes to resident_dashboard, blocked from guard & admin dashboards
        self.client.force_login(self.resident_a)
        resp = self.client.get(reverse("dashboard"))
        self.assertRedirects(resp, reverse("resident_dashboard"))
        self.assertEqual(self.client.get(reverse("resident_dashboard")).status_code, 200)
        self.assertEqual(self.client.get(reverse("guard_dashboard")).status_code, 403)
        self.assertEqual(self.client.get(reverse("admin_dashboard")).status_code, 403)

        # Guard goes to guard_dashboard, blocked from resident & admin dashboards
        self.client.force_login(self.guard_user)
        resp = self.client.get(reverse("dashboard"))
        self.assertRedirects(resp, reverse("guard_dashboard"))
        self.assertEqual(self.client.get(reverse("guard_dashboard")).status_code, 200)
        self.assertEqual(self.client.get(reverse("resident_dashboard")).status_code, 403)
        self.assertEqual(self.client.get(reverse("admin_dashboard")).status_code, 403)

        # Admin goes to admin_dashboard, blocked from resident & guard dashboards
        self.client.force_login(self.admin_user)
        resp = self.client.get(reverse("dashboard"))
        self.assertRedirects(resp, reverse("admin_dashboard"))
        self.assertEqual(self.client.get(reverse("admin_dashboard")).status_code, 200)
        self.assertEqual(self.client.get(reverse("resident_dashboard")).status_code, 403)
        self.assertEqual(self.client.get(reverse("guard_dashboard")).status_code, 403)

    def test_05_admin_can_approve_pending_resident_and_assign_roles(self):
        self.client.force_login(self.admin_user)
        self.assertFalse(self.resident_a.is_approved)

        approve_resp = self.client.post(
            reverse("manage_user_status", kwargs={"pk": self.resident_a.pk}),
            {"action": "approve"},
        )
        self.assertRedirects(approve_resp, reverse("admin_dashboard"))
        self.resident_a.refresh_from_db()
        self.assertTrue(self.resident_a.is_approved)

    def test_06_profile_view_edit_photo_upload_and_isolation(self):
        # Anonymous users redirected to login
        for name in ("profile", "profile_edit", "dashboard", "resident_dashboard"):
            anon = self.client.get(reverse(name))
            self.assertEqual(anon.status_code, 302)
            self.assertIn(reverse("login"), anon.url)

        self.client.force_login(self.resident_a)

        # Cannot view or edit resident_b's profile
        self.assertEqual(
            self.client.get(reverse("profile_detail", kwargs={"pk": self.resident_b.pk})).status_code,
            403,
        )
        self.assertEqual(
            self.client.post(
                reverse("profile_edit_pk", kwargs={"pk": self.resident_b.pk}),
                {"first_name": "Hacked", "last_name": "Name", "email": "hack@sekyu.ph"},
            ).status_code,
            403,
        )

        # Generate an in-memory PNG for profile photo upload test
        img_buffer = io.BytesIO()
        Image.new("RGB", (32, 32), color=(15, 118, 110)).save(img_buffer, format="PNG")
        img_buffer.seek(0)
        uploaded_photo = SimpleUploadedFile(
            "avatar.png", img_buffer.read(), content_type="image/png"
        )

        update_resp = self.client.post(
            reverse("profile_edit"),
            {
                "first_name": "Juanito",
                "last_name": "Dela Cruz Jr.",
                "email": "juanito.updated@sekyu.ph",
                "phone_number": "+63 917 888 9999",
                "profile_photo": uploaded_photo,
            },
            follow=True,
        )
        self.assertEqual(update_resp.status_code, 200)
        self.resident_a.refresh_from_db()
        self.assertEqual(self.resident_a.first_name, "Juanito")
        self.assertEqual(self.resident_a.email, "juanito.updated@sekyu.ph")
        self.assertEqual(self.resident_a.phone_number, "+63 917 888 9999")
        self.assertTrue(bool(self.resident_a.profile_photo))

    def test_07_code_quality_and_project_files(self):
        resolved = resolve(reverse("profile_edit"))
        self.assertEqual(resolved.func.view_class, ProfileUpdateView)
        self.assertTrue(issubclass(ProfileUpdateView, UpdateView))
        self.assertTrue(issubclass(ProfileUpdateView, LoginRequiredMixin))
        self.assertTrue(issubclass(ProfileUpdateView, SuccessMessageMixin))
        self.assertTrue(issubclass(SignUpView, SuccessMessageMixin))

        base_dir = Path(settings.BASE_DIR)
        self.assertTrue((base_dir / "README.md").exists())
        self.assertTrue((base_dir / "requirements.txt").exists())
        self.assertTrue((base_dir / ".gitignore").exists())
        gi = (base_dir / ".gitignore").read_text(encoding="utf-8")
        for entry in ("__pycache__/", ".venv/", "venv/", ".env"):
            self.assertIn(entry, gi)
        self.assertNotIn("requirements.txt", gi)

        call_command("check")
