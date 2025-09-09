from functools import wraps
from django.shortcuts import redirect
from django.urls import reverse
from django.http import HttpResponseForbidden
from django.utils import timezone
from datetime import date
from django.db.models import Sum

from models import login


def admin_required(view_func):
    """Decorator that checks the session for an admin user_id and confirms usertype=='admin'.
    Redirects to a login page (you must implement) if missing.
    """
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        admin_id = request.session.get('lid')
        if not admin_id:
            return redirect(reverse('admin_login'))
        try:
            user = login.objects.get(username=admin_id) if isinstance(admin_id, str) else login.objects.get(pk=admin_id)
        except login.DoesNotExist:
            return redirect(reverse('admin_login'))
        # additional guard
        if user.usertype != 'admin':
            return HttpResponseForbidden('Admin access required')
        request.admin_user = user
        return view_func(request, *args, **kwargs)
    return _wrapped


def month_start_end(dt=None):
    from datetime import date
    if dt is None:
        dt = timezone.now().date()
    start = dt.replace(day=1)
    # compute month end simply
    import calendar
    last = calendar.monthrange(dt.year, dt.month)[1]
    end = dt.replace(day=last)
    return start, end