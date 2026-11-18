from unittest.mock import patch
from django.contrib import admin
from django.contrib.messages import get_messages
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.test import Client, TestCase
from django.urls import reverse

from accounts.models import CustomUser
from households.admin import HouseholdAdmin
from households.apps import HouseholdsConfig
from households.forms import HouseholdForm
from households.models import Household


class HouseholdModelAndFormTests(TestCase):
    def setUp(self):
        self.resident_approved = CustomUser.objects.create_user(
            username="res_approved",
            email="res.approved@sekyu.ph",
            password="SecurePassword123!",
            first_name="Maria",
            last_name="Santos",
            role=CustomUser.Role.RESIDENT,
            is_approved=True,
        )
        self.resident_pending = CustomUser.objects.create_user(
            username="res_pending",
            email="res.pending@sekyu.ph",
            password="SecurePassword123!",
            first_name="Juan",
            last_name="Cruz",
            role=CustomUser.Role.RESIDENT,
            is_approved=False,
        )
        self.household = Household.objects.create(
            user=self.resident_approved,
            block_number=5,
            lot_number=12,
            street_name="  Narra   Street  ",
        )

    def test_app_config_and_admin_registration(self):
        self.assertEqual(HouseholdsConfig.name, "households")
        self.assertIn(Household, admin.site._registry)
        self.assertIsInstance(admin.site._registry[Household], HouseholdAdmin)

    def test_household_properties_normalization_and_constraints(self):
        self.assertEqual(self.household.street_name, "Narra Street")
        self.assertEqual(self.household.unit_label, "Block 5, Lot 12, Narra Street")
        self.assertEqual(str(self.household), "Block 5, Lot 12, Narra Street (res_approved)")
        self.assertTrue(self.household.is_verified_for_passes)

        # Delinquent household or unapproved user is not verified for passes (BR-13)
        self.household.hoa_status = Household.HoaStatus.DELINQUENT
        self.household.save()
        self.assertFalse(self.household.is_verified_for_passes)

        pending_hh = Household.objects.create(
            user=self.resident_pending,
            block_number=2,
            lot_number=4,
            street_name="Molave Avenue",
        )
        self.assertFalse(pending_hh.is_verified_for_passes)

        # Empty street branch in save()
        empty_street_hh = Household(
            user=self.resident_approved,
            block_number=9,
            lot_number=9,
            street_name="",
        )
        empty_street_hh.save()
        self.assertEqual(empty_street_hh.street_name, "")

        # Duplicate block, lot, street violates UniqueConstraint (BR-04)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Household.objects.create(
                    user=self.resident_pending,
                    block_number=5,
                    lot_number=12,
                    street_name="Narra Street",
                )

        # User deletion is blocked by PROTECT (BR-05)
        with self.assertRaises(ProtectedError):
            self.resident_approved.delete()

    def test_household_form_validation_and_duplicate_check(self):
        # Invalid block, lot, and blank street
        bad_form = HouseholdForm(
            data={
                "block_number": 0,
                "lot_number": -3,
                "street_name": "   ",
            }
        )
        self.assertFalse(bad_form.is_valid())
        self.assertIn("block_number", bad_form.errors)
        self.assertIn("lot_number", bad_form.errors)
        self.assertIn("street_name", bad_form.errors)

        # Direct clean method checks for non-positive integers and blank street
        bad_form.cleaned_data = {"block_number": 0, "lot_number": 0, "street_name": "   "}
        with self.assertRaises(Exception):
            bad_form.clean_block_number()
        with self.assertRaises(Exception):
            bad_form.clean_lot_number()
        with self.assertRaises(Exception):
            bad_form.clean_street_name()

        # Duplicate block/lot/street (case-insensitive) rejected by clean() (BR-04)
        dup_form = HouseholdForm(
            data={
                "block_number": 5,
                "lot_number": 12,
                "street_name": "narra street",
            }
        )
        self.assertFalse(dup_form.is_valid())
        self.assertIn("__all__", dup_form.errors)

        # Updating existing instance with its own block/lot/street succeeds
        own_form = HouseholdForm(
            instance=self.household,
            data={
                "block_number": 5,
                "lot_number": 12,
                "street_name": "Narra Street",
            },
        )
        self.assertTrue(own_form.is_valid(), own_form.errors)


