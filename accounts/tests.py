import io
from unittest.mock import patch
from PIL import Image
from django.contrib import admin
from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.messages import get_messages
from django.contrib.messages.views import SuccessMessageMixin
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, connection, transaction
from django.test import Client, TestCase
from django.urls import resolve, reverse
from django.views.generic import UpdateView

from accounts.admin import CustomUserAdmin
from accounts.apps import AccountsConfig
from accounts.backends import EmailOrUsernameModelBackend
from accounts.forms import (
    BootstrapFormMixin,
    CustomAuthenticationForm,
    CustomerUserCreationForm,
    ProfileUpdateForm,
)
from accounts.models import CustomUser
from accounts.views import (
    CustomLoginView,
    CustomLogoutView,
    ProfileUpdateView,
    ProfileView,
    SignUpView,
)


def _make_test_png(name="avatar.png", color=(15, 118, 110)):
    buf = io.BytesIO()
    Image.new("RGB", (32, 32), color=color).save(buf, format="PNG")
    buf.seek(0)
    return SimpleUploadedFile(name, buf.read(), content_type="image/png")


class CustomUserModelTests(TestCase):
    def test_app_config_and_admin_registration(self):
        self.assertEqual(AccountsConfig.name, "accounts")
        self.assertIn(CustomUser, admin.site._registry)
        self.assertIsInstance(admin.site._registry[CustomUser], CustomUserAdmin)

    def test_model_save_normalization_and_role_approval_defaults(self):
        resident = CustomUser.objects.create_user(
            username="res_norm",
            email="  RES.Norm@Sekyu.PH  ",
            password="SecurePassword123!",
            first_name="Juan",
            last_name="Dela Cruz",
            role=CustomUser.Role.RESIDENT,
        )
        self.assertEqual(resident.email, "res.norm@sekyu.ph")
        self.assertFalse(resident.is_approved)
        self.assertEqual(resident.full_name, "Juan Dela Cruz")
        self.assertEqual(str(resident), "res_norm (Subdivision Resident)")

        guard = CustomUser.objects.create_user(
            username="guard_auto",
            email="guard.auto@sekyu.ph",
            password="SecurePassword123!",
            role=CustomUser.Role.GUARD,
        )
        self.assertTrue(guard.is_approved)
        self.assertEqual(guard.full_name, "guard_auto")

        admin_u = CustomUser.objects.create_user(
            username="admin_auto",
            email="admin.auto@sekyu.ph",
            password="SecurePassword123!",
            role=CustomUser.Role.ADMIN,
        )
        self.assertTrue(admin_u.is_approved)

    def test_superuser_auto_approved_and_db_constraints_enforced(self):
        su = CustomUser.objects.create_superuser(
            username="super_hoa",
            email="super@sekyu.ph",
            password="SecurePassword123!",
        )
        self.assertTrue(su.is_approved)

        # Blank email exercises save() when self.email is empty
        blank_email_u = CustomUser.objects.create_user(
            username="blank_email_u",
            email="",
            password="SecurePassword123!",
        )
        self.assertEqual(blank_email_u.email, "")

        # Duplicate email violates DB unique constraint
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                CustomUser.objects.create_user(
                    username="dup_email_user",
                    email="super@sekyu.ph",
                    password="SecurePassword123!",
                )

        # Invalid role violates DB CheckConstraint (users_role_valid_check)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        INSERT INTO users (
                            password, is_superuser, username, first_name, last_name,
                            is_staff, is_active, date_joined, email, role, phone_number, is_approved
                        ) VALUES (
                            'pbkdf2_sha256$1$x$y', false, 'bad_role_u', '', '',
                            false, true, NOW(), 'badrole@sekyu.ph', 'HACKER', '', false
                        )
                        """
                    )


class EmailOrUsernameBackendTests(TestCase):
    def setUp(self):
        self.user = CustomUser.objects.create_user(
            username="resident_one",
            email="resident.one@sekyu.ph",
            password="SecurePassword123!",
            role=CustomUser.Role.RESIDENT,
        )
        self.inactive_user = CustomUser.objects.create_user(
            username="inactive_res",
            email="inactive@sekyu.ph",
            password="SecurePassword123!",
            is_active=False,
        )
        self.backend = EmailOrUsernameModelBackend()

    def test_authenticate_username_email_and_failure_paths(self):
        self.assertEqual(
            authenticate(username="RESIDENT_ONE", password="SecurePassword123!"),
            self.user,
        )
        self.assertEqual(
            authenticate(username="Resident.One@Sekyu.PH", password="SecurePassword123!"),
            self.user,
        )
        # kwargs USERNAME_FIELD fallback when username=None
        with patch("accounts.backends.UserModel.USERNAME_FIELD", "login_id"):
            self.assertEqual(
                self.backend.authenticate(
                    None, username=None, password="SecurePassword123!", login_id="resident_one"
                ),
                self.user,
            )
        # Missing credentials
        self.assertIsNone(self.backend.authenticate(None, username="", password="SecurePassword123!"))
        self.assertIsNone(self.backend.authenticate(None, username="resident_one", password=None))
        # Non-existent user triggers timing-safe path
        self.assertIsNone(self.backend.authenticate(None, username="ghost_user", password="any"))
        # Wrong password
        self.assertIsNone(self.backend.authenticate(None, username="resident_one", password="Wrong!"))
        # Inactive user
        self.assertIsNone(self.backend.authenticate(None, username="inactive_res", password="SecurePassword123!"))

    def test_backend_handles_does_not_exist_exception_gracefully(self):
        with patch.object(CustomUser._default_manager, "filter", side_effect=CustomUser.DoesNotExist):
            self.assertIsNone(self.backend.authenticate(None, username="resident_one", password="SecurePassword123!"))


class AccountFormsTests(TestCase):
    def setUp(self):
        self.existing = CustomUser.objects.create_user(
            username="existing_res",
            email="existing@sekyu.ph",
            password="SecurePassword123!",
            first_name="Ana",
            last_name="Cruz",
            phone_number="09171234567",
        )
        self.other = CustomUser.objects.create_user(
            username="other_res",
            email="other@sekyu.ph",
            password="SecurePassword123!",
        )

    def test_bootstrap_mixin_handles_checkbox_and_invalid_classes(self):
        from django import forms

        class DummyForm(BootstrapFormMixin, forms.Form):
            agree = forms.BooleanField(required=True)
            agree_pre = forms.BooleanField(
                required=False,
                widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
            )
            note = forms.CharField(required=True)
            note_pre = forms.CharField(
                required=True,
                widget=forms.TextInput(attrs={"class": "form-control is-invalid"}),
            )

            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self._apply_bootstrap_classes()

        form = DummyForm(data={})
        self.assertFalse(form.is_valid())
        self.assertIn("form-check-input", form.fields["agree"].widget.attrs["class"])
        self.assertIn("is-invalid", form.fields["agree"].widget.attrs["class"])
        self.assertIn("form-check-input", form.fields["agree_pre"].widget.attrs["class"])
        self.assertIn("form-control", form.fields["note"].widget.attrs["class"])
        self.assertIn("is-invalid", form.fields["note_pre"].widget.attrs["class"])

    def test_signup_form_validation_and_commit_false(self):
        # Empty email / duplicate email / duplicate username
        bad_form = CustomerUserCreationForm(
            data={
                "username": "EXISTING_RES",
                "email": "EXISTING@sekyu.ph",
                "first_name": "Test",
                "last_name": "User",
                "phone_number": "09170000000",
                "password1": "StrongGatePass123!@#",
                "password2": "Mismatch123!",
            }
        )
        self.assertFalse(bad_form.is_valid())
        self.assertIn("username", bad_form.errors)
        self.assertIn("email", bad_form.errors)
        self.assertIn("password2", bad_form.errors)

        # Direct clean_email when cleaned_data has empty email
        empty_email_form = CustomerUserCreationForm(
            data={
                "username": "brand_new",
                "email": "",
                "first_name": "Brand",
                "last_name": "New",
                "phone_number": "09171112222",
                "password1": "StrongGatePass123!@#",
                "password2": "StrongGatePass123!@#",
            }
        )
        self.assertFalse(empty_email_form.is_valid())
        self.assertIn("email", empty_email_form.errors)
        empty_email_form.cleaned_data = {"email": ""}
        with self.assertRaises(Exception):
            empty_email_form.clean_email()

        # Valid save(commit=False)
        valid_form = CustomerUserCreationForm(
            data={
                "username": "fresh_res",
                "email": "Fresh.Res@Sekyu.PH",
                "first_name": "Liza",
                "last_name": "Ramos",
                "phone_number": "09179998888",
                "password1": "StrongGatePass123!@#",
                "password2": "StrongGatePass123!@#",
            }
        )
        self.assertTrue(valid_form.is_valid(), valid_form.errors)
        unsaved = valid_form.save(commit=False)
        self.assertIsNone(unsaved.pk)
        self.assertEqual(unsaved.role, CustomUser.Role.RESIDENT)
        self.assertFalse(unsaved.is_approved)

    def test_profile_update_form_email_uniqueness_and_own_email(self):
        # Allowing own email
        own_form = ProfileUpdateForm(
            instance=self.existing,
            data={
                "first_name": "Ana",
                "last_name": "Cruz",
                "email": "EXISTING@sekyu.ph",
                "phone_number": "09171234567",
            },
        )
        self.assertTrue(own_form.is_valid(), own_form.errors)

        # Rejecting another user's email
        dup_form = ProfileUpdateForm(
            instance=self.existing,
            data={
                "first_name": "Ana",
                "last_name": "Cruz",
                "email": "other@sekyu.ph",
                "phone_number": "09171234567",
            },
        )
        self.assertFalse(dup_form.is_valid())
        self.assertIn("email", dup_form.errors)

        # Unbound/no-pk instance branch
        new_profile_form = ProfileUpdateForm(
            data={
                "first_name": "New",
                "last_name": "Profile",
                "email": "brandnew@sekyu.ph",
                "phone_number": "09170001122",
            }
        )
        self.assertTrue(new_profile_form.is_valid(), new_profile_form.errors)

        # Empty email branch
        empty_form = ProfileUpdateForm(instance=self.existing, data={"first_name": "A", "last_name": "B", "email": ""})
        self.assertFalse(empty_form.is_valid())
        empty_form.cleaned_data = {"email": ""}
        with self.assertRaises(Exception):
            empty_form.clean_email()


class AccountViewsAndTemplatesTests(TestCase):
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
            first_name="",
            last_name="",
            phone_number="",
            role=CustomUser.Role.RESIDENT,
            is_approved=True,
        )

    def test_signup_login_logout_flow_and_messages(self):
        self.assertEqual(self.client.get(reverse("signup")).status_code, 200)
        self.assertEqual(self.client.get(reverse("login")).status_code, 200)

        # Invalid signup renders field errors
        bad_signup = self.client.post(reverse("signup"), {"username": ""})
        self.assertEqual(bad_signup.status_code, 200)
        self.assertContains(bad_signup, "This field is required")

        # Valid signup creates hashed resident and shows Bootstrap success alert
        signup_resp = self.client.post(
            reverse("signup"),
            {
                "username": "new_homeowner",
                "email": "new.homeowner@sekyu.ph",
                "first_name": "Elena",
                "last_name": "Reyes",
                "phone_number": "+63 917 999 0000",
                "password1": "StrongGatePass123!@#",
                "password2": "StrongGatePass123!@#",
            },
            follow=True,
        )
        self.assertRedirects(signup_resp, reverse("login"))
        created = CustomUser.objects.get(username="new_homeowner")
        self.assertTrue(created.check_password("StrongGatePass123!@#"))
        self.assertRegex(
            signup_resp.content.decode("utf-8"),
            r'class="[^"]*\balert\b[^"]*\balert-success\b[^"]*"[^>]*role="alert"',
        )

        # Invalid login displays error message + form error
        bad_login = self.client.post(
            reverse("login"),
            {"username": "resident_a", "password": "WrongPassword!"},
        )
        self.assertEqual(bad_login.status_code, 200)
        self.assertContains(bad_login, "Invalid username/email or password")

        # Empty login renders field errors
        empty_login = self.client.post(reverse("login"), {"username": "", "password": ""})
        self.assertEqual(empty_login.status_code, 200)

        # Valid login via email + logout info message
        login_resp = self.client.post(
            reverse("login"),
            {"username": "resident_a@sekyu.ph", "password": "SecurePassword123!"},
        )
        self.assertRedirects(login_resp, reverse("dashboard"), fetch_redirect_response=False)

        logout_resp = self.client.post(reverse("logout"), follow=True)
        self.assertRedirects(logout_resp, reverse("login"))
        msgs = [str(m) for m in get_messages(logout_resp.wsgi_request)]
        self.assertTrue(any("safely signed out" in m for m in msgs))

        # Anonymous logout still redirects cleanly without message
        anon_logout = self.client.post(reverse("logout"))
        self.assertEqual(anon_logout.status_code, 302)

    def test_profile_isolation_photo_upload_and_template_branches(self):
        # Anonymous redirected to login
        for name in ("profile", "profile_edit"):
            resp = self.client.get(reverse(name))
            self.assertEqual(resp.status_code, 302)
            self.assertIn(reverse("login"), resp.url)

        # Also test ProfileView direct dispatch when unauthenticated
        from django.test import RequestFactory
        from django.contrib.auth.models import AnonymousUser

        rf = RequestFactory()
        req = rf.get(reverse("profile"))
        req.user = AnonymousUser()
        anon_dispatch = ProfileView.as_view()(req)
        self.assertEqual(anon_dispatch.status_code, 302)

        # Login as resident_a (pending, no photo yet)
        self.client.force_login(self.resident_a)
        self.assertEqual(self.client.get(reverse("profile")).status_code, 200)
        self.assertEqual(
            self.client.get(reverse("profile_detail", kwargs={"pk": self.resident_a.pk})).status_code,
            200,
        )
        self.assertEqual(
            self.client.get(reverse("profile_detail", kwargs={"pk": self.resident_b.pk})).status_code,
            403,
        )
        self.assertEqual(
            self.client.get(reverse("profile_edit_pk", kwargs={"pk": self.resident_b.pk})).status_code,
            403,
        )
        self.assertEqual(self.client.get(reverse("profile_edit")).status_code, 200)

        # Invalid profile edit renders field errors
        bad_edit = self.client.post(
            reverse("profile_edit"),
            {"first_name": "", "last_name": "", "email": "not-an-email"},
        )
        self.assertEqual(bad_edit.status_code, 200)
        self.assertContains(bad_edit, "Enter a valid email address")

        # Valid edit with photo upload
        ok_edit = self.client.post(
            reverse("profile_edit"),
            {
                "first_name": "Juanito",
                "last_name": "Dela Cruz",
                "email": "juanito@sekyu.ph",
                "phone_number": "+63 917 888 9999",
                "profile_photo": _make_test_png(),
            },
            follow=True,
        )
        self.assertEqual(ok_edit.status_code, 200)
        self.resident_a.refresh_from_db()
        self.assertTrue(bool(self.resident_a.profile_photo))
        # Visit edit page again to exercise existing profile_photo preview branch
        self.assertEqual(self.client.get(reverse("profile_edit")).status_code, 200)

        # Login as resident_b (approved, blank first/last name) to cover those template branches
        self.client.force_login(self.resident_b)
        prof_b = self.client.get(reverse("profile"))
        self.assertEqual(prof_b.status_code, 200)
        self.assertContains(prof_b, "HOA Verified")
        self.assertContains(prof_b, "Not specified")
        self.assertEqual(self.client.get(reverse("profile_edit")).status_code, 200)

    def test_csrf_protection_and_cbv_architecture(self):
        csrf_client = Client(enforce_csrf_checks=True)
        for url in (reverse("login"), reverse("signup"), reverse("profile_edit")):
            self.assertEqual(csrf_client.post(url, {"username": "x"}).status_code, 403)

        resolved = resolve(reverse("profile_edit"))
        view_cls = resolved.func.view_class
        self.assertEqual(view_cls, ProfileUpdateView)
        self.assertTrue(issubclass(view_cls, UpdateView))
        self.assertTrue(issubclass(view_cls, LoginRequiredMixin))
        self.assertTrue(issubclass(view_cls, SuccessMessageMixin))
        self.assertTrue(issubclass(SignUpView, SuccessMessageMixin))
        self.assertEqual(resolve(reverse("login")).func.view_class, CustomLoginView)
        self.assertEqual(resolve(reverse("logout")).func.view_class, CustomLogoutView)
