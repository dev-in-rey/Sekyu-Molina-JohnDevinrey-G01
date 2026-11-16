import io
from PIL import Image
from django.contrib.messages import get_messages
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.urls import reverse

from accounts.models import CustomUser
from dashboard.apps import DashboardConfig


def _make_avatar(name="guard_avatar.png"):
    buf = io.BytesIO()
    Image.new("RGB", (24, 24), color=(15, 23, 42)).save(buf, format="PNG")
    buf.seek(0)
    return SimpleUploadedFile(name, buf.read(), content_type="image/png")


class DashboardTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.resident_pending = CustomUser.objects.create_user(
            username="res_pending",
            email="res_pending@sekyu.ph",
            password="SecurePassword123!",
            first_name="Juan",
            last_name="Dela Cruz",
            phone_number="+63 917 111 2222",
            role=CustomUser.Role.RESIDENT,
            is_approved=False,
        )
        self.resident_approved = CustomUser.objects.create_user(
            username="res_approved",
            email="res_approved@sekyu.ph",
            password="SecurePassword123!",
            first_name="Maria",
            last_name="Santos",
            phone_number="+63 917 333 4444",
            role=CustomUser.Role.RESIDENT,
            is_approved=True,
            profile_photo=_make_avatar("res.png"),
        )
        self.resident_no_phone = CustomUser.objects.create_user(
            username="res_nophone",
            email="res_nophone@sekyu.ph",
            password="SecurePassword123!",
            first_name="",
            last_name="",
            phone_number="",
            role=CustomUser.Role.RESIDENT,
            is_approved=True,
        )
        self.resident_inactive = CustomUser.objects.create_user(
            username="res_inactive",
            email="res_inactive@sekyu.ph",
            password="SecurePassword123!",
            role=CustomUser.Role.RESIDENT,
            is_approved=True,
            is_active=False,
        )
        self.guard = CustomUser.objects.create_user(
            username="guard_one",
            email="guard@sekyu.ph",
            password="SecurePassword123!",
            first_name="Ramon",
            last_name="Bautista",
            role=CustomUser.Role.GUARD,
            profile_photo=_make_avatar("guard.png"),
        )
        self.admin = CustomUser.objects.create_user(
            username="hoa_admin",
            email="admin@sekyu.ph",
            password="SecurePassword123!",
            first_name="John",
            last_name="Molina",
            role=CustomUser.Role.ADMIN,
        )

    def test_app_config(self):
        self.assertEqual(DashboardConfig.name, "dashboard")

    def test_anonymous_redirects_to_login_from_all_dashboards(self):
        for name in ("dashboard", "resident_dashboard", "guard_dashboard", "admin_dashboard", "admin_panel"):
            resp = self.client.get(reverse(name))
            self.assertEqual(resp.status_code, 302)
            self.assertIn(reverse("login"), resp.url)

    def test_role_based_routing_and_strict_403_isolation(self):
        # Resident (pending)
        self.client.force_login(self.resident_pending)
        self.assertRedirects(self.client.get(reverse("dashboard")), reverse("resident_dashboard"))
        res_dash = self.client.get(reverse("resident_dashboard"))
        self.assertEqual(res_dash.status_code, 200)
        self.assertContains(res_dash, "Household Verification Pending")
        self.assertEqual(self.client.get(reverse("guard_dashboard")).status_code, 403)
        self.assertEqual(self.client.get(reverse("admin_dashboard")).status_code, 403)

        # Resident (approved, with photo)
        self.client.force_login(self.resident_approved)
        res_ok_dash = self.client.get(reverse("resident_dashboard"))
        self.assertEqual(res_ok_dash.status_code, 200)
        self.assertContains(res_ok_dash, "Verified Homeowner Standing")

        # Guard
        self.client.force_login(self.guard)
        self.assertRedirects(self.client.get(reverse("dashboard")), reverse("guard_dashboard"))
        guard_dash = self.client.get(reverse("guard_dashboard"))
        self.assertEqual(guard_dash.status_code, 200)
        self.assertContains(guard_dash, "Maria Santos")
        self.assertContains(guard_dash, "Not provided")
        self.assertNotContains(guard_dash, "res_pending")
        self.assertNotContains(guard_dash, "res_inactive")
        self.assertEqual(self.client.get(reverse("resident_dashboard")).status_code, 403)
        self.assertEqual(self.client.get(reverse("admin_dashboard")).status_code, 403)

        # Admin
        self.client.force_login(self.admin)
        self.assertRedirects(self.client.get(reverse("dashboard")), reverse("admin_dashboard"))
        admin_dash = self.client.get(reverse("admin_dashboard"))
        self.assertEqual(admin_dash.status_code, 200)
        self.assertEqual(self.client.get(reverse("admin_panel")).status_code, 200)
        self.assertEqual(self.client.get(reverse("resident_dashboard")).status_code, 403)
        self.assertEqual(self.client.get(reverse("guard_dashboard")).status_code, 403)

    def test_guard_dashboard_empty_directory_state(self):
        CustomUser.objects.filter(role=CustomUser.Role.RESIDENT).delete()
        guard_no_photo = CustomUser.objects.create_user(
            username="guard_plain",
            email="guard.plain@sekyu.ph",
            password="SecurePassword123!",
            role=CustomUser.Role.GUARD,
        )
        self.client.force_login(guard_no_photo)
        resp = self.client.get(reverse("guard_dashboard"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "No verified residents yet")

    def test_manage_resident_status_view_all_actions_and_guards(self):
        url = reverse("manage_user_status", kwargs={"pk": self.resident_pending.pk})
        self_url = reverse("manage_user_status", kwargs={"pk": self.admin.pk})

        # Anonymous & non-admin blocked
        self.assertEqual(self.client.post(url, {"action": "approve"}).status_code, 302)
        self.client.force_login(self.resident_pending)
        self.assertEqual(self.client.post(url, {"action": "approve"}).status_code, 403)
        self.client.force_login(self.guard)
        self.assertEqual(self.client.post(url, {"action": "approve"}).status_code, 403)

        # Admin tests
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(url).status_code, 405)
        self.assertEqual(
            self.client.post(
                reverse("manage_user_status", kwargs={"pk": 999999}),
                {"action": "approve"},
            ).status_code,
            404,
        )

        # Approve resident
        resp = self.client.post(url, {"action": "approve"})
        self.assertRedirects(resp, reverse("admin_dashboard"))
        self.resident_pending.refresh_from_db()
        self.assertTrue(self.resident_pending.is_approved)

        # Revoke approval on resident & self warning
        self.client.post(url, {"action": "revoke_approval"})
        self.resident_pending.refresh_from_db()
        self.assertFalse(self.resident_pending.is_approved)

        self_revoke = self.client.post(self_url, {"action": "revoke_approval"}, follow=True)
        self.assertTrue(any("cannot revoke approval" in str(m) for m in get_messages(self_revoke.wsgi_request)))

        # Toggle active on resident & self-deactivation error
        self.client.post(url, {"action": "toggle_active"})
        self.resident_pending.refresh_from_db()
        self.assertFalse(self.resident_pending.is_active)

        self.client.post(url, {"action": "toggle_active"})
        self.resident_pending.refresh_from_db()
        self.assertTrue(self.resident_pending.is_active)

        self_deact = self.client.post(self_url, {"action": "toggle_active"}, follow=True)
        self.assertTrue(any("cannot deactivate your own" in str(m) for m in get_messages(self_deact.wsgi_request)))

        # Change role: promote to GUARD (auto-approves), demote back to RESIDENT, invalid role, self-demotion guard
        self.client.post(url, {"action": "change_role", "role": CustomUser.Role.GUARD})
        self.resident_pending.refresh_from_db()
        self.assertEqual(self.resident_pending.role, CustomUser.Role.GUARD)
        self.assertTrue(self.resident_pending.is_approved)

        self.client.post(url, {"action": "change_role", "role": CustomUser.Role.RESIDENT})
        self.resident_pending.refresh_from_db()
        self.assertEqual(self.resident_pending.role, CustomUser.Role.RESIDENT)

        bad_role = self.client.post(url, {"action": "change_role", "role": "INVALID"}, follow=True)
        self.assertTrue(any("Invalid role" in str(m) for m in get_messages(bad_role.wsgi_request)))

        self_demote = self.client.post(
            self_url, {"action": "change_role", "role": CustomUser.Role.RESIDENT}, follow=True
        )
        self.assertTrue(any("cannot demote your own" in str(m) for m in get_messages(self_demote.wsgi_request)))

        # Unsupported action raises 403 PermissionDenied
        bad_action = self.client.post(url, {"action": "drop_table"})
        self.assertEqual(bad_action.status_code, 403)
