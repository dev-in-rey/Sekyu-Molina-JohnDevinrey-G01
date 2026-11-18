from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("accounts.urls")),
    path("accounts/", include("django.contrib.auth.urls")),
    path("households/", include("households.urls")),
    path("", include("dashboard.urls")),
]

if "passes" in settings.INSTALLED_APPS:  # pragma: no branch
    urlpatterns.insert(4, path("passes/", include("passes.urls")))

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
