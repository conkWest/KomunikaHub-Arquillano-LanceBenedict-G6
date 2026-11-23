"""Incident ticketing models (SDD section 4: ERD tables 7-13 + zones).

Business rules referenced as BR-nn come from the Software Design Document.
"""
import os
import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinLengthValidator
from django.db import models
from django.db.models import Q

MAX_PHOTOS = 3                      # BR-23
MAX_PHOTO_BYTES = 5 * 1024 * 1024   # BR-23 (5,242,880 bytes)
MAX_OPEN_TICKETS = 5                # BR-21
MIN_DESCRIPTION = 20                # BR-20
ALLOWED_PHOTO_TYPES = {             # BR-23
    '.jpg': 'image/jpeg',
    '.jpeg': 'image/jpeg',
    '.png': 'image/png',
    '.webp': 'image/webp',
}


def _check(condition, name):
    """CheckConstraint that works on Django < 5.1 (check=) and >= 5.1 (condition=)."""
    try:
        return models.CheckConstraint(condition=condition, name=name)
    except TypeError:  # pragma: no cover - older Django
        return models.CheckConstraint(check=condition, name=name)


# --------------------------------------------------------------------------
# Reference data (F-12, BR-35): deactivated, never deleted
# --------------------------------------------------------------------------
class Zone(models.Model):
    code = models.CharField(max_length=10, unique=True)
    name = models.CharField(max_length=80)
    description = models.CharField(max_length=200, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['code']

    def __str__(self):
        return f"{self.code} - {self.name}"


class IncidentCategory(models.Model):
    name = models.CharField(max_length=60, unique=True)
    description = models.CharField(max_length=200, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['name']
        verbose_name_plural = 'incident categories'

    def __str__(self):
        return self.name


class FieldTeam(models.Model):
    name = models.CharField(max_length=80, unique=True)
    specialization = models.CharField(max_length=80, blank=True)
    contact_number = models.CharField(max_length=20, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


# --------------------------------------------------------------------------
# Incident ticket (F-08, F-09, F-10)
# --------------------------------------------------------------------------
class IncidentTicket(models.Model):
    PENDING, IN_PROGRESS, RESOLVED = 'Pending', 'In Progress', 'Resolved'
    STATUS_CHOICES = [(s, s) for s in (PENDING, IN_PROGRESS, RESOLVED)]
    NEXT_STATUS = {PENDING: IN_PROGRESS, IN_PROGRESS: RESOLVED}  # BR-26

    LOW, MEDIUM, HIGH, CRITICAL = 'Low', 'Medium', 'High', 'Critical'
    URGENCY_CHOICES = [(u, u) for u in (LOW, MEDIUM, HIGH, CRITICAL)]

    ticket_no = models.CharField(max_length=20, unique=True, editable=False)  # BR-22
    reporter = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
                                 related_name='reported_tickets')
    category = models.ForeignKey(IncidentCategory, on_delete=models.PROTECT, related_name='tickets')
    zone = models.ForeignKey(Zone, on_delete=models.PROTECT, related_name='tickets')
    title = models.CharField(max_length=120)
    description = models.TextField(validators=[MinLengthValidator(MIN_DESCRIPTION)])  # BR-20
    location_details = models.CharField(max_length=200)
    urgency = models.CharField(max_length=10, choices=URGENCY_CHOICES, default=MEDIUM)
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default=PENDING)
    resolution_summary = models.TextField(blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [
            _check(Q(status__in=['Pending', 'In Progress', 'Resolved']), 'ticket_status_valid'),
            _check(Q(urgency__in=['Low', 'Medium', 'High', 'Critical']), 'ticket_urgency_valid'),
            # BR-28: Resolved needs a summary and a resolution time
            _check(~Q(status='Resolved') | (~Q(resolution_summary='') & Q(resolved_at__isnull=False)),
                   'ticket_resolved_needs_summary'),
        ]
        indexes = [
            models.Index(fields=['reporter']),
            models.Index(fields=['status', 'urgency']),
        ]

    def __str__(self):
        return f"{self.ticket_no} - {self.title}"

    # -- helpers ----------------------------------------------------------
    @property
    def is_closed(self):  # BR-34
        return self.status == self.RESOLVED

    @property
    def active_assignment(self):
        return self.assignments.filter(released_at__isnull=True).select_related('team').first()

    @property
    def resident_can_edit(self):  # BR-25
        return self.status == self.PENDING and not self.assignments.exists()

    @property
    def next_status(self):
        return self.NEXT_STATUS.get(self.status)


def _photo_path(instance, filename):
    ext = os.path.splitext(filename)[1].lower()
    return f"tickets/{instance.ticket_id}/{uuid.uuid4().hex}{ext}"


class TicketAttachment(models.Model):
    ticket = models.ForeignKey(IncidentTicket, on_delete=models.PROTECT, related_name='attachments')
    image = models.ImageField(upload_to=_photo_path)
    file_name = models.CharField(max_length=255)
    mime_type = models.CharField(max_length=20)
    file_size_bytes = models.PositiveIntegerField()
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['uploaded_at']
        constraints = [
            _check(Q(mime_type__in=['image/jpeg', 'image/png', 'image/webp']), 'attachment_mime_valid'),
            _check(Q(file_size_bytes__gte=1, file_size_bytes__lte=MAX_PHOTO_BYTES), 'attachment_size_valid'),
        ]

    def __str__(self):
        return self.file_name


class TicketAssignment(models.Model):
    ticket = models.ForeignKey(IncidentTicket, on_delete=models.PROTECT, related_name='assignments')
    team = models.ForeignKey(FieldTeam, on_delete=models.PROTECT, related_name='assignments')
    assigned_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
                                    related_name='made_assignments')
    assigned_at = models.DateTimeField(auto_now_add=True)
    released_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-assigned_at']
        constraints = [
            # BR-29: only one active assignment per ticket
            models.UniqueConstraint(fields=['ticket'], condition=Q(released_at__isnull=True),
                                    name='one_active_assignment_per_ticket'),
        ]

    def __str__(self):
        return f"{self.ticket.ticket_no} -> {self.team}"


class TicketStatusLog(models.Model):
    """Append-only audit trail (F-11, BR-31, BR-32)."""
    ticket = models.ForeignKey(IncidentTicket, on_delete=models.PROTECT, related_name='status_logs')
    changed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
                                   related_name='status_changes')
    old_status = models.CharField(max_length=12, null=True, blank=True)
    new_status = models.CharField(max_length=12)
    remarks = models.CharField(max_length=500, blank=True)
    changed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['changed_at', 'pk']
        constraints = [
            _check((Q(old_status__isnull=True) & Q(new_status='Pending')) |
                   (Q(old_status='Pending') & Q(new_status='In Progress')) |
                   (Q(old_status='In Progress') & Q(new_status='Resolved')),
                   'status_log_forward_only'),  # BR-26
        ]

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError("Status log entries are immutable.")  # BR-32
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Status log entries cannot be deleted.")  # BR-32

    def __str__(self):
        return f"{self.ticket.ticket_no}: {self.old_status or '-'} -> {self.new_status}"


class TicketRemark(models.Model):
    INTERNAL, PUBLIC = 'Internal', 'Public'
    VISIBILITY_CHOICES = [(INTERNAL, 'Internal (staff only)'), (PUBLIC, 'Public (resident can see)')]

    ticket = models.ForeignKey(IncidentTicket, on_delete=models.PROTECT, related_name='remarks')
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
                               related_name='ticket_remarks')
    remark_text = models.CharField(max_length=1000)
    visibility = models.CharField(max_length=10, choices=VISIBILITY_CHOICES, default=INTERNAL)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at', 'pk']
        constraints = [_check(Q(visibility__in=['Internal', 'Public']), 'remark_visibility_valid')]

    def __str__(self):
        return f"{self.ticket.ticket_no} [{self.visibility}]"
