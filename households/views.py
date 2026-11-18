from django.contrib import messages
from django.contrib.messages.views import SuccessMessageMixin
from django.core.exceptions import PermissionDenied
from django.db.models.deletion import ProtectedError
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import CreateView, DeleteView, ListView, UpdateView

from accounts.models import CustomUser
from dashboard.views import RoleRequiredMixin
from .forms import HouseholdForm
from .models import Household


class HouseholdListView(RoleRequiredMixin, ListView):
    model = Household
    template_name = "households/household_list.html"
    context_object_name = "households"
    required_role = CustomUser.Role.RESIDENT

    def get_queryset(self):
        return Household.objects.filter(user=self.request.user).order_by(
            "block_number", "lot_number", "street_name"
        )


class HouseholdCreateView(RoleRequiredMixin, SuccessMessageMixin, CreateView):
    model = Household
    form_class = HouseholdForm
    template_name = "households/household_form.html"
    success_url = reverse_lazy("household_list")
    success_message = "Household unit registered successfully!"
    required_role = CustomUser.Role.RESIDENT

    def form_valid(self, form):
        form.instance.user = self.request.user
        return super().form_valid(form)

    def form_invalid(self, form):
        messages.error(
            self.request,
            "Please correct the highlighted errors before saving your household unit.",
        )
        return super().form_invalid(form)


class HouseholdUpdateView(RoleRequiredMixin, SuccessMessageMixin, UpdateView):
    model = Household
    form_class = HouseholdForm
    template_name = "households/household_form.html"
    success_url = reverse_lazy("household_list")
    success_message = "Household unit updated successfully!"
    required_role = CustomUser.Role.RESIDENT

    def get_object(self, queryset=None):
        household = get_object_or_404(Household, pk=self.kwargs["pk"])
        if household.user_id != self.request.user.id:
            raise PermissionDenied("You can only modify your own household records.")
        return household

    def form_invalid(self, form):
        messages.error(
            self.request,
            "Please correct the highlighted errors before updating your household unit.",
        )
        return super().form_invalid(form)


class HouseholdDeleteView(RoleRequiredMixin, DeleteView):
    model = Household
    template_name = "households/household_confirm_delete.html"
    context_object_name = "household"
    success_url = reverse_lazy("household_list")
    required_role = CustomUser.Role.RESIDENT

    def get_object(self, queryset=None):
        household = get_object_or_404(Household, pk=self.kwargs["pk"])
        if household.user_id != self.request.user.id:
            raise PermissionDenied("You can only delete your own household records.")
        return household

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        unit_label = self.object.unit_label
        try:
            self.object.delete()
            messages.success(
                request,
                f"Household unit '{unit_label}' has been removed from your profile.",
            )
        except ProtectedError:
            messages.error(
                request,
                f"Cannot delete '{unit_label}' because visitor passes or gate access logs are linked to this unit (BR-05 / BR-19).",
            )
        return redirect(self.success_url)


class AdminHouseholdListView(RoleRequiredMixin, ListView):
    model = Household
    template_name = "households/admin_household_list.html"
    context_object_name = "households"
    required_role = CustomUser.Role.ADMIN

    def get_queryset(self):
        return Household.objects.select_related("user").order_by(
            "block_number", "lot_number", "street_name"
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        qs = context["households"]
        context["total_households"] = qs.count()
        context["good_standing_count"] = qs.filter(
            hoa_status=Household.HoaStatus.GOOD_STANDING
        ).count()
        context["delinquent_count"] = qs.filter(
            hoa_status=Household.HoaStatus.DELINQUENT
        ).count()
        context["inactive_count"] = qs.filter(
            hoa_status=Household.HoaStatus.INACTIVE
        ).count()
        context["hoa_status_choices"] = Household.HoaStatus.choices
        return context


class ManageHouseholdStatusView(RoleRequiredMixin, View):
    required_role = CustomUser.Role.ADMIN

    def post(self, request, pk, *args, **kwargs):
        household = get_object_or_404(Household, pk=pk)
        new_status = request.POST.get("hoa_status", "").strip()
        valid_statuses = {choice[0] for choice in Household.HoaStatus.choices}
        if new_status not in valid_statuses:
            messages.error(request, "Invalid HOA standing status selected.")
            return redirect("admin_household_list")

        household.hoa_status = new_status
        household.save(update_fields=["hoa_status"])
        messages.success(
            request,
            f"HOA standing for '{household.unit_label}' updated to {household.get_hoa_status_display()}.",
        )
        return redirect("admin_household_list")
