from django import forms
from django.core.exceptions import ValidationError

from accounts.forms import BootstrapFormMixin
from .models import Household


class HouseholdForm(BootstrapFormMixin, forms.ModelForm):
    block_number = forms.IntegerField(
        min_value=1,
        required=True,
        label="Block Number",
        widget=forms.NumberInput(
            attrs={
                "placeholder": "e.g. 5",
                "min": "1",
            }
        ),
    )
    lot_number = forms.IntegerField(
        min_value=1,
        required=True,
        label="Lot Number",
        widget=forms.NumberInput(
            attrs={
                "placeholder": "e.g. 12",
                "min": "1",
            }
        ),
    )
    street_name = forms.CharField(
        max_length=100,
        required=True,
        label="Street Name",
        widget=forms.TextInput(
            attrs={
                "placeholder": "e.g. Narra Street",
            }
        ),
    )

    class Meta:
        model = Household
        fields = ("block_number", "lot_number", "street_name")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._apply_bootstrap_classes()

    def clean_block_number(self):
        block = self.cleaned_data.get("block_number")
        if block is None or block <= 0:
            raise ValidationError(
                "Block number must be a positive integer greater than zero (BR-06)."
            )
        return block

    def clean_lot_number(self):
        lot = self.cleaned_data.get("lot_number")
        if lot is None or lot <= 0:
            raise ValidationError(
                "Lot number must be a positive integer greater than zero (BR-06)."
            )
        return lot

    def clean_street_name(self):
        street = " ".join(self.cleaned_data.get("street_name", "").strip().split())
        if not street:
            raise ValidationError("Street name is required.")
        return street

    def clean(self):
        cleaned_data = super().clean()
        block = cleaned_data.get("block_number")
        lot = cleaned_data.get("lot_number")
        street = cleaned_data.get("street_name")

        if block and lot and street:
            qs = Household.objects.filter(
                block_number=block,
                lot_number=lot,
                street_name__iexact=street,
            )
            if self.instance and self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise ValidationError(
                    "A household unit with this Block, Lot, and Street Name is already registered in the subdivision (BR-04)."
                )
        return cleaned_data
