from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Q
from django.db.models.deletion import ProtectedError
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from accounts.models import CustomUser
from dashboard.views import RoleRequiredMixin
from households.models import Household
from .forms import GuardPinValidationForm, VisitorPassForm
from .models import GateAccessLog, VisitorPass


class VisitorPassListView(RoleRequiredMixin, ListView):
    model = VisitorPass
    template_name = "passes/pass_list.html"
    context_object_name = "passes"
    required_role = CustomUser.Role.RESIDENT

    def get_queryset(self):
        qs = VisitorPass.objects.select_related("household").filter(
            household__user=self.request.user
        )
        now = timezone.now()
        for pass_obj in qs:
            pass_obj.refresh_expiration(now=now)
        status_filter = self.request.GET.get("status", "").strip().upper()
        valid_statuses = {choice[0] for choice in VisitorPass.Status.choices}
        if status_filter in valid_statuses:
            qs = qs.filter(status=status_filter)
        return qs.order_by("-created_at")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user_households = Household.objects.filter(user=self.request.user)
        context["user_households_count"] = user_households.count()
        context["can_generate_pass"] = bool(
            self.request.user.is_approved
            and user_households.filter(
                hoa_status=Household.HoaStatus.GOOD_STANDING
            ).exists()
        )
        context["selected_status"] = self.request.GET.get("status", "ALL").strip().upper()
        context["status_choices"] = VisitorPass.Status.choices
        return context


class VisitorPassCreateView(RoleRequiredMixin, CreateView):
    model = VisitorPass
    form_class = VisitorPassForm
    template_name = "passes/pass_form.html"
    required_role = CustomUser.Role.RESIDENT

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["has_households"] = Household.objects.filter(
            user=self.request.user
        ).exists()
        return context

    def form_valid(self, form):
        now = timezone.now()
        if form.instance.valid_from > now:
            form.instance.status = VisitorPass.Status.PENDING
        else:
            form.instance.status = VisitorPass.Status.ACTIVE
        response = super().form_valid(form)
        messages.success(
            self.request,
            f"Digital visitor pass created for {self.object.visitor_name}! 4-Digit Gate PIN: {self.object.access_pin}",
        )
        return response

    def form_invalid(self, form):
        messages.error(
            self.request,
            "Unable to generate visitor pass. Please review the validation errors below.",
        )
        return super().form_invalid(form)

    def get_success_url(self):
        return reverse("pass_detail", kwargs={"pk": self.object.pk})


class VisitorPassDetailView(RoleRequiredMixin, DetailView):
    model = VisitorPass
    template_name = "passes/pass_detail.html"
    context_object_name = "visitor_pass"
    required_role = CustomUser.Role.RESIDENT

    def get_object(self, queryset=None):
        visitor_pass = get_object_or_404(
            VisitorPass.objects.select_related("household", "household__user"),
            pk=self.kwargs["pk"],
        )
        if visitor_pass.household.user_id != self.request.user.id:
            raise PermissionDenied("You can only view visitor passes issued by your own household.")
        visitor_pass.refresh_expiration()
        return visitor_pass

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["gate_logs"] = self.object.gate_logs.select_related(
            "guard_user"
        ).order_by("-entry_timestamp")
        return context


class VisitorPassUpdateView(RoleRequiredMixin, SuccessMessageMixin, UpdateView):
    model = VisitorPass
    form_class = VisitorPassForm
    template_name = "passes/pass_form.html"
    success_message = "Visitor pass details updated successfully!"
    required_role = CustomUser.Role.RESIDENT

    def get_object(self, queryset=None):
        visitor_pass = get_object_or_404(
            VisitorPass.objects.select_related("household"),
            pk=self.kwargs["pk"],
        )
        if visitor_pass.household.user_id != self.request.user.id:
            raise PermissionDenied("You can only modify your own visitor passes.")
        visitor_pass.refresh_expiration()
        return visitor_pass

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and request.user.role == CustomUser.Role.RESIDENT:
            obj = self.get_object()
            if obj.status not in (VisitorPass.Status.PENDING, VisitorPass.Status.ACTIVE):
                messages.warning(
                    request,
                    f"Pass #{obj.pk} is already {obj.get_status_display()} and can no longer be edited.",
                )
                return redirect("pass_detail", pk=obj.pk)
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["has_households"] = True
        return context

    def form_valid(self, form):
        now = timezone.now()
        if form.instance.valid_from > now:
            form.instance.status = VisitorPass.Status.PENDING
        else:
            form.instance.status = VisitorPass.Status.ACTIVE
        return super().form_valid(form)

    def form_invalid(self, form):
        messages.error(
            self.request,
            "Please correct the highlighted errors before saving changes to this visitor pass.",
        )
        return super().form_invalid(form)

    def get_success_url(self):
        return reverse("pass_detail", kwargs={"pk": self.object.pk})


