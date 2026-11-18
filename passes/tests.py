from datetime import timedelta
from unittest.mock import patch
from django.contrib import admin
from django.contrib.messages import get_messages
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.models import CustomUser
from households.models import Household
from passes.admin import GateAccessLogAdmin, VisitorPassAdmin
from passes.apps import PassesConfig
from passes.forms import GuardPinValidationForm, VisitorPassForm
from passes.models import GateAccessLog, VisitorPass


class VisitorPassAndGateLogModelTests(TestCase):
    def setUp(self):
        self.resident = CustomUser.objects.create_user(
            username="res_pass",
            email="res.pass@sekyu.ph",
            password="SecurePassword123!",
            first_name="Maria",
            last_name="Santos",
            role=CustomUser.Role.RESIDENT,
            is_approved=True,
        )
        self.guard = CustomUser.objects.create_user(
            username="guard_pass",
            email="guard.pass@sekyu.ph",
            password="SecurePassword123!",
            role=CustomUser.Role.GUARD,
        )
        self.household = Household.objects.create(
            user=self.resident,
            block_number=4,
            lot_number=10,
            street_name="Narra Street",
        )

    def test_app_config_and_admin_registration(self):
        self.assertEqual(PassesConfig.name, "passes")
        self.assertIn(VisitorPass, admin.site._registry)
        self.assertIsInstance(admin.site._registry[VisitorPass], VisitorPassAdmin)
        self.assertIn(GateAccessLog, admin.site._registry)
        self.assertIsInstance(admin.site._registry[GateAccessLog], GateAccessLogAdmin)

    def test_visitor_pass_generation_expiration_and_db_constraints(self):
        now = timezone.now()
        vpass = VisitorPass.objects.create(
            household=self.household,
            visitor_name="  Carlo   Mendoza  ",
            visitor_phone="09175550199",
            visitor_type=VisitorPass.VisitorType.DELIVERY,
            valid_from=now - timedelta(hours=1),
            valid_until=now + timedelta(hours=2),
        )
        self.assertEqual(vpass.visitor_name, "Carlo Mendoza")
        self.assertEqual(len(vpass.access_pin), 4)
        self.assertTrue(vpass.access_pin.isdigit())
        self.assertTrue(vpass.qr_token.startswith("SKP-"))
        self.assertIn("Carlo Mendoza", str(vpass))

        # Fallback branch in generate_access_pin when all 50 random attempts collide
        with patch("passes.models.secrets.randbelow", return_value=int(vpass.access_pin)):
            pin_fallback = VisitorPass.generate_access_pin()
            self.assertEqual(len(pin_fallback), 4)

        # Empty visitor_name branch in save()
        blank_name_pass = VisitorPass(
            household=self.household,
            visitor_name="",
            access_pin="1234",
            qr_token="SKP-custom-token",
            valid_from=now,
            valid_until=now + timedelta(hours=1),
        )
        blank_name_pass.save()
        self.assertEqual(blank_name_pass.access_pin, "1234")

        # refresh_expiration transitions ACTIVE/PENDING past valid_until to EXPIRED (BR-14)
        vpass.refresh_expiration(now=now + timedelta(hours=5))
        vpass.refresh_from_db()
        self.assertEqual(vpass.status, VisitorPass.Status.EXPIRED)

        # Unsaved pass refresh_expiration branch
        unsaved = VisitorPass(
            household=self.household,
            visitor_name="Unsaved Guest",
            valid_from=now - timedelta(hours=3),
            valid_until=now - timedelta(hours=1),
        )
        self.assertEqual(unsaved.refresh_expiration(now=now), VisitorPass.Status.EXPIRED)

        # Invalid window (valid_until <= valid_from) violates CheckConstraint (BR-09)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                VisitorPass.objects.create(
                    household=self.household,
                    visitor_name="Bad Window",
                    valid_from=now,
                    valid_until=now - timedelta(minutes=10),
                )

        # Non-4-digit PIN violates CheckConstraint (BR-10)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                VisitorPass.objects.create(
                    household=self.household,
                    visitor_name="Bad PIN",
                    access_pin="12A4",
                    valid_from=now,
                    valid_until=now + timedelta(hours=1),
                )

    def test_gate_access_log_constraints_and_br19_protection(self):
        now = timezone.now()
        vpass = VisitorPass.objects.create(
            household=self.household,
            visitor_name="Service Tech",
            valid_from=now - timedelta(hours=1),
            valid_until=now + timedelta(hours=2),
        )
        log = GateAccessLog.objects.create(
            guard_user=self.guard,
            visitor_pass=vpass,
            household=self.household,
            visitor_name=vpass.visitor_name,
            visitor_type=GateAccessLog.VisitorType.SERVICE,
            entry_timestamp=now,
            verification_status=GateAccessLog.VerificationStatus.GRANTED,
        )
        self.assertIn("Service Tech", str(log))

        # BR-19: VisitorPass referenced by GateAccessLog cannot be deleted
        with self.assertRaises(ProtectedError):
            vpass.delete()

        # BR-18: exit_timestamp < entry_timestamp violates CheckConstraint
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                GateAccessLog.objects.create(
                    guard_user=self.guard,
                    visitor_pass=vpass,
                    household=self.household,
                    visitor_name="Time Traveler",
                    entry_timestamp=now,
                    exit_timestamp=now - timedelta(minutes=5),
                    verification_status=GateAccessLog.VerificationStatus.GRANTED,
                )


