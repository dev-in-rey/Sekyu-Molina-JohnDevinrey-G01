from django.contrib import admin
from .models import GateAccessLog, VisitorPass


@admin.register(VisitorPass)
class VisitorPassAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "visitor_name",
        "visitor_type",
        "access_pin",
        "household",
        "status",
        "is_multi_entry",
        "valid_from",
        "valid_until",
    ]
    list_filter = ["status", "visitor_type", "is_multi_entry"]
    search_fields = ["visitor_name", "visitor_phone", "access_pin", "qr_token", "household__street_name"]


@admin.register(GateAccessLog)
class GateAccessLogAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "visitor_name",
        "visitor_type",
        "household",
        "guard_user",
        "verification_status",
        "entry_timestamp",
        "exit_timestamp",
    ]
    list_filter = ["verification_status", "visitor_type", "sync_status"]
    search_fields = ["visitor_name", "remarks", "household__street_name", "guard_user__username"]
