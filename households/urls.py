from django.urls import path
from .views import (
    AdminHouseholdListView,
    HouseholdCreateView,
    HouseholdDeleteView,
    HouseholdListView,
    HouseholdUpdateView,
    ManageHouseholdStatusView,
)

urlpatterns = [
    path("", HouseholdListView.as_view(), name="household_list"),
    path("create/", HouseholdCreateView.as_view(), name="household_create"),
    path("<int:pk>/edit/", HouseholdUpdateView.as_view(), name="household_edit"),
    path("<int:pk>/delete/", HouseholdDeleteView.as_view(), name="household_delete"),
    path("manage/", AdminHouseholdListView.as_view(), name="admin_household_list"),
    path(
        "<int:pk>/status/",
        ManageHouseholdStatusView.as_view(),
        name="manage_household_status",
    ),
]