class VisitorPassAndGuardFormsTests(TestCase):
    def setUp(self):
        self.resident_ok = CustomUser.objects.create_user(
            username="res_ok",
            email="res.ok@sekyu.ph",
            password="SecurePassword123!",
            role=CustomUser.Role.RESIDENT,
            is_approved=True,
        )
        self.resident_unapproved = CustomUser.objects.create_user(
            username="res_unapp",
            email="res.unapp@sekyu.ph",
            password="SecurePassword123!",
            role=CustomUser.Role.RESIDENT,
            is_approved=False,
        )
        self.hh_good = Household.objects.create(
            user=self.resident_ok,
            block_number=1,
            lot_number=1,
            street_name="Narra Street",
            hoa_status=Household.HoaStatus.GOOD_STANDING,
        )
        self.hh_delinquent = Household.objects.create(
            user=self.resident_ok,
            block_number=1,
            lot_number=2,
            street_name="Narra Street",
            hoa_status=Household.HoaStatus.DELINQUENT,
        )
        self.hh_unapp = Household.objects.create(
            user=self.resident_unapproved,
            block_number=2,
            lot_number=1,
            street_name="Molave Street",
        )

    def test_visitor_pass_form_validation_rules(self):
        now = timezone.localtime(timezone.now()).replace(second=0, microsecond=0)
        start_str = now.strftime("%Y-%m-%dT%H:%M")
        end_str = (now + timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M")

        # Unbound form sets default initial window; form without user works too
        unbound = VisitorPassForm(user=self.resident_ok)
        self.assertIn("valid_from", unbound.initial)
        no_user_form = VisitorPassForm()
        self.assertIn("form-select", no_user_form.fields["household"].widget.attrs["class"])

        # Pre-populated form-select class branch
        custom_form = VisitorPassForm(user=self.resident_ok)
        custom_form.fields["household"].widget.attrs["class"] = "form-select"
        custom_form.__init__(user=self.resident_ok)

        # Unapproved resident rejected (BR-13)
        unapp_form = VisitorPassForm(
            user=self.resident_unapproved,
            data={
                "household": self.hh_unapp.pk,
                "visitor_name": "Guest One",
                "visitor_phone": "",
                "visitor_type": VisitorPass.VisitorType.GUEST,
                "valid_from": start_str,
                "valid_until": end_str,
            },
        )
        self.assertFalse(unapp_form.is_valid())
        self.assertIn("household", unapp_form.errors)

        # Delinquent household rejected (BR-13), blank visitor_name, bad phone, invalid window (BR-09)
        bad_form = VisitorPassForm(
            user=self.resident_ok,
            data={
                "household": self.hh_delinquent.pk,
                "visitor_name": "   ",
                "visitor_phone": "invalid-phone!",
                "visitor_type": VisitorPass.VisitorType.GUEST,
                "valid_from": end_str,
                "valid_until": start_str,
            },
        )
        self.assertFalse(bad_form.is_valid())
        self.assertIn("household", bad_form.errors)
        self.assertIn("visitor_name", bad_form.errors)
        self.assertIn("visitor_phone", bad_form.errors)
        self.assertIn("__all__", bad_form.errors)

        # Direct clean_visitor_name empty check
        bad_form.cleaned_data = {"visitor_name": "   "}
        with self.assertRaises(Exception):
            bad_form.clean_visitor_name()

        # Valid form
        ok_form = VisitorPassForm(
            user=self.resident_ok,
            data={
                "household": self.hh_good.pk,
                "visitor_name": "Ana Gomez",
                "visitor_phone": "+63 917 123 4567",
                "visitor_type": VisitorPass.VisitorType.GUEST,
                "valid_from": start_str,
                "valid_until": end_str,
            },
        )
        self.assertTrue(ok_form.is_valid(), ok_form.errors)

    def test_guard_pin_validation_form(self):
        bad_pin = GuardPinValidationForm(data={"access_pin": "12A", "remarks": ""})
        self.assertFalse(bad_pin.is_valid())
        self.assertIn("access_pin", bad_pin.errors)

        ok_pin = GuardPinValidationForm(data={"access_pin": "0429", "remarks": "ID checked"})
        self.assertTrue(ok_pin.is_valid())
        self.assertEqual(ok_pin.cleaned_data["access_pin"], "0429")


class VisitorPassAndGuardViewsTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.resident_a = CustomUser.objects.create_user(
            username="res_a",
            email="res.a@sekyu.ph",
            password="SecurePassword123!",
            first_name="Maria",
            last_name="Santos",
            role=CustomUser.Role.RESIDENT,
            is_approved=True,
        )
        self.resident_b = CustomUser.objects.create_user(
            username="res_b",
            email="res.b@sekyu.ph",
            password="SecurePassword123!",
            first_name="Pedro",
            last_name="Reyes",
            role=CustomUser.Role.RESIDENT,
            is_approved=False,
        )
        self.guard = CustomUser.objects.create_user(
            username="guard_one",
            email="guard.one@sekyu.ph",
            password="SecurePassword123!",
            first_name="Ramon",
            last_name="Bautista",
            role=CustomUser.Role.GUARD,
        )
        self.admin = CustomUser.objects.create_user(
            username="admin_one",
            email="admin.one@sekyu.ph",
            password="SecurePassword123!",
            first_name="John",
            last_name="Molina",
            role=CustomUser.Role.ADMIN,
        )
        self.hh_a = Household.objects.create(
            user=self.resident_a,
            block_number=4,
            lot_number=9,
            street_name="Narra Street",
        )
        now = timezone.now()
        self.pass_a = VisitorPass.objects.create(
            household=self.hh_a,
            visitor_name="GrabFood Rider",
            visitor_phone="09171234567",
            visitor_type=VisitorPass.VisitorType.DELIVERY,
            access_pin="4821",
            valid_from=now - timedelta(minutes=30),
            valid_until=now + timedelta(hours=3),
            is_multi_entry=False,
            status=VisitorPass.Status.ACTIVE,
        )

    def test_anonymous_and_role_isolation_across_pass_routes(self):
        for url in (
            reverse("pass_list"),
            reverse("pass_create"),
            reverse("pass_detail", kwargs={"pk": self.pass_a.pk}),
            reverse("pass_edit", kwargs={"pk": self.pass_a.pk}),
            reverse("pass_delete", kwargs={"pk": self.pass_a.pk}),
            reverse("guard_pass_validate"),
            reverse("gate_log_list"),
        ):
            resp = self.client.get(url)
            self.assertEqual(resp.status_code, 302)
            self.assertIn(reverse("login"), resp.url)

        # Resident blocked from guard validation & gate logs (403)
        self.client.force_login(self.resident_a)
        self.assertEqual(self.client.get(reverse("guard_pass_validate")).status_code, 403)
        self.assertEqual(self.client.get(reverse("gate_log_list")).status_code, 403)

        # Guard blocked from resident pass views (403)
        self.client.force_login(self.guard)
        self.assertEqual(self.client.get(reverse("pass_list")).status_code, 403)
        self.assertEqual(self.client.get(reverse("pass_create")).status_code, 403)

        # Resident B blocked from Resident A's pass detail, edit, revoke, delete (403)
        self.client.force_login(self.resident_b)
        self.assertEqual(self.client.get(reverse("pass_list")).status_code, 200)
        self.assertEqual(self.client.get(reverse("pass_create")).status_code, 200)
        for name in ("pass_detail", "pass_edit", "pass_delete"):
            self.assertEqual(
                self.client.get(reverse(name, kwargs={"pk": self.pass_a.pk})).status_code,
                403,
            )
        self.assertEqual(
            self.client.post(reverse("pass_revoke", kwargs={"pk": self.pass_a.pk})).status_code,
            403,
        )
        self.assertEqual(
            self.client.post(reverse("pass_delete", kwargs={"pk": self.pass_a.pk})).status_code,
            403,
        )

    def test_resident_pass_crud_lifecycle(self):
        self.client.force_login(self.resident_a)
        now = timezone.localtime(timezone.now()).replace(second=0, microsecond=0)

        # List view and status filter
        self.assertEqual(self.client.get(reverse("pass_list")).status_code, 200)
        self.assertEqual(
            self.client.get(reverse("pass_list") + "?status=ACTIVE").status_code,
            200,
        )

        # Invalid create
        bad_create = self.client.post(
            reverse("pass_create"),
            {
                "household": self.hh_a.pk,
                "visitor_name": "",
                "visitor_type": VisitorPass.VisitorType.GUEST,
                "valid_from": (now + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M"),
                "valid_until": now.strftime("%Y-%m-%dT%H:%M"),
            },
        )
        self.assertEqual(bad_create.status_code, 200)

        # Valid create (future valid_from -> PENDING status; immediate valid_from -> ACTIVE status)
        future_resp = self.client.post(
            reverse("pass_create"),
            {
                "household": self.hh_a.pk,
                "visitor_name": "Future Contractor",
                "visitor_phone": "09178889999",
                "visitor_type": VisitorPass.VisitorType.CONTRACTOR,
                "valid_from": (now + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M"),
                "valid_until": (now + timedelta(hours=6)).strftime("%Y-%m-%dT%H:%M"),
                "is_multi_entry": "on",
            },
        )
        future_pass = VisitorPass.objects.get(visitor_name="Future Contractor")
        self.assertEqual(future_pass.status, VisitorPass.Status.PENDING)
        self.assertRedirects(future_resp, reverse("pass_detail", kwargs={"pk": future_pass.pk}))

        active_resp = self.client.post(
            reverse("pass_create"),
            {
                "household": self.hh_a.pk,
                "visitor_name": "Active Guest",
                "visitor_phone": "",
                "visitor_type": VisitorPass.VisitorType.GUEST,
                "valid_from": (now - timedelta(minutes=10)).strftime("%Y-%m-%dT%H:%M"),
                "valid_until": (now + timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M"),
            },
        )
        active_pass = VisitorPass.objects.get(visitor_name="Active Guest")
        self.assertEqual(active_pass.status, VisitorPass.Status.ACTIVE)
        self.assertRedirects(active_resp, reverse("pass_detail", kwargs={"pk": active_pass.pk}))

        # Edit pass (GET, invalid POST, valid POST with future and current start)
        self.assertEqual(
            self.client.get(reverse("pass_edit", kwargs={"pk": future_pass.pk})).status_code,
            200,
        )
        bad_edit = self.client.post(
            reverse("pass_edit", kwargs={"pk": future_pass.pk}),
            {
                "household": self.hh_a.pk,
                "visitor_name": "",
                "visitor_type": VisitorPass.VisitorType.CONTRACTOR,
                "valid_from": now.strftime("%Y-%m-%dT%H:%M"),
                "valid_until": (now - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M"),
            },
        )
        self.assertEqual(bad_edit.status_code, 200)

        ok_edit_active = self.client.post(
            reverse("pass_edit", kwargs={"pk": future_pass.pk}),
            {
                "household": self.hh_a.pk,
                "visitor_name": "Updated Contractor",
                "visitor_phone": "09178889999",
                "visitor_type": VisitorPass.VisitorType.CONTRACTOR,
                "valid_from": (now - timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M"),
                "valid_until": (now + timedelta(hours=4)).strftime("%Y-%m-%dT%H:%M"),
                "is_multi_entry": "on",
            },
        )
        self.assertRedirects(ok_edit_active, reverse("pass_detail", kwargs={"pk": future_pass.pk}))
        future_pass.refresh_from_db()
        self.assertEqual(future_pass.status, VisitorPass.Status.ACTIVE)

        ok_edit_pending = self.client.post(
            reverse("pass_edit", kwargs={"pk": future_pass.pk}),
            {
                "household": self.hh_a.pk,
                "visitor_name": "Updated Contractor",
                "visitor_phone": "09178889999",
                "visitor_type": VisitorPass.VisitorType.CONTRACTOR,
                "valid_from": (now + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M"),
                "valid_until": (now + timedelta(hours=4)).strftime("%Y-%m-%dT%H:%M"),
            },
        )
        self.assertRedirects(ok_edit_pending, reverse("pass_detail", kwargs={"pk": future_pass.pk}))
        future_pass.refresh_from_db()
        self.assertEqual(future_pass.status, VisitorPass.Status.PENDING)

        # Revoke pass & try revoking or editing an already-revoked pass
        rev_resp = self.client.post(
            reverse("pass_revoke", kwargs={"pk": future_pass.pk}),
            follow=True,
        )
        self.assertRedirects(rev_resp, reverse("pass_detail", kwargs={"pk": future_pass.pk}))
        future_pass.refresh_from_db()
        self.assertEqual(future_pass.status, VisitorPass.Status.REVOKED)

        rev_again = self.client.post(
            reverse("pass_revoke", kwargs={"pk": future_pass.pk}),
            follow=True,
        )
        self.assertTrue(
            any("cannot be revoked" in str(m) for m in get_messages(rev_again.wsgi_request))
        )

        edit_revoked = self.client.get(
            reverse("pass_edit", kwargs={"pk": future_pass.pk}),
            follow=True,
        )
        self.assertRedirects(edit_revoked, reverse("pass_detail", kwargs={"pk": future_pass.pk}))

        # Delete unused pass (GET confirm + POST delete)
        self.assertEqual(
            self.client.get(reverse("pass_delete", kwargs={"pk": future_pass.pk})).status_code,
            200,
        )
        del_resp = self.client.post(
            reverse("pass_delete", kwargs={"pk": future_pass.pk}),
            follow=True,
        )
        self.assertRedirects(del_resp, reverse("pass_list"))
        self.assertFalse(VisitorPass.objects.filter(pk=future_pass.pk).exists())

    def test_guard_pin_validation_and_gate_log_workflows(self):
        now = timezone.now()
        self.client.force_login(self.guard)

        # GET guard validate page
        self.assertEqual(self.client.get(reverse("guard_pass_validate")).status_code, 200)

        # 1. Invalid PIN format (BR-10)
        bad_pin = self.client.post(reverse("guard_pass_validate"), {"access_pin": "99"})
        self.assertEqual(bad_pin.status_code, 200)
        self.assertContains(bad_pin, "exact 4-digit numeric string")

        # 2. Non-existent 4-digit PIN -> NOT_FOUND
        not_found = self.client.post(reverse("guard_pass_validate"), {"access_pin": "9999"})
        self.assertEqual(not_found.status_code, 200)
        self.assertContains(not_found, "Unrecognized PIN: 9999")

        # 3. Valid single-entry pass -> GRANTED and transitions to USED (BR-15)
        grant_resp = self.client.post(
            reverse("guard_pass_validate"),
            {"access_pin": "4821", "remarks": "Courier ID verified"},
        )
        self.assertEqual(grant_resp.status_code, 200)
        self.assertContains(grant_resp, "GATE CLEARANCE GRANTED")
        self.pass_a.refresh_from_db()
        self.assertEqual(self.pass_a.status, VisitorPass.Status.USED)
        granted_log = GateAccessLog.objects.get(visitor_pass=self.pass_a)
        self.assertEqual(granted_log.verification_status, GateAccessLog.VerificationStatus.GRANTED)

        # 4. Reusing single-entry pass -> DENIED (already USED, BR-15)
        reuse_resp = self.client.post(reverse("guard_pass_validate"), {"access_pin": "4821"})
        self.assertEqual(reuse_resp.status_code, 200)
        self.assertContains(reuse_resp, "GATE CLEARANCE DENIED")
        self.assertContains(reuse_resp, "already Used")

        # 5. Expired pass -> DENIED and marked EXPIRED (BR-14)
        exp_pass = VisitorPass.objects.create(
            household=self.hh_a,
            visitor_name="Late Visitor",
            access_pin="1111",
            valid_from=now - timedelta(hours=4),
            valid_until=now - timedelta(minutes=5),
            status=VisitorPass.Status.ACTIVE,
        )
        exp_resp = self.client.post(reverse("guard_pass_validate"), {"access_pin": "1111"})
        self.assertContains(exp_resp, "GATE CLEARANCE DENIED")
        exp_pass.refresh_from_db()
        self.assertEqual(exp_pass.status, VisitorPass.Status.EXPIRED)

        # Re-validating an already EXPIRED pass hits the status == EXPIRED branch
        exp_again = self.client.post(reverse("guard_pass_validate"), {"access_pin": "1111"})
        self.assertContains(exp_again, "GATE CLEARANCE DENIED")

        # 6. Future pass not yet valid -> DENIED (BR-09)
        early_pass = VisitorPass.objects.create(
            household=self.hh_a,
            visitor_name="Early Visitor",
            access_pin="2222",
            valid_from=now + timedelta(hours=2),
            valid_until=now + timedelta(hours=5),
            status=VisitorPass.Status.PENDING,
        )
        early_resp = self.client.post(reverse("guard_pass_validate"), {"access_pin": "2222"})
        self.assertContains(early_resp, "not started yet")
        self.assertEqual(early_pass.status, VisitorPass.Status.PENDING)

        # 7. Multi-entry pass -> GRANTED and stays ACTIVE
        multi_pass = VisitorPass.objects.create(
            household=self.hh_a,
            visitor_name="Family Driver",
            access_pin="3333",
            valid_from=now - timedelta(minutes=15),
            valid_until=now + timedelta(hours=6),
            is_multi_entry=True,
            status=VisitorPass.Status.PENDING,
        )
        multi_resp = self.client.post(reverse("guard_pass_validate"), {"access_pin": "3333"})
        self.assertContains(multi_resp, "GATE CLEARANCE GRANTED")
        multi_pass.refresh_from_db()
        self.assertEqual(multi_pass.status, VisitorPass.Status.ACTIVE)

        # 8. Household becomes DELINQUENT -> DENIED (BR-13)
        self.hh_a.hoa_status = Household.HoaStatus.DELINQUENT
        self.hh_a.save()
        delinq_resp = self.client.post(reverse("guard_pass_validate"), {"access_pin": "3333"})
        self.assertContains(delinq_resp, "not HOA-verified or not in Good Standing")
        self.hh_a.hoa_status = Household.HoaStatus.GOOD_STANDING
        self.hh_a.save()

        # 9. Record exit on granted log, duplicate exit, and denied log (BR-18)
        denied_log = GateAccessLog.objects.filter(
            verification_status=GateAccessLog.VerificationStatus.DENIED
        ).first()
        self.client.post(reverse("record_gate_exit", kwargs={"pk": denied_log.pk}))
        denied_log.refresh_from_db()
        self.assertIsNone(denied_log.exit_timestamp)

        self.client.post(reverse("record_gate_exit", kwargs={"pk": granted_log.pk}))
        granted_log.refresh_from_db()
        self.assertIsNotNone(granted_log.exit_timestamp)

        # Duplicate exit attempt shows info message
        self.client.post(reverse("record_gate_exit", kwargs={"pk": granted_log.pk}))

        # 10. Gate log list view with filters for Guard and Admin
        self.assertEqual(
            self.client.get(reverse("gate_log_list") + "?status=GRANTED&q=GrabFood").status_code,
            200,
        )
        self.assertEqual(
            self.client.get(reverse("gate_log_list") + "?q=NoSuchVisitorXYZ").status_code,
            200,
        )
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse("gate_log_list")).status_code, 200)

        # 11. Resident viewing pass detail sees gate logs and cannot delete pass with logs (BR-19)
        self.client.force_login(self.resident_a)
        detail_resp = self.client.get(reverse("pass_detail", kwargs={"pk": self.pass_a.pk}))
        self.assertEqual(detail_resp.status_code, 200)
        self.assertContains(detail_resp, "Courier ID verified")

        prot_del = self.client.post(
            reverse("pass_delete", kwargs={"pk": self.pass_a.pk}),
            follow=True,
        )
        self.assertRedirects(prot_del, reverse("pass_detail", kwargs={"pk": self.pass_a.pk}))
        self.assertTrue(VisitorPass.objects.filter(pk=self.pass_a.pk).exists())
