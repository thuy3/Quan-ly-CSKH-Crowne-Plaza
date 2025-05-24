"""
URL configuration for hotel_management project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from accounts import views as account_views
from core import views as core_views
from accounts.views import change_password_view
from core.views import RoomDetailView

urlpatterns = [
    # path('admin/', admin.site.urls),

    # Authentication URLs
    path('login/', account_views.login_view, name='login'),
    path('logout/', account_views.logout_view, name='logout'),
    path('register/', account_views.register_view, name='register'),
    path('profile/', account_views.profile_view, name='profile'),
    path('profile/edit/', account_views.profile_edit_view, name='profile_edit'),
    path('change-password/', change_password_view, name='change_password'),

    # Core URLs
    path('', core_views.home, name='home'),
    path('rooms/', core_views.room_search, name='room_search'),
    path('rooms/<int:pk>/', RoomDetailView.as_view(), name='room_detail'),
    path('services/', core_views.service_list, name='service_list'),
    path('services/<int:pk>/', core_views.service_detail, name='service_detail'),
    path('requests/', core_views.customer_requests, name='customer_requests'),
    path('requests/<int:booking_pk>/', core_views.request_detail, name='request_detail'),
    path('requests/<int:pk>/delete/', core_views.delete_request, name='delete_request'),

    # Customer URLs
    path('my-bookings/', core_views.customer_bookings, name='customer_bookings'),
    path('bookings/<int:pk>/', core_views.booking_detail, name='booking_detail'),

    # Admin URLs
    path('admin-dashboard/', core_views.admin_dashboard, name='admin_dashboard'),
    path('admin-dashboard/rooms/', core_views.admin_room_management, name='admin_room_management'),
    path('admin/rooms/add/', core_views.add_room, name='add_room'),
    path('admin-dashboard/rooms/<int:pk>/edit/', core_views.edit_room, name='edit_room'),
    path('admin-dashboard/rooms/<int:pk>/delete/', core_views.delete_room, name='delete_room'),
    path('admin-dashboard/bookings/', core_views.admin_booking_management, name='admin_booking_management'),
    path('admin-dashboard/bookings/<int:pk>/', core_views.process_booking, name='process_booking'),
    path('admin-dashboard/customers/', core_views.admin_customer_management, name='admin_customer_management'),
    path('admin-dashboard/customers/<int:pk>/', core_views.customer_detail, name='customer_detail'),
    path('customers/<int:pk>/edit/', core_views.edit_customer, name='edit_customer'),
    path('customers/<int:pk>/delete/', core_views.delete_customer, name='delete_customer'),
    path('admin-dashboard/staff/', core_views.admin_staff_management, name='admin_staff_management'),
    path('admin-dashboard/staff/add/', core_views.add_staff, name='add_staff'),
    path('admin-dashboard/staff/<int:pk>/edit/', core_views.edit_staff, name='edit_staff'),
    path('admin-dashboard/staff/<int:pk>/delete/', core_views.delete_staff, name='delete_staff'),
    path('admin-dashboard/schedule/', core_views.admin_schedule_management, name='admin_schedule_management'),
    path('admin-dashboard/schedule/<int:pk>/delete/', core_views.delete_schedule, name='delete_schedule'),
    path('admin-dashboard/requests/', core_views.admin_request_management, name='admin_request_management'),
    path('admin-dashboard/requests/<int:pk>/', core_views.process_request, name='process_request'),
    path('admin-dashboard/services/', core_views.admin_service_management, name='admin_service_management'),
    path('admin/services/add/', core_views.add_service, name='add_service'),
    path('admin-dashboard/services/<int:pk>/edit/', core_views.edit_service, name='edit_service'),
    path('admin-dashboard/services/<int:pk>/delete/', core_views.delete_service, name='delete_service'),
    path('admin-dashboard/service-bookings/', core_views.admin_service_booking, name='admin_service_booking'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)