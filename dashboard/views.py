from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone
from django.views import View
from django.views.generic import RedirectView, TemplateView

from accounts.models import CustomUser
from households.models import Household
from passes.models import GateAccessLog, VisitorPass


class RoleRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    """
    Restricts a view to users authenticated with a specific CustomUser.Role.
    Logged-out users are redirected to the login page.
    Logged-in users with a different role receive HTTP 403 Forbidden.
    """

    required_role = None

    def test_func(self):
        user = self.request.user
        return bool(
            user.is_authenticated and self.required_role and user.role == self.required_role
        )


class DashboardRedirectView(LoginRequiredMixin, RedirectView):
    """
    Routes each logged-in user directly to the dashboard matching their role.
    """

    permanent = False

    def get_redirect_url(self, *args, **kwargs):
        user = self.request.user
        if user.role == CustomUser.Role.ADMIN:
            return reverse("admin_dashboard")
        if user.role == CustomUser.Role.GUARD:
            return reverse("guard_dashboard")
        return reverse("resident_dashboard")


class ResidentDashboardView(RoleRequiredMixin, TemplateView):
    template_name = "dashboard/resident_dashboard.html"
    required_role = CustomUser.Role.RESIDENT

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["resident_count"] = CustomUser.objects.filter(
            role=CustomUser.Role.RESIDENT, is_active=True
        ).count()
        context["guard_count"] = CustomUser.objects.filter(
            role=CustomUser.Role.GUARD, is_active=True
        ).count()
        my_households = Household.objects.filter(user=self.request.user)
        context["my_households"] = my_households
        context["my_household_count"] = my_households.count()
        my_passes = VisitorPass.objects.select_related("household").filter(
            household__user=self.request.user
        )
        now = timezone.now()
        for pass_obj in my_passes:
            pass_obj.refresh_expiration(now=now)
        context["recent_passes"] = my_passes.order_by("-created_at")[:5]
        context["active_pass_count"] = my_passes.filter(
            status__in=[VisitorPass.Status.ACTIVE, VisitorPass.Status.PENDING]
        ).count()
        return context


class GuardDashboardView(RoleRequiredMixin, TemplateView):
    template_name = "dashboard/guard_dashboard.html"
    required_role = CustomUser.Role.GUARD

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["verified_residents"] = CustomUser.objects.filter(
            role=CustomUser.Role.RESIDENT,
            is_approved=True,
            is_active=True,
        ).order_by("last_name", "first_name")
        context["approved_resident_count"] = context["verified_residents"].count()
        context["pending_resident_count"] = CustomUser.objects.filter(
            role=CustomUser.Role.RESIDENT,
            is_approved=False,
        ).count()
        context["active_passes_count"] = VisitorPass.objects.filter(
            status__in=[VisitorPass.Status.ACTIVE, VisitorPass.Status.PENDING],
            valid_until__gt=timezone.now(),
        ).count()
        context["recent_gate_logs"] = GateAccessLog.objects.select_related(
            "household", "visitor_pass", "guard_user"
        ).order_by("-entry_timestamp")[:5]
        return context


class AdminDashboardView(RoleRequiredMixin, TemplateView):
    template_name = "dashboard/admin_dashboard.html"
    required_role = CustomUser.Role.ADMIN

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        users_qs = CustomUser.objects.all().order_by("-date_joined")
        context["all_users"] = users_qs
        context["total_users"] = users_qs.count()
        context["pending_residents"] = users_qs.filter(
            role=CustomUser.Role.RESIDENT, is_approved=False
        )
        context["pending_count"] = context["pending_residents"].count()
        context["approved_residents_count"] = users_qs.filter(
            role=CustomUser.Role.RESIDENT, is_approved=True
        ).count()
        context["guard_count"] = users_qs.filter(role=CustomUser.Role.GUARD).count()
        context["admin_count"] = users_qs.filter(role=CustomUser.Role.ADMIN).count()
        context["role_choices"] = CustomUser.Role.choices
        context["household_count"] = Household.objects.count()
        context["gate_log_count"] = GateAccessLog.objects.count()
        context["recent_gate_logs"] = GateAccessLog.objects.select_related(
            "household", "visitor_pass", "guard_user"
        ).order_by("-entry_timestamp")[:5]
        return context


class ManageResidentStatusView(RoleRequiredMixin, View):
    """
    Allows an HOA Administrator to approve/unapprove a resident, toggle active status,
    or assign user roles (RESIDENT, GUARD, ADMIN).
    """

    required_role = CustomUser.Role.ADMIN

    def post(self, request, pk, *args, **kwargs):
        target_user = get_object_or_404(CustomUser, pk=pk)
        action = request.POST.get("action", "").strip()

        if action == "approve":
            target_user.is_approved = True
            target_user.save(update_fields=["is_approved"])
            messages.success(
                request,
                f"Resident account '{target_user.username}' has been verified and approved.",
            )
        elif action == "revoke_approval":
            if target_user.pk == request.user.pk:
                messages.warning(request, "You cannot revoke approval on your own admin account.")
            else:
                target_user.is_approved = False
                target_user.save(update_fields=["is_approved"])
                messages.info(
                    request,
                    f"Approval for '{target_user.username}' has been set to pending.",
                )
        elif action == "toggle_active":
            if target_user.pk == request.user.pk:
                messages.error(request, "You cannot deactivate your own currently logged-in account.")
            else:
                target_user.is_active = not target_user.is_active
                target_user.save(update_fields=["is_active"])
                state = "activated" if target_user.is_active else "deactivated"
                messages.success(request, f"Account '{target_user.username}' has been {state}.")
        elif action == "change_role":
            new_role = request.POST.get("role", "").strip()
            valid_roles = {choice[0] for choice in CustomUser.Role.choices}
            if target_user.pk == request.user.pk and new_role != CustomUser.Role.ADMIN:
                messages.error(request, "You cannot demote your own administrator role.")
            elif new_role in valid_roles:
                target_user.role = new_role
                if new_role in (CustomUser.Role.GUARD, CustomUser.Role.ADMIN):
                    target_user.is_approved = True
                target_user.save()
                messages.success(
                    request,
                    f"Updated role for '{target_user.username}' to {target_user.get_role_display()}.",
                )
            else:
                messages.error(request, "Invalid role selection.")
        else:
            raise PermissionDenied("Unsupported administrative action.")

        return redirect("admin_dashboard")
