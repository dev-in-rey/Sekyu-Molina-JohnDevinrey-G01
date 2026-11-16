from django.urls import path
from .views import (
    CustomLoginView,
    CustomLogoutView,
    SignUpView,
    ProfileView,
    ProfileUpdateView,
)

urlpatterns = [
    path("login/", CustomLoginView.as_view(), name="login"),
    path("logout/", CustomLogoutView.as_view(), name="logout"),
    path("signup/", SignUpView.as_view(), name="signup"),
    path("profile/", ProfileView.as_view(), name="profile"),
    path("profile/edit/", ProfileUpdateView.as_view(), name="profile_edit"),
    path("profile/<int:pk>/", ProfileView.as_view(), name="profile_detail"),
    path("profile/<int:pk>/edit/", ProfileUpdateView.as_view(), name="profile_edit_pk"),
]