class VisitorPassRevokeView(RoleRequiredMixin, View):
    required_role = CustomUser.Role.RESIDENT

    def post(self, request, pk, *args, **kwargs):
        visitor_pass = get_object_or_404(
            VisitorPass.objects.select_related("household"),
            pk=pk,
        )
        if visitor_pass.household.user_id != request.user.id:
            raise PermissionDenied("You can only revoke your own visitor passes.")
        visitor_pass.refresh_expiration()
        if visitor_pass.status in (VisitorPass.Status.PENDING, VisitorPass.Status.ACTIVE):
            visitor_pass.status = VisitorPass.Status.REVOKED
            visitor_pass.save(update_fields=["status"])
            messages.success(
                request,
                f"Visitor pass for '{visitor_pass.visitor_name}' (PIN {visitor_pass.access_pin}) has been revoked.",
            )
        else:
            messages.warning(
                request,
                f"Visitor pass cannot be revoked because its status is already {visitor_pass.get_status_display()}.",
            )
        return redirect("pass_detail", pk=visitor_pass.pk)


class VisitorPassDeleteView(RoleRequiredMixin, DeleteView):
    model = VisitorPass
    template_name = "passes/pass_confirm_delete.html"
    context_object_name = "visitor_pass"
    success_url = reverse_lazy("pass_list")
    required_role = CustomUser.Role.RESIDENT

    def get_object(self, queryset=None):
        visitor_pass = get_object_or_404(
            VisitorPass.objects.select_related("household"),
            pk=self.kwargs["pk"],
        )
        if visitor_pass.household.user_id != self.request.user.id:
            raise PermissionDenied("You can only delete your own visitor passes.")
        return visitor_pass

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        visitor_name = self.object.visitor_name
        pin = self.object.access_pin
        try:
            self.object.delete()
            messages.success(
                request,
                f"Visitor pass for '{visitor_name}' (PIN {pin}) has been deleted.",
            )
            return redirect(self.success_url)
        except ProtectedError:
            messages.error(
                request,
                "Cannot delete this visitor pass because gate access logs already reference it; historical security audits must be preserved (BR-19).",
            )
            return redirect("pass_detail", pk=self.object.pk)


