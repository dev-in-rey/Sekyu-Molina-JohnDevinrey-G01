from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import CustomUser


@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    list_display = [
        "username",
        "email",
        "first_name",
        "last_name",
        "role",
        "is_approved",
        "is_active",
        "is_staff",
    ]
    list_filter = ["role", "is_approved", "is_active", "is_staff"]
    search_fields = ["username", "email", "first_name", "last_name", "phone_number"]

    fieldsets = UserAdmin.fieldsets + (
        (
            "Sekyu Community Security Profile",
            {"fields": ("role", "phone_number", "is_approved", "profile_photo")},
        ),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        (
            "Sekyu Community Security Profile",
            {"fields": ("email", "first_name", "last_name", "role", "phone_number", "is_approved")},
        ),
    )
