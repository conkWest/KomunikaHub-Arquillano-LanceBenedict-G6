from functools import wraps

from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden

from .services import is_resident, is_staff


def _role_required(check, message):
    def decorator(view):
        @wraps(view)
        @login_required
        def wrapper(request, *args, **kwargs):
            if not check(request.user):  # BR-09: 403 for the wrong role
                return HttpResponseForbidden(message)
            return view(request, *args, **kwargs)
        return wrapper
    return decorator


resident_required = _role_required(is_resident, "Access Denied: Residents only.")
staff_required = _role_required(is_staff, "Access Denied: Barangay Staff only.")
