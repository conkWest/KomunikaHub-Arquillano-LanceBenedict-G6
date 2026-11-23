from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from . import services
from .forms import (AdvanceStatusForm, AssignTeamForm, RemarkForm, TicketFilterForm, TicketForm,
                    UrgencyForm)
from .models import IncidentTicket, TicketAttachment, TicketRemark
from .permissions import resident_required, staff_required


def _errors(request, exc):
    for msg in getattr(exc, 'messages', [str(exc)]):
        messages.error(request, msg)


def _post_args(request):
    """Bind the form only on POST, even if the POST body is empty."""
    if request.method == 'POST':
        return request.POST, request.FILES
    return None, None


def _filter(qs, form):
    if form.is_valid():
        d = form.cleaned_data
        if d.get('q'):
            qs = qs.filter(Q(ticket_no__icontains=d['q']) | Q(title__icontains=d['q']))
        for field in ('status', 'urgency', 'zone', 'category'):
            if d.get(field):
                qs = qs.filter(**{field: d[field]})
    return qs


# ---------------------------------------------------------------- resident
@resident_required
def my_tickets(request):  # Read (list) - BR-24: own tickets only
    filter_form = TicketFilterForm(request.GET or None)
    qs = IncidentTicket.objects.filter(reporter=request.user).select_related('category', 'zone')
    qs = _filter(qs, filter_form)
    page = Paginator(qs, 10).get_page(request.GET.get('page'))
    return render(request, 'tickets/my_tickets.html', {
        'page': page, 'filter_form': filter_form,
        'open_count': services.open_ticket_count(request.user),
    })


@resident_required
def ticket_create(request):  # Create
    form = TicketForm(*_post_args(request))
    if request.method == 'POST':
        if form.is_valid():
            try:
                ticket = services.create_ticket(request.user, form, form.cleaned_data['photos'])
            except ValidationError as exc:
                _errors(request, exc)
            else:
                messages.success(request, f"Ticket {ticket.ticket_no} was submitted. "
                                          "Barangay staff will review it shortly.")
                return redirect('ticket_detail', pk=ticket.pk)
        else:
            messages.error(request, "Please correct the errors below.")
    return render(request, 'tickets/ticket_form.html', {'form': form, 'mode': 'create'})


@resident_required
def ticket_detail(request, pk):  # Read (detail) - BR-24, BR-33
    ticket = get_object_or_404(
        IncidentTicket.objects.select_related('category', 'zone'), pk=pk, reporter=request.user)
    return render(request, 'tickets/ticket_detail.html', {
        'ticket': ticket,
        'logs': ticket.status_logs.select_related('changed_by'),
        'remarks': ticket.remarks.filter(visibility=TicketRemark.PUBLIC).select_related('author'),
        'assignment': ticket.active_assignment,
        'attachments': ticket.attachments.all(),
    })


@resident_required
def ticket_edit(request, pk):  # Update - BR-25
    ticket = get_object_or_404(IncidentTicket, pk=pk, reporter=request.user)
    if not ticket.resident_can_edit:
        messages.error(request, "This ticket can no longer be edited because it is already being handled.")
        return redirect('ticket_detail', pk=ticket.pk)
    form = TicketForm(*_post_args(request), instance=ticket)
    if request.method == 'POST':
        if form.is_valid():
            try:
                services.update_ticket(ticket, request.user, form, form.cleaned_data['photos'])
            except ValidationError as exc:
                _errors(request, exc)
            else:
                messages.success(request, "Ticket updated successfully.")
                return redirect('ticket_detail', pk=ticket.pk)
        else:
            messages.error(request, "Please correct the errors below.")
    return render(request, 'tickets/ticket_form.html', {
        'form': form, 'mode': 'edit', 'ticket': ticket, 'attachments': ticket.attachments.all()})