class HouseholdViewsAndRoleIsolationTests(TestCase):
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
            username="guard_hh",
            email="guard.hh@sekyu.ph",
            password="SecurePassword123!",
            role=CustomUser.Role.GUARD,
        )
        self.admin = CustomUser.objects.create_user(
            username="admin_hh",
            email="admin.hh@sekyu.ph",
            password="SecurePassword123!",
            role=CustomUser.Role.ADMIN,
        )
        self.hh_a = Household.objects.create(
            user=self.resident_a,
            block_number=3,
            lot_number=8,
            street_name="Acacia Street",
        )

    def test_anonymous_and_cross_role_access_controls(self):
        for url in (
            reverse("household_list"),
            reverse("household_create"),
            reverse("household_edit", kwargs={"pk": self.hh_a.pk}),
            reverse("household_delete", kwargs={"pk": self.hh_a.pk}),
            reverse("admin_household_list"),
        ):
            resp = self.client.get(url)
            self.assertEqual(resp.status_code, 302)
            self.assertIn(reverse("login"), resp.url)

        # Guard blocked from all household views (403)
        self.client.force_login(self.guard)
        self.assertEqual(self.client.get(reverse("household_list")).status_code, 403)
        self.assertEqual(self.client.get(reverse("household_create")).status_code, 403)
        self.assertEqual(self.client.get(reverse("admin_household_list")).status_code, 403)

        # Admin blocked from resident CRUD views, Resident blocked from admin household views
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse("household_list")).status_code, 403)
        self.client.force_login(self.resident_a)
        self.assertEqual(self.client.get(reverse("admin_household_list")).status_code, 403)
        self.assertEqual(
            self.client.post(
                reverse("manage_household_status", kwargs={"pk": self.hh_a.pk}),
                {"hoa_status": "DELINQUENT"},
            ).status_code,
            403,
        )

    def test_resident_crud_and_ownership_isolation(self):
        # Resident B sees empty state and gets 403 on Resident A's household
        self.client.force_login(self.resident_b)
        list_b = self.client.get(reverse("household_list"))
        self.assertEqual(list_b.status_code, 200)
        self.assertContains(list_b, "No household units registered yet")
        self.assertNotContains(list_b, "Acacia Street")
        self.assertEqual(
            self.client.get(reverse("household_edit", kwargs={"pk": self.hh_a.pk})).status_code,
            403,
        )
        self.assertEqual(
            self.client.get(reverse("household_delete", kwargs={"pk": self.hh_a.pk})).status_code,
            403,
        )
        self.assertEqual(
            self.client.post(reverse("household_delete", kwargs={"pk": self.hh_a.pk})).status_code,
            403,
        )

        # Resident B creates a household (invalid first, then valid)
        self.assertEqual(self.client.get(reverse("household_create")).status_code, 200)
        bad_create = self.client.post(
            reverse("household_create"),
            {"block_number": 3, "lot_number": 8, "street_name": "Acacia Street"},
        )
        self.assertEqual(bad_create.status_code, 200)
        self.assertContains(bad_create, "already registered")

        ok_create = self.client.post(
            reverse("household_create"),
            {"block_number": 7, "lot_number": 15, "street_name": "Kamagong Road"},
            follow=True,
        )
        self.assertRedirects(ok_create, reverse("household_list"))
        hh_b = Household.objects.get(user=self.resident_b, block_number=7)

        # Update own household (invalid then valid)
        self.assertEqual(
            self.client.get(reverse("household_edit", kwargs={"pk": hh_b.pk})).status_code,
            200,
        )
        bad_edit = self.client.post(
            reverse("household_edit", kwargs={"pk": hh_b.pk}),
            {"block_number": 3, "lot_number": 8, "street_name": "Acacia Street"},
        )
        self.assertEqual(bad_edit.status_code, 200)

        ok_edit = self.client.post(
            reverse("household_edit", kwargs={"pk": hh_b.pk}),
            {"block_number": 7, "lot_number": 16, "street_name": "Kamagong Road"},
            follow=True,
        )
        self.assertRedirects(ok_edit, reverse("household_list"))
        hh_b.refresh_from_db()
        self.assertEqual(hh_b.lot_number, 16)

        # Delete confirmation page & ProtectedError handling vs successful delete
        self.assertEqual(
            self.client.get(reverse("household_delete", kwargs={"pk": hh_b.pk})).status_code,
            200,
        )
        with patch.object(Household, "delete", side_effect=ProtectedError("Protected", [hh_b])):
            prot_resp = self.client.post(
                reverse("household_delete", kwargs={"pk": hh_b.pk}),
                follow=True,
            )
            self.assertRedirects(prot_resp, reverse("household_list"))
            self.assertTrue(
                any("Cannot delete" in str(m) for m in get_messages(prot_resp.wsgi_request))
            )

        del_resp = self.client.post(
            reverse("household_delete", kwargs={"pk": hh_b.pk}),
            follow=True,
        )
        self.assertRedirects(del_resp, reverse("household_list"))
        self.assertFalse(Household.objects.filter(pk=hh_b.pk).exists())

    def test_admin_household_directory_and_status_updates(self):
        self.client.force_login(self.admin)
        resp = self.client.get(reverse("admin_household_list"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Acacia Street")

        # Update HOA standing through GOOD_STANDING, DELINQUENT, INACTIVE, and invalid choice
        status_url = reverse("manage_household_status", kwargs={"pk": self.hh_a.pk})
        for status_val in (
            Household.HoaStatus.DELINQUENT,
            Household.HoaStatus.INACTIVE,
            Household.HoaStatus.GOOD_STANDING,
        ):
            post_resp = self.client.post(status_url, {"hoa_status": status_val}, follow=True)
            self.assertRedirects(post_resp, reverse("admin_household_list"))
            self.hh_a.refresh_from_db()
            self.assertEqual(self.hh_a.hoa_status, status_val)

        # Also exercise resident list rendering for DELINQUENT and INACTIVE badges
        self.hh_a.hoa_status = Household.HoaStatus.DELINQUENT
        self.hh_a.save()
        Household.objects.create(
            user=self.resident_b,
            block_number=10,
            lot_number=2,
            street_name="Yakal Street",
            hoa_status=Household.HoaStatus.INACTIVE,
        )
        self.assertEqual(self.client.get(reverse("admin_household_list")).status_code, 200)
        self.client.force_login(self.resident_a)
        self.assertEqual(self.client.get(reverse("household_list")).status_code, 200)
        self.client.force_login(self.resident_b)
        self.assertEqual(self.client.get(reverse("household_list")).status_code, 200)

        # Invalid status rejected
        self.client.force_login(self.admin)
        bad_status = self.client.post(status_url, {"hoa_status": "BOGUS"}, follow=True)
        self.assertTrue(
            any("Invalid HOA standing" in str(m) for m in get_messages(bad_status.wsgi_request))
        )

        # Empty admin household directory state
        Household.objects.all().delete()
        empty_admin = self.client.get(reverse("admin_household_list"))
        self.assertContains(empty_admin, "No household units registered yet")
