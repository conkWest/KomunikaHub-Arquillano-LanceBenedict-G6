from django.contrib.auth.decorators import login_required
from django.db.models import Count
from django.http import HttpResponseForbidden
from django.shortcuts import redirect, render

from tickets.models import IncidentTicket, TicketRemark


def _status_counts(qs):
    counts = {s.replace(' ', '_'): 0 for s, _ in IncidentTicket.STATUS_CHOICES}
    for row in qs.values('status').annotate(n=Count('id')):
        counts[row['status'].replace(' ', '_')] = row['n']
    return counts


@login_required
def role_redirect_view(request):
    if request.user.role == 'staff':
        return redirect('staff_dashboard')
    return redirect('resident_dashboard')


@login_required
def staff_dashboard(request):
    if request.user.role != 'staff':
        return HttpResponseForbidden("Access Denied: Barangay Staff only.")
    tickets = IncidentTicket.objects.all()
    counts = _status_counts(tickets)
    urgency = {u: 0 for u, _ in IncidentTicket.URGENCY_CHOICES}
    for row in tickets.exclude(status=IncidentTicket.RESOLVED).values('urgency').annotate(n=Count('id')):
        urgency[row['urgency']] = row['n']
    by_zone = (tickets.exclude(status=IncidentTicket.RESOLVED)
               .values('zone__code', 'zone__name').annotate(n=Count('id')).order_by('-n')[:6])
    needs_attention = (tickets.filter(status=IncidentTicket.PENDING)
                       .select_related('category', 'zone').order_by('-created_at')[:5])
    return render(request, 'dashboard/staff_dashboard.html', {
        'counts': counts, 'total': sum(counts.values()), 'urgency': urgency,
        'by_zone': by_zone, 'needs_attention': needs_attention,
    })


@login_required
def resident_dashboard(request):
    if request.user.role != 'resident':
        return HttpResponseForbidden("Access Denied: Residents only.")
    mine = IncidentTicket.objects.filter(reporter=request.user)
    counts = _status_counts(mine)
    recent = mine.select_related('category', 'zone')[:5]
    updates = (TicketRemark.objects.filter(ticket__reporter=request.user, visibility=TicketRemark.PUBLIC)
               .select_related('ticket').order_by('-created_at')[:3])
    return render(request, 'dashboard/resident_dashboard.html', {
        'counts': counts, 'total': sum(counts.values()), 'recent': recent, 'updates': updates,
    })