@resident_required
@require_POST
def attachment_delete(request, pk):  # Delete (photo) - BR-25
    attachment = get_object_or_404(TicketAttachment, pk=pk, ticket__reporter=request.user)
    ticket_pk = attachment.ticket_id
    try:
        services.delete_photo(attachment, request.user)
    except ValidationError as exc:
        _errors(request, exc)
        return redirect('ticket_detail', pk=ticket_pk)
    messages.success(request, "Photo removed.")
    return redirect('ticket_edit', pk=ticket_pk)


# ------------------------------------------------------------------- staff
@staff_required
def dispatch_list(request):  # Read (all tickets) - F-09/F-10
    filter_form = TicketFilterForm(request.GET or None)
    qs = IncidentTicket.objects.select_related('category', 'zone', 'reporter')
    qs = _filter(qs, filter_form)
    page = Paginator(qs, 15).get_page(request.GET.get('page'))
    params = request.GET.copy()
    params.pop('page', None)
    return render(request, 'tickets/dispatch_list.html', {
        'page': page, 'filter_form': filter_form, 'querystring': params.urlencode()})


@staff_required
def manage_ticket(request, pk):  # Update (assign / urgency / status / remarks)
    ticket = get_object_or_404(
        IncidentTicket.objects.select_related('category', 'zone', 'reporter'), pk=pk)
    action = request.POST.get('action') if request.method == 'POST' else None
    bound = lambda cls, name: cls(request.POST) if action == name else cls()  # noqa: E731

    urgency_form = (UrgencyForm(request.POST) if action == 'urgency'
                    else UrgencyForm(initial={'urgency': ticket.urgency}))
    assign_form, advance_form, remark_form = (
        bound(AssignTeamForm, 'assign'), bound(AdvanceStatusForm, 'advance'), bound(RemarkForm, 'remark'))

    if request.method == 'POST':
        forms_by_action = {'urgency': urgency_form, 'assign': assign_form,
                           'advance': advance_form, 'remark': remark_form}
        form = forms_by_action.get(action)
        if form is None:
            messages.error(request, "Unknown action.")
        elif not form.is_valid():
            messages.error(request, "Please correct the errors below.")
        else:
            d = form.cleaned_data
            try:
                if action == 'urgency':
                    services.set_urgency(ticket, request.user, d['urgency'])
                    messages.success(request, f"Urgency set to {d['urgency']}.")
                elif action == 'assign':
                    services.assign_team(ticket, request.user, d['team'])
                    messages.success(request, f"Ticket assigned to {d['team'].name}.")
                elif action == 'advance':
                    t = services.advance_status(ticket, request.user,
                                                d['resolution_summary'], d['remarks'])
                    messages.success(request, f"Status advanced to {t.status}.")
                else:
                    services.add_remark(ticket, request.user, d['remark_text'], d['visibility'])
                    messages.success(request, "Remark posted.")
                return redirect('manage_ticket', pk=ticket.pk)
            except ValidationError as exc:
                _errors(request, exc)
        ticket.refresh_from_db()

    return render(request, 'tickets/manage_ticket.html', {
        'ticket': ticket,
        'assignment': ticket.active_assignment,
        'assignment_history': ticket.assignments.select_related('team', 'assigned_by'),
        'logs': ticket.status_logs.select_related('changed_by'),
        'remarks': ticket.remarks.select_related('author'),
        'attachments': ticket.attachments.all(),
        'urgency_form': urgency_form, 'assign_form': assign_form,
        'advance_form': advance_form, 'remark_form': remark_form,
    })


@staff_required
@require_POST
def remark_delete(request, pk):  # Delete (remark)
    remark = get_object_or_404(TicketRemark, pk=pk)
    ticket_pk = remark.ticket_id
    try:
        services.delete_remark(remark, request.user)
        messages.success(request, "Remark deleted.")
    except ValidationError as exc:
        _errors(request, exc)
    return redirect('manage_ticket', pk=ticket_pk)
