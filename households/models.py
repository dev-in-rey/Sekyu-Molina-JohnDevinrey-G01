from django.conf import settings
from django.db import models
from django.db.models import Q


class Household(models.Model):
    class HoaStatus(models.TextChoices):
        GOOD_STANDING = "GOOD_STANDING", "Good Standing"
        DELINQUENT = "DELINQUENT", "Delinquent"
        INACTIVE = "INACTIVE", "Inactive"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        db_column="user_id",
        related_name="households",
        help_text="Primary resident user who heads the property.",
    )
    block_number = models.PositiveIntegerField(
        help_text="Subdivision block number designation of the physical residence.",
    )
    lot_number = models.PositiveIntegerField(
        help_text="Subdivision lot number designation of the physical residence.",
    )
    street_name = models.CharField(
        max_length=100,
        help_text="Designated street or avenue name where the residence is situated.",
    )
    hoa_status = models.CharField(
        max_length=20,
        choices=HoaStatus.choices,
        default=HoaStatus.GOOD_STANDING,
        help_text="Status of the property with the community Homeowners Association.",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="Timestamp recording when the household profile was registered.",
    )

    class Meta:
        db_table = "households"
        ordering = ["block_number", "lot_number", "street_name"]
        constraints = [
            models.UniqueConstraint(
                fields=("block_number", "lot_number", "street_name"),
                name="households_block_lot_street_uniq",
            ),
            models.CheckConstraint(
                condition=Q(block_number__gt=0) & Q(lot_number__gt=0),
                name="households_positive_block_lot_check",
            ),
            models.CheckConstraint(
                condition=Q(hoa_status__in=["GOOD_STANDING", "DELINQUENT", "INACTIVE"]),
                name="households_hoa_status_valid_check",
            ),
        ]

    @property
    def unit_label(self):
        return f"Block {self.block_number}, Lot {self.lot_number}, {self.street_name}"

    @property
    def is_verified_for_passes(self):
        return bool(
            self.user.is_active
            and self.user.is_approved
            and self.hoa_status == self.HoaStatus.GOOD_STANDING
        )

    def save(self, *args, **kwargs):
        if self.street_name:
            self.street_name = " ".join(self.street_name.strip().split())
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.unit_label} ({self.user.username})"