class GuardPassValidateView(RoleRequiredMixin, View):
    template_name = "passes/guard_validate.html"
    required_role = CustomUser.Role.GUARD

    def _get_context(self, form=None, validation_result=None):
        return {
            "form": form or GuardPinValidationForm(),
            "validation_result": validation_result,
            "recent_logs": GateAccessLog.objects.select_related(
                "household", "visitor_pass", "guard_user"
            ).order_by("-entry_timestamp")[:8],
            "active_passes_count": VisitorPass.objects.filter(
                status__in=[VisitorPass.Status.ACTIVE, VisitorPass.Status.PENDING],
                valid_until__gt=timezone.now(),
            ).count(),
        }

    def get(self, request, *args, **kwargs):
        return render(request, self.template_name, self._get_context())

    def post(self, request, *args, **kwargs):
        form = GuardPinValidationForm(request.POST)
        if not form.is_valid():
            messages.error(
                request,
                "Invalid PIN format. Please enter an exact 4-digit numeric PIN (BR-10).",
            )
            return render(request, self.template_name, self._get_context(form=form))

        pin = form.cleaned_data["access_pin"]
        remarks = (form.cleaned_data.get("remarks") or "").strip()

        candidates = list(
            VisitorPass.objects.select_related("household", "household__user")
            .filter(access_pin=pin)
            .order_by("-created_at")
        )
        if not candidates:
            messages.error(
                request,
                f"Gate Clearance DENIED: No visitor pass found matching 4-digit PIN '{pin}'.",
            )
            return render(
                request,
                self.template_name,
                self._get_context(
                    form=GuardPinValidationForm(),
                    validation_result={
                        "outcome": "NOT_FOUND",
                        "pin": pin,
                        "reason": "No issued visitor pass matches this 4-digit security PIN.",
                    },
                ),
            )

        visitor_pass = next(
            (
                p
                for p in candidates
                if p.status in (VisitorPass.Status.ACTIVE, VisitorPass.Status.PENDING)
            ),
            candidates[0],
        )

        now = timezone.now()
        with transaction.atomic():
            if now >= visitor_pass.valid_until or visitor_pass.status == VisitorPass.Status.EXPIRED:
                if visitor_pass.status != VisitorPass.Status.EXPIRED:
                    visitor_pass.status = VisitorPass.Status.EXPIRED
                    visitor_pass.save(update_fields=["status"])
                reason = "Visitor pass has expired past its Valid Until window (BR-14)."
                log = GateAccessLog.objects.create(
                    guard_user=request.user,
                    visitor_pass=visitor_pass,
                    household=visitor_pass.household,
                    visitor_name=visitor_pass.visitor_name,
                    visitor_type=visitor_pass.visitor_type,
                    entry_timestamp=now,
                    verification_status=GateAccessLog.VerificationStatus.DENIED,
                    remarks=remarks or reason,
                )
                messages.error(
                    request,
                    f"Gate Clearance DENIED for {visitor_pass.visitor_name}: {reason}",
                )
            elif visitor_pass.status in (VisitorPass.Status.USED, VisitorPass.Status.REVOKED):
                reason = f"Visitor pass status is already {visitor_pass.get_status_display()} (BR-12 / BR-15)."
                log = GateAccessLog.objects.create(
                    guard_user=request.user,
                    visitor_pass=visitor_pass,
                    household=visitor_pass.household,
                    visitor_name=visitor_pass.visitor_name,
                    visitor_type=visitor_pass.visitor_type,
                    entry_timestamp=now,
                    verification_status=GateAccessLog.VerificationStatus.DENIED,
                    remarks=remarks or reason,
                )
                messages.error(
                    request,
                    f"Gate Clearance DENIED for {visitor_pass.visitor_name}: {reason}",
                )
            elif not visitor_pass.household.is_verified_for_passes:
                reason = "Destination household unit is not HOA-verified or not in Good Standing (BR-13)."
                log = GateAccessLog.objects.create(
                    guard_user=request.user,
                    visitor_pass=visitor_pass,
                    household=visitor_pass.household,
                    visitor_name=visitor_pass.visitor_name,
                    visitor_type=visitor_pass.visitor_type,
                    entry_timestamp=now,
                    verification_status=GateAccessLog.VerificationStatus.DENIED,
                    remarks=remarks or reason,
                )
                messages.error(
                    request,
                    f"Gate Clearance DENIED for {visitor_pass.visitor_name}: {reason}",
                )
            elif now < visitor_pass.valid_from:
                reason = "Visitor pass validity window has not started yet (BR-09)."
                log = GateAccessLog.objects.create(
                    guard_user=request.user,
                    visitor_pass=visitor_pass,
                    household=visitor_pass.household,
                    visitor_name=visitor_pass.visitor_name,
                    visitor_type=visitor_pass.visitor_type,
                    entry_timestamp=now,
                    verification_status=GateAccessLog.VerificationStatus.DENIED,
                    remarks=remarks or reason,
                )
                messages.error(
                    request,
                    f"Gate Clearance DENIED for {visitor_pass.visitor_name}: {reason}",
                )
            else:
                if visitor_pass.is_multi_entry:
                    visitor_pass.status = VisitorPass.Status.ACTIVE
                else:
                    visitor_pass.status = VisitorPass.Status.USED
                visitor_pass.save(update_fields=["status"])
                reason = "4-digit PIN verified at guardhouse checkpoint."
                log = GateAccessLog.objects.create(
                    guard_user=request.user,
                    visitor_pass=visitor_pass,
                    household=visitor_pass.household,
                    visitor_name=visitor_pass.visitor_name,
                    visitor_type=visitor_pass.visitor_type,
                    entry_timestamp=now,
                    verification_status=GateAccessLog.VerificationStatus.GRANTED,
                    remarks=remarks or reason,
                )
                messages.success(
                    request,
                    f"Gate Clearance GRANTED for {visitor_pass.visitor_name} visiting {visitor_pass.household.unit_label}!",
                )

        return render(
            request,
            self.template_name,
            self._get_context(
                form=GuardPinValidationForm(),
                validation_result={
                    "outcome": log.verification_status,
                    "pin": pin,
                    "visitor_pass": visitor_pass,
                    "log": log,
                    "reason": reason,
                },
            ),
        )


