from django.db import models
from django.db.models import Q
from django.contrib.auth.models import AbstractUser


class CustomUser(AbstractUser):
    class Role(models.TextChoices):
        RESIDENT = "RESIDENT", "Subdivision Resident"
        GUARD = "GUARD", "Security Guard"
        ADMIN = "ADMIN", "HOA Administrator"

    email = models.EmailField(
        max_length=100,
        unique=True,
        help_text="Required. A valid and unique email address for your account.",
    )
    role = models.CharField(
        max_length=15,
        choices=Role.choices,
        default=Role.RESIDENT,
    )
    phone_number = models.CharField(
        max_length=20,
        blank=True,
        help_text="Contact mobile number for SMS notifications and gate security dispatch.",
    )
    is_approved = models.BooleanField(
        default=False,
        help_text="Designates whether the resident's household profile has been verified by an HOA Administrator.",
    )
    profile_photo = models.ImageField(
        upload_to="profiles/",
        blank=True,
        null=True,
        help_text="Optional profile photograph.",
    )

    class Meta:
        db_table = "users"
        constraints = [
            models.CheckConstraint(
                condition=Q(role__in=["RESIDENT", "GUARD", "ADMIN"]),
                name="users_role_valid_check",
            ),
        ]

    @property
    def full_name(self):
        name = f"{self.first_name} {self.last_name}".strip()
        return name or self.username

    def save(self, *args, **kwargs):
        if self.email:
            self.email = self.email.strip().lower()
        if self.role in (self.Role.ADMIN, self.Role.GUARD) or self.is_superuser:
            self.is_approved = True
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.username} ({self.get_role_display()})"
