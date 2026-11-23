from django.urls import path

from . import views

urlpatterns = [
    # Resident
    path('', views.my_tickets, name='my_tickets'),
    path('new/', views.ticket_create, name='ticket_create'),
    path('<int:pk>/', views.ticket_detail, name='ticket_detail'),
    path('<int:pk>/edit/', views.ticket_edit, name='ticket_edit'),
    path('photos/<int:pk>/delete/', views.attachment_delete, name='attachment_delete'),
    # Staff
    path('dispatch/', views.dispatch_list, name='dispatch_list'),
    path('dispatch/<int:pk>/', views.manage_ticket, name='manage_ticket'),
    path('remarks/<int:pk>/delete/', views.remark_delete, name='remark_delete'),
]