class GateAccessLogListView(LoginRequiredMixin, UserPassesTestMixin, ListView):
    model = GateAccessLog
    template_name = "passes/gate_logs.html"
    context_object_name = "gate_logs"

    def test_func(self):
        return bool(
            self.request.user.is_authenticated
            and self.request.user.role in (CustomUser.Role.GUARD, CustomUser.Role.ADMIN)
        )

    def get_queryset(self):
        qs = GateAccessLog.objects.select_related(
            "household", "household__user", "guard_user", "visitor_pass"
        )
        status_filter = self.request.GET.get("status", "").strip().upper()
        valid_statuses = {
            choice[0] for choice in GateAccessLog.VerificationStatus.choices
        }
        if status_filter in valid_statuses:
            qs = qs.filter(verification_status=status_filter)

        search_q = self.request.GET.get("q", "").strip()
        if search_q:
            qs = qs.filter(
                Q(visitor_name__icontains=search_q)
                | Q(household__street_name__icontains=search_q)
                | Q(guard_user__username__icontains=search_q)
                | Q(visitor_pass__access_pin__icontains=search_q)
            )
        return qs.order_by("-entry_timestamp")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        all_logs = GateAccessLog.objects.all()
        context["total_logs_count"] = all_logs.count()
        context["granted_count"] = all_logs.filter(
            verification_status=GateAccessLog.VerificationStatus.GRANTED
        ).count()
        context["denied_count"] = all_logs.filter(
            verification_status=GateAccessLog.VerificationStatus.DENIED
        ).count()
        context["inside_count"] = all_logs.filter(
            verification_status=GateAccessLog.VerificationStatus.GRANTED,
            exit_timestamp__isnull=True,
        ).count()
        context["selected_status"] = self.request.GET.get("status", "ALL").strip().upper()
        context["search_query"] = self.request.GET.get("q", "").strip()
        context["verification_choices"] = GateAccessLog.VerificationStatus.choices
        return context


class RecordGateExitView(RoleRequiredMixin, View):
    required_role = CustomUser.Role.GUARD

    def post(self, request, pk, *args, **kwargs):
        log = get_object_or_404(GateAccessLog, pk=pk)
        if log.verification_status != GateAccessLog.VerificationStatus.GRANTED:
            messages.warning(
                request,
                "Exit timestamps can only be recorded for granted gate entries.",
            )
        elif log.exit_timestamp is not None:
            messages.info(
                request,
                f"Departure for '{log.visitor_name}' was already recorded.",
            )
        else:
            now = timezone.now()
            log.exit_timestamp = now if now >= log.entry_timestamp else log.entry_timestamp
            log.save(update_fields=["exit_timestamp"])
            messages.success(
                request,
                f"Exit timestamp recorded for '{log.visitor_name}' (Log #{log.id}).",
            )
        return redirect("gate_log_list")
