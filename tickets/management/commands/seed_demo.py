"""Seed reference data and demo/test accounts.

    python manage.py seed_demo
Safe to run more than once (uses get_or_create).
"""
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from tickets.models import FieldTeam, IncidentCategory, Zone

ZONES = [('Z-01', 'Purok 1 - Riverside'), ('Z-02', 'Purok 2 - Market Area'),
         ('Z-03', 'Purok 3 - Hillside'), ('Z-04', 'Purok 4 - Poblacion')]
CATEGORIES = [
    ('Road and Drainage Damage', 'Potholes, broken roads, clogged canals'),
    ('Streetlight or Electrical', 'Broken streetlights, exposed wires'),
    ('Garbage and Sanitation', 'Uncollected garbage, illegal dumping'),
    ('Water Supply', 'No water, leaks, low pressure'),
    ('Public Safety Hazard', 'Fallen poles, unsafe structures'),
    ('Noise Disturbance', 'Loud music, construction noise'),
    ('Flooding or Fallen Tree', 'Flood water, obstructing trees'),
]
TEAMS = [('Maintenance Crew A', 'Roads and drainage', '0917-000-0001'),
         ('Sanitation Team', 'Garbage and sanitation', '0917-000-0002'),
         ('Peacekeeping (Tanod) Unit', 'Safety and noise', '0917-000-0003'),
         ('Electrical Response Team', 'Streetlights and wiring', '0917-000-0004')]
PASSWORD = 'Komunika#2026'
USERS = [
    ('staff_demo', 'staff', 'Maria', 'Santos', 'staff_demo@komunikahub.test'),
    ('resident_demo', 'resident', 'Juan', 'Dela Cruz', 'resident_demo@komunikahub.test'),
    ('resident_demo2', 'resident', 'Ana', 'Reyes', 'resident_demo2@komunikahub.test'),
]


class Command(BaseCommand):
    help = 'Seed zones, incident categories, field teams and demo accounts.'

    def handle(self, *args, **options):
        for code, name in ZONES:
            Zone.objects.get_or_create(code=code, defaults={'name': name})
        for name, desc in CATEGORIES:
            IncidentCategory.objects.get_or_create(name=name, defaults={'description': desc})
        for name, spec, phone in TEAMS:
            FieldTeam.objects.get_or_create(name=name, defaults={'specialization': spec, 'contact_number': phone})
        User = get_user_model()
        for username, role, first, last, email in USERS:
            user, created = User.objects.get_or_create(username=username, defaults={
                'role': role, 'first_name': first, 'last_name': last, 'email': email,
                'is_staff': role == 'staff'})
            if created:
                user.set_password(PASSWORD)
                user.save()
        self.stdout.write(self.style.SUCCESS(
            f'Seeded. Demo accounts (password: {PASSWORD}): ' + ', '.join(u[0] for u in USERS)))
