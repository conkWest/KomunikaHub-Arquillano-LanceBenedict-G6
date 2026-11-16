from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden

@login_required
def role_redirect_view(request):
    if request.user.role == 'staff':
        return redirect('staff_dashboard')
    return redirect('resident_dashboard')

@login_required
def staff_dashboard(request):
    if request.user.role != 'staff':
        return HttpResponseForbidden("Access Denied: Barangay Staff only.")
    return render(request, 'dashboard/staff_dashboard.html')

@login_required
def resident_dashboard(request):
    if request.user.role != 'resident':
        return HttpResponseForbidden("Access Denied: Residents only.")
    return render(request, 'dashboard/resident_dashboard.html')