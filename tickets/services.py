"""Business logic for the ticket workflow. Views stay thin; every rule lives here."""
import os

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .models import (ALLOWED_PHOTO_TYPES, MAX_OPEN_TICKETS, MAX_PHOTOS, FieldTeam,
                     IncidentTicket, TicketAssignment, TicketAttachment, TicketRemark,
                     TicketStatusLog)


def is_staff(user):
    return user.is_authenticated and user.role == 'staff'


def is_resident(user):
    return user.is_authenticated and user.role == 'resident'


def open_ticket_count(user):
    return IncidentTicket.objects.filter(reporter=user).exclude(status=IncidentTicket.RESOLVED).count()


def _lock(ticket):
    return IncidentTicket.objects.select_for_update().get(pk=ticket.pk)


def add_photos(ticket, files):
    """Save validated photo uploads. Re-checks the limit (BR-23) inside the transaction."""
    existing = ticket.attachments.count()
    if existing + len(files) > MAX_PHOTOS:
        raise ValidationError(f"A ticket can have at most {MAX_PHOTOS} photos.")
    for f in files:
        ext = os.path.splitext(f.name)[1].lower()
        TicketAttachment.objects.create(
            ticket=ticket, image=f, file_name=f.name[:255],
            mime_type=ALLOWED_PHOTO_TYPES[ext], file_size_bytes=f.size,
        )


@transaction.atomic
def create_ticket(reporter, form, photos):
    """F-08. `form` is a validated TicketForm."""
    if not is_resident(reporter):  # BR-19
        raise ValidationError("Only residents can submit incident tickets.")
    if open_ticket_count(reporter) >= MAX_OPEN_TICKETS:  # BR-21
        raise ValidationError(
            f"You already have {MAX_OPEN_TICKETS} unresolved tickets. "
            "Please wait until one is resolved before filing another.")
    ticket = form.save(commit=False)
    ticket.reporter = reporter
    ticket.ticket_no = f"TMP-{os.urandom(8).hex()}"
    ticket.save()
    ticket.ticket_no = f"KH-{timezone.now().year}-{ticket.pk:05d}"  # BR-22
    ticket.save(update_fields=['ticket_no'])
    TicketStatusLog.objects.create(  # BR-31 initial entry
        ticket=ticket, changed_by=reporter, old_status=None,
        new_status=IncidentTicket.PENDING, remarks='Ticket submitted')
    add_photos(ticket, photos)
    return ticket


@transaction.atomic
def update_ticket(ticket, user, form, photos):
    """Resident edit, allowed only while Pending and unassigned (BR-25)."""
    ticket = _lock(ticket)
    if ticket.reporter_id != user.id:
        raise ValidationError("You can only edit your own tickets.")
    if not ticket.resident_can_edit:
        raise ValidationError("This ticket can no longer be edited: it is already being handled.")
    ticket = form.save()
    add_photos(ticket, photos)
    return ticket


@transaction.atomic
def delete_photo(attachment, user):
    ticket = _lock(attachment.ticket)
    if ticket.reporter_id != user.id:
        raise ValidationError("You can only change your own tickets.")
    if not ticket.resident_can_edit:  # BR-25
        raise ValidationError("Photos can only be removed while the ticket is Pending and unassigned.")
    attachment.image.delete(save=False)
    attachment.delete()


def _require_admin(user):
    if not is_staff(user):  # BR-30
        raise ValidationError("Only administrators can perform this action.")


def _require_open(ticket):
    if ticket.is_closed:  # BR-34
        raise ValidationError("This ticket is Resolved and closed. No further changes are allowed.")


@transaction.atomic
def set_urgency(ticket, user, urgency):
    _require_admin(user)
    ticket = _lock(ticket)
    _require_open(ticket)
    if urgency not in dict(IncidentTicket.URGENCY_CHOICES):
        raise ValidationError("Invalid urgency level.")
    ticket.urgency = urgency
    ticket.save(update_fields=['urgency', 'updated_at'])
    return ticket


@transaction.atomic
def assign_team(ticket, user, team):
    _require_admin(user)
    ticket = _lock(ticket)
    _require_open(ticket)
    if not team.is_active:  # BR-27 / BR-35
        raise ValidationError("That field team is inactive and cannot receive assignments.")
    current = ticket.active_assignment
    if current and current.team_id == team.id:
        raise ValidationError(f"{team.name} is already assigned to this ticket.")
    if current:  # BR-29: release the previous assignment first
        current.released_at = timezone.now()
        current.save(update_fields=['released_at'])
    return TicketAssignment.objects.create(ticket=ticket, team=team, assigned_by=user)


@transaction.atomic
def advance_status(ticket, user, resolution_summary='', remarks=''):
    """Move forward exactly one step (BR-26)."""
    _require_admin(user)
    ticket = _lock(ticket)
    _require_open(ticket)
    new = ticket.next_status
    old = ticket.status
    if new == IncidentTicket.IN_PROGRESS and not ticket.active_assignment:  # BR-27
        raise ValidationError("Assign an active field team before moving the ticket to In Progress.")
    if new == IncidentTicket.RESOLVED:
        summary = (resolution_summary or '').strip()
        if not summary:  # BR-28
            raise ValidationError("A resolution summary is required to resolve a ticket.")
        ticket.resolution_summary = summary
        ticket.resolved_at = timezone.now()
    ticket.status = new
    ticket.save()
    TicketStatusLog.objects.create(ticket=ticket, changed_by=user, old_status=old,
                                   new_status=new, remarks=(remarks or '')[:500])
    return ticket


@transaction.atomic
def add_remark(ticket, user, text, visibility):
    _require_admin(user)
    ticket = _lock(ticket)
    _require_open(ticket)
    return TicketRemark.objects.create(ticket=ticket, author=user, remark_text=text, visibility=visibility)


@transaction.atomic
def delete_remark(remark, user):
    _require_admin(user)
    ticket = _lock(remark.ticket)
    _require_open(ticket)
    if remark.author_id != user.id:
        raise ValidationError("You can only delete remarks you wrote.")
    remark.delete()
