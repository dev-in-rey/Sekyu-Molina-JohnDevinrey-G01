import re
from datetime import timedelta
from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone

from accounts.forms import BootstrapFormMixin
from households.models import Household
from .models import VisitorPass


class VisitorPassForm(BootstrapFormMixin, forms.ModelForm):
    visitor_name = forms.CharField(
        max_length=100,
        required=True,
        label="Visitor Full Name",
        widget=forms.TextInput(
            attrs={
                "placeholder": "e.g. Carlo Mendoza (GrabExpress)",
            }
        ),
    )
    visitor_phone = forms.CharField(
        max_length=20,
        required=False,
        label="Visitor Contact Number (Optional)",
        widget=forms.TextInput(
            attrs={
                "placeholder": "e.g. +63 917 555 0199",
            }
        ),
    )
    valid_from = forms.DateTimeField(
        required=True,
        label="Valid From",
        input_formats=["%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"],
        widget=forms.DateTimeInput(
            attrs={"type": "datetime-local"},
            format="%Y-%m-%dT%H:%M",
        ),
    )
    valid_until = forms.DateTimeField(
        required=True,
        label="Valid Until (Expiration)",
        input_formats=["%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"],
        widget=forms.DateTimeInput(
            attrs={"type": "datetime-local"},
            format="%Y-%m-%dT%H:%M",
        ),
    )

    class Meta:
        model = VisitorPass
        fields = (
            "household",
            "visitor_name",
            "visitor_phone",
            "visitor_type",
            "valid_from",
            "valid_until",
            "is_multi_entry",
        )
        labels = {
            "household": "Destination Household Unit",
            "visitor_type": "Visitor Category",
            "is_multi_entry": "Allow multiple entries within validity window",
        }

    def __init__(self, *args, user=None, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)
        if self.user is not None:
            self.fields["household"].queryset = Household.objects.filter(
                user=self.user
            ).order_by("block_number", "lot_number")
        if not self.is_bound and not self.instance.pk:
            now_local = timezone.localtime(timezone.now()).replace(second=0, microsecond=0)
            self.initial.setdefault("valid_from", now_local.strftime("%Y-%m-%dT%H:%M"))
            self.initial.setdefault(
                "valid_until",
                (now_local + timedelta(hours=4)).strftime("%Y-%m-%dT%H:%M"),
            )
        self._apply_bootstrap_classes()
        for field_name in ("household", "visitor_type"):
            css = self.fields[field_name].widget.attrs.get("class", "")
            if "form-select" not in css:
                self.fields[field_name].widget.attrs["class"] = f"{css} form-select".strip()

    def clean_visitor_name(self):
        name = " ".join(self.cleaned_data.get("visitor_name", "").strip().split())
        if not name:
            raise ValidationError("Visitor full name is required.")
        return name

    def clean_visitor_phone(self):
        phone = (self.cleaned_data.get("visitor_phone") or "").strip()
        if phone and not re.fullmatch(r"^[0-9+\-\s()]{7,20}$", phone):
            raise ValidationError(
                "Enter a valid contact phone number (7 to 20 digits, +, -, spaces, or parentheses)."
            )
        return phone or None

    def clean_household(self):
        household = self.cleaned_data.get("household")
        if self.user is not None and not self.user.is_approved:
            raise ValidationError(
                "Your resident account must be approved by an HOA Administrator before generating visitor passes (BR-13)."
            )
        if household and not household.is_verified_for_passes:
            raise ValidationError(
                "Visitor passes cannot be generated for a household unit that is not verified or not in Good Standing with the HOA (BR-13)."
            )
        return household

    def clean(self):
        cleaned_data = super().clean()
        valid_from = cleaned_data.get("valid_from")
        valid_until = cleaned_data.get("valid_until")
        if valid_from and valid_until and valid_until <= valid_from:
            raise ValidationError(
                "Scheduled expiration time (Valid Until) must be later than the start time (Valid From) (BR-09)."
            )
        return cleaned_data


class GuardPinValidationForm(BootstrapFormMixin, forms.Form):
    access_pin = forms.CharField(
        max_length=4,
        required=True,
        label="4-Digit Visitor Access PIN",
        widget=forms.TextInput(
            attrs={
                "placeholder": "0000",
                "inputmode": "numeric",
                "maxlength": "4",
                "autocomplete": "off",
                "autofocus": True,
                "class": "form-control font-mono-code text-center fs-4 fw-bold",
            }
        ),
    )
    remarks = forms.CharField(
        max_length=255,
        required=False,
        label="Checkpoint Remarks (Optional)",
        widget=forms.TextInput(
            attrs={
                "placeholder": "e.g. Plate ABC-1234, courier ID verified at gatehouse",
            }
        ),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._apply_bootstrap_classes()

    def clean_access_pin(self):
        pin = (self.cleaned_data.get("access_pin") or "").strip()
        if not re.fullmatch(r"^[0-9]{4}$", pin):
            raise ValidationError(
                "Access PIN must consist of an exact 4-digit numeric string (BR-10)."
            )
        return pin
