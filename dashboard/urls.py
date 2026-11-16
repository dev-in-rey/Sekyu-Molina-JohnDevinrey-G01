from django.urls import path
from .views import (
    DashboardRedirectView,
    ResidentDashboardView,
    GuardDashboardView,
    AdminDashboardView,
    ManageResidentStatusView,
)

urlpatterns = [
    path("", DashboardRedirectView.as_view(), name="dashboard"),
    path("dashboard/resident/", ResidentDashboardView.as_view(), name="resident_dashboard"),
    path("dashboard/guard/", GuardDashboardView.as_view(), name="guard_dashboard"),
    path("dashboard/admin/", AdminDashboardView.as_view(), name="admin_dashboard"),
    path("admin-panel/", AdminDashboardView.as_view(), name="admin_panel"),
    path(
        "dashboard/admin/users/<int:pk>/manage/",
        ManageResidentStatusView.as_view(),
        name="manage_user_status",
    ),
]
