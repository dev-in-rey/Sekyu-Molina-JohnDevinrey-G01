from django import forms
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.core.exceptions import ValidationError
from .models import CustomUser


class BootstrapFormMixin:
    def _apply_bootstrap_classes(self):
        for name, field in self.fields.items():
            css = field.widget.attrs.get("class", "")
            classes = css.split() if css else []
            if isinstance(field.widget, forms.CheckboxInput):
                if "form-check-input" not in classes:
                    classes.append("form-check-input")
            else:
                if "form-control" not in classes:
                    classes.append("form-control")
            if self.is_bound and self.errors.get(name):
                if "is-invalid" not in classes:
                    classes.append("is-invalid")
            field.widget.attrs["class"] = " ".join(classes)


class CustomAuthenticationForm(BootstrapFormMixin, AuthenticationForm):
    username = forms.CharField(
        label="Username or Email Address",
        widget=forms.TextInput(
            attrs={
                "autofocus": True,
                "placeholder": "Enter your username or email",
            }
        ),
    )

    error_messages = {
        "invalid_login": (
            "Invalid username/email or password. Please verify your credentials and try again."
        ),
        "inactive": "This account is currently inactive. Please contact the HOA Administration.",
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._apply_bootstrap_classes()


class CustomerUserCreationForm(BootstrapFormMixin, UserCreationForm):
    first_name = forms.CharField(
        max_length=150,
        required=True,
        label="First Name",
        widget=forms.TextInput(attrs={"placeholder": "e.g. Juan"}),
    )
    last_name = forms.CharField(
        max_length=150,
        required=True,
        label="Last Name",
        widget=forms.TextInput(attrs={"placeholder": "e.g. Dela Cruz"}),
    )
    email = forms.EmailField(
        max_length=100,
        required=True,
        label="Email Address",
        widget=forms.EmailInput(attrs={"placeholder": "e.g. juan.delacruz@example.com"}),
    )
    phone_number = forms.CharField(
        max_length=20,
        required=True,
        label="Contact Number",
        widget=forms.TextInput(attrs={"placeholder": "e.g. +63 917 123 4567"}),
    )

    class Meta(UserCreationForm.Meta):
        model = CustomUser
        fields = ("username", "email", "first_name", "last_name", "phone_number")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._apply_bootstrap_classes()

    def clean_email(self):
        email = self.cleaned_data.get("email", "").strip().lower()
        if not email:
            raise ValidationError("An email address is required.")
        if CustomUser.objects.filter(email__iexact=email).exists():
            raise ValidationError("A user with that email address already exists.")
        return email

    def clean_username(self):
        username = self.cleaned_data.get("username", "").strip()
        if CustomUser.objects.filter(username__iexact=username).exists():
            raise ValidationError("A user with that username already exists.")
        return username

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data["email"]
        user.role = CustomUser.Role.RESIDENT
        user.is_approved = False
        if commit:
            user.save()
        return user


class ProfileUpdateForm(BootstrapFormMixin, forms.ModelForm):
    first_name = forms.CharField(max_length=150, required=True, label="First Name")
    last_name = forms.CharField(max_length=150, required=True, label="Last Name")
    email = forms.EmailField(max_length=100, required=True, label="Email Address")
    phone_number = forms.CharField(max_length=20, required=False, label="Contact Number")

    class Meta:
        model = CustomUser
        fields = ("first_name", "last_name", "email", "phone_number", "profile_photo")
        widgets = {
            "profile_photo": forms.FileInput(attrs={"accept": "image/*"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._apply_bootstrap_classes()

    def clean_email(self):
        email = self.cleaned_data.get("email", "").strip().lower()
        if not email:
            raise ValidationError("An email address is required.")
        qs = CustomUser.objects.filter(email__iexact=email)
        if self.instance and self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError("Another account is already using this email address.")
        return email
