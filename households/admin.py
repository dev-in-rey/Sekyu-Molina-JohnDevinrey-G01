from django.contrib import admin
from .models import Household


@admin.register(Household)
class HouseholdAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "block_number",
        "lot_number",
        "street_name",
        "user",
        "hoa_status",
        "created_at",
    ]
    list_filter = ["hoa_status", "street_name"]
    search_fields = ["street_name", "user__username", "user__email", "user__first_name", "user__last_name"]
    ordering = ["block_number", "lot_number", "street_name"]
