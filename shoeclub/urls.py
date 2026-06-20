from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path


def health_check(request):
    return JsonResponse(
        {
            "status": "ok",
            "message": "Backend running successfully",
            "version": "1.0.0",
        }
    )


urlpatterns = [
    path("django-admin/", admin.site.urls),
    path("api/health/", health_check, name="health_check"),
    path("", include("store.urls")),
]

if settings.DEBUG:
    import debug_toolbar

    urlpatterns += [path("__debug__/", include(debug_toolbar.urls))]
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
