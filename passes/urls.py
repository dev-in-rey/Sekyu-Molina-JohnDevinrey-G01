from django.urls import path
from .views import (
    GateAccessLogListView,
    GuardPassValidateView,
    RecordGateExitView,
    VisitorPassCreateView,
    VisitorPassDeleteView,
    VisitorPassDetailView,
    VisitorPassListView,
    VisitorPassRevokeView,
    VisitorPassUpdateView,
)

urlpatterns = [
    path("", VisitorPassListView.as_view(), name="pass_list"),
    path("create/", VisitorPassCreateView.as_view(), name="pass_create"),
    path("<int:pk>/", VisitorPassDetailView.as_view(), name="pass_detail"),
    path("<int:pk>/edit/", VisitorPassUpdateView.as_view(), name="pass_edit"),
    path("<int:pk>/revoke/", VisitorPassRevokeView.as_view(), name="pass_revoke"),
    path("<int:pk>/delete/", VisitorPassDeleteView.as_view(), name="pass_delete"),
    path("validate/", GuardPassValidateView.as_view(), name="guard_pass_validate"),
    path("logs/", GateAccessLogListView.as_view(), name="gate_log_list"),
    path("logs/<int:pk>/exit/", RecordGateExitView.as_view(), name="record_gate_exit"),
]
