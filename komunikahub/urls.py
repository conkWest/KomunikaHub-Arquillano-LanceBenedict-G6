from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from accounts import views as acc_views
from dashboard import views as dash_views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', acc_views.login_view, name='home'),
    path('register/', acc_views.register_view, name='register'),
    path('login/', acc_views.login_view, name='login'),
    path('logout/', acc_views.logout_view, name='logout'),
    path('profile/', acc_views.profile_view, name='profile'),
    path('redirect/', dash_views.role_redirect_view, name='role_redirect'),
    path('dashboard/staff/', dash_views.staff_dashboard, name='staff_dashboard'),
    path('dashboard/resident/', dash_views.resident_dashboard, name='resident_dashboard'),
    path('tickets/', include('tickets.urls')),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
