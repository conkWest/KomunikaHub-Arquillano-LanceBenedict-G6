import io
import shutil

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image

from . import services
from .models import (FieldTeam, IncidentCategory, IncidentTicket, TicketRemark, TicketStatusLog, Zone)

User = get_user_model()
TEST_MEDIA = settings.BASE_DIR / 'media_test'
LONG_DESC = 'A large pothole has formed in the middle of the road near the school.'


def png(name='p.png', size=None):
    buf = io.BytesIO()
    Image.new('RGB', (10, 10), 'red').save(buf, 'PNG')
    data = buf.getvalue()
    if size:
        data = data + b'0' * (size - len(data))
    return SimpleUploadedFile(name, data, content_type='image/png')


@override_settings(MEDIA_ROOT=TEST_MEDIA)
class TicketBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.zone = Zone.objects.create(code='Z-01', name='Purok 1')
        cls.cat = IncidentCategory.objects.create(name='Road Damage')
        cls.team = FieldTeam.objects.create(name='Crew A')
        cls.res = User.objects.create_user('res1', 'r1@x.com', 'pass12345', role='resident')
        cls.res2 = User.objects.create_user('res2', 'r2@x.com', 'pass12345', role='resident')
        cls.staff = User.objects.create_user('staff1', 's@x.com', 'pass12345', role='staff')

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TEST_MEDIA, ignore_errors=True)

    def payload(self, **over):
        d = {'title': 'Pothole on Main St', 'category': self.cat.pk, 'zone': self.zone.pk,
             'location_details': 'In front of the school', 'description': LONG_DESC}
        d.update(over)
        return d

    def make_ticket(self, user=None, **kw):
        user = user or self.res
        t = IncidentTicket(reporter=user, category=self.cat, zone=self.zone, title='T title',
                           description=LONG_DESC, location_details='Somewhere', ticket_no=f'X{IncidentTicket.objects.count()}')
        t.save()
        t.ticket_no = f'KH-2026-{t.pk:05d}'
        t.save()
        TicketStatusLog.objects.create(ticket=t, changed_by=user, new_status='Pending')
        return t


class ResidentFlowTests(TicketBase):
    def test_login_required(self):
        self.assertEqual(self.client.get(reverse('my_tickets')).status_code, 302)

    def test_create_ticket_end_to_end(self):
        self.client.login(username='res1', password='pass12345')
        r = self.client.post(reverse('ticket_create'), {**self.payload(), 'photos': [png('a.png')]}, follow=True)
        self.assertEqual(r.status_code, 200)
        t = IncidentTicket.objects.get()
        self.assertEqual(t.reporter, self.res)
        self.assertEqual(t.status, 'Pending')
        self.assertRegex(t.ticket_no, r'^KH-\d{4}-\d{5}$')
        self.assertEqual(t.attachments.count(), 1)
        log = t.status_logs.get()
        self.assertIsNone(log.old_status)
        self.assertEqual(log.new_status, 'Pending')
        self.assertContains(r, t.ticket_no)

    def test_short_description_rejected(self):
        self.client.login(username='res1', password='pass12345')
        r = self.client.post(reverse('ticket_create'), self.payload(description='too short'))
        self.assertEqual(IncidentTicket.objects.count(), 0)
        self.assertContains(r, 'at least 20 characters')

    def test_required_fields(self):
        self.client.login(username='res1', password='pass12345')
        r = self.client.post(reverse('ticket_create'), {})
        self.assertEqual(IncidentTicket.objects.count(), 0)
        self.assertContains(r, 'This field is required')

    def test_max_three_photos(self):
        self.client.login(username='res1', password='pass12345')
        files = [png(f'{i}.png') for i in range(4)]
        r = self.client.post(reverse('ticket_create'), {**self.payload(), 'photos': files})
        self.assertEqual(IncidentTicket.objects.count(), 0)
        self.assertContains(r, 'at most 3 photos')

    def test_photo_type_and_size(self):
        self.client.login(username='res1', password='pass12345')
        bad = SimpleUploadedFile('x.gif', b'GIF89a', content_type='image/gif')
        r = self.client.post(reverse('ticket_create'), {**self.payload(), 'photos': [bad]})
        self.assertContains(r, 'not allowed')
        big = png('big.png', size=5 * 1024 * 1024 + 1)
        r = self.client.post(reverse('ticket_create'), {**self.payload(), 'photos': [big]})
        self.assertContains(r, 'larger than 5 MB')
        self.assertEqual(IncidentTicket.objects.count(), 0)

    def test_five_open_ticket_limit(self):
        for _ in range(5):
            self.make_ticket()
        self.client.login(username='res1', password='pass12345')
        r = self.client.post(reverse('ticket_create'), self.payload(), follow=True)
        self.assertEqual(IncidentTicket.objects.count(), 5)
        self.assertContains(r, '5 unresolved tickets')

    def test_resolved_tickets_do_not_count_toward_limit(self):
        for _ in range(5):
            self.make_ticket()
        t = IncidentTicket.objects.first()
        IncidentTicket.objects.filter(pk=t.pk).update(status='Resolved', resolution_summary='ok',
                                                      resolved_at=t.created_at)
        self.client.login(username='res1', password='pass12345')
        self.client.post(reverse('ticket_create'), self.payload())
        self.assertEqual(IncidentTicket.objects.count(), 6)

    def test_resident_sees_only_own_tickets(self):
        mine, theirs = self.make_ticket(self.res), self.make_ticket(self.res2)
        self.client.login(username='res1', password='pass12345')
        self.assertContains(self.client.get(reverse('my_tickets')), mine.ticket_no)
        self.assertNotContains(self.client.get(reverse('my_tickets')), theirs.ticket_no)
        self.assertEqual(self.client.get(reverse('ticket_detail', args=[theirs.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse('ticket_edit', args=[theirs.pk])).status_code, 404)

    def test_edit_only_while_pending_and_unassigned(self):
        t = self.make_ticket()
        self.client.login(username='res1', password='pass12345')
        r = self.client.post(reverse('ticket_edit', args=[t.pk]), self.payload(title='Updated title'))
        self.assertRedirects(r, reverse('ticket_detail', args=[t.pk]))
        t.refresh_from_db()
        self.assertEqual(t.title, 'Updated title')
        services.assign_team(t, self.staff, self.team)
        r = self.client.post(reverse('ticket_edit', args=[t.pk]), self.payload(title='Again'))
        t.refresh_from_db()
        self.assertEqual(t.title, 'Updated title')
        self.assertEqual(r.status_code, 302)

    def test_delete_photo(self):
        t = self.make_ticket()
        services.add_photos(t, [png('a.png')])
        a = t.attachments.get()
        self.client.login(username='res1', password='pass12345')
        self.client.post(reverse('attachment_delete', args=[a.pk]))
        self.assertEqual(t.attachments.count(), 0)

    def test_cannot_delete_other_residents_photo(self):
        t = self.make_ticket(self.res2)
        services.add_photos(t, [png('a.png')])
        self.client.login(username='res1', password='pass12345')
        r = self.client.post(reverse('attachment_delete', args=[t.attachments.get().pk]))
        self.assertEqual(r.status_code, 404)
        self.assertEqual(t.attachments.count(), 1)

    def test_internal_remarks_hidden_from_resident(self):
        t = self.make_ticket()
        services.add_remark(t, self.staff, 'SECRET internal note', 'Internal')
        services.add_remark(t, self.staff, 'Crew dispatched today', 'Public')
        self.client.login(username='res1', password='pass12345')
        r = self.client.get(reverse('ticket_detail', args=[t.pk]))
        self.assertContains(r, 'Crew dispatched today')
        self.assertNotContains(r, 'SECRET internal note')


class RoleAccessTests(TicketBase):
    def test_resident_denied_staff_pages(self):
        t = self.make_ticket()
        self.client.login(username='res1', password='pass12345')
        self.assertEqual(self.client.get(reverse('dispatch_list')).status_code, 403)
        self.assertEqual(self.client.get(reverse('manage_ticket', args=[t.pk])).status_code, 403)
        self.assertEqual(self.client.get(reverse('staff_dashboard')).status_code, 403)

    def test_staff_denied_resident_pages(self):
        self.client.login(username='staff1', password='pass12345')
        self.assertEqual(self.client.get(reverse('ticket_create')).status_code, 403)
        self.assertEqual(self.client.get(reverse('my_tickets')).status_code, 403)

    def test_staff_sees_all_and_filters(self):
        a, b = self.make_ticket(self.res), self.make_ticket(self.res2)
        services.set_urgency(b, self.staff, 'Critical')
        self.client.login(username='staff1', password='pass12345')
        r = self.client.get(reverse('dispatch_list'))
        self.assertContains(r, a.ticket_no)
        self.assertContains(r, b.ticket_no)
        r = self.client.get(reverse('dispatch_list'), {'urgency': 'Critical'})
        self.assertContains(r, b.ticket_no)
        self.assertNotContains(r, a.ticket_no)

    def test_dashboards_render_for_each_role(self):
        self.make_ticket()
        self.client.login(username='res1', password='pass12345')
        self.assertEqual(self.client.get(reverse('resident_dashboard')).status_code, 200)
        self.client.logout()
        self.client.login(username='staff1', password='pass12345')
        self.assertEqual(self.client.get(reverse('staff_dashboard')).status_code, 200)


class WorkflowTests(TicketBase):
    def setUp(self):
        self.t = self.make_ticket()

    def test_cannot_start_without_team(self):  # BR-27
        with self.assertRaises(ValidationError):
            services.advance_status(self.t, self.staff)

    def test_cannot_start_with_inactive_team(self):
        self.team.is_active = False
        self.team.save()
        with self.assertRaises(ValidationError):
            services.assign_team(self.t, self.staff, self.team)

    def test_full_flow_and_audit_log(self):
        services.assign_team(self.t, self.staff, self.team)
        services.advance_status(self.t, self.staff, remarks='Crew on site')
        self.t.refresh_from_db()
        self.assertEqual(self.t.status, 'In Progress')
        with self.assertRaises(ValidationError):  # BR-28
            services.advance_status(self.t, self.staff, resolution_summary='   ')
        services.advance_status(self.t, self.staff, resolution_summary='Pothole filled')
        self.t.refresh_from_db()
        self.assertEqual(self.t.status, 'Resolved')
        self.assertIsNotNone(self.t.resolved_at)
        self.assertEqual([(l.old_status, l.new_status) for l in self.t.status_logs.all()],
                         [(None, 'Pending'), ('Pending', 'In Progress'), ('In Progress', 'Resolved')])

    def test_closed_ticket_is_locked(self):  # BR-34
        services.assign_team(self.t, self.staff, self.team)
        services.advance_status(self.t, self.staff)
        services.advance_status(self.t, self.staff, resolution_summary='Done')
        for fn in (lambda: services.advance_status(self.t, self.staff),
                   lambda: services.add_remark(self.t, self.staff, 'x', 'Public'),
                   lambda: services.assign_team(self.t, self.staff, self.team),
                   lambda: services.set_urgency(self.t, self.staff, 'High')):
            with self.assertRaises(ValidationError):
                fn()

    def test_reassign_releases_previous(self):  # BR-29
        team2 = FieldTeam.objects.create(name='Crew B')
        services.assign_team(self.t, self.staff, self.team)
        services.assign_team(self.t, self.staff, team2)
        self.assertEqual(self.t.assignments.filter(released_at__isnull=True).count(), 1)
        self.assertEqual(self.t.active_assignment.team, team2)
        self.assertEqual(self.t.assignments.count(), 2)

    def test_db_blocks_two_active_assignments(self):
        services.assign_team(self.t, self.staff, self.team)
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.t.assignments.create(team=self.team, assigned_by=self.staff)

    def test_status_log_immutable(self):  # BR-32
        log = self.t.status_logs.get()
        log.remarks = 'tamper'
        with self.assertRaises(ValidationError):
            log.save()
        with self.assertRaises(ValidationError):
            log.delete()

    def test_resident_cannot_use_staff_services(self):  # BR-30
        for fn in (lambda: services.assign_team(self.t, self.res, self.team),
                   lambda: services.set_urgency(self.t, self.res, 'High'),
                   lambda: services.add_remark(self.t, self.res, 'x', 'Public')):
            with self.assertRaises(ValidationError):
                fn()

    def test_staff_manage_view_flow(self):
        self.client.login(username='staff1', password='pass12345')
        url = reverse('manage_ticket', args=[self.t.pk])
        self.assertContains(self.client.get(url), self.t.ticket_no)
        r = self.client.post(url, {'action': 'advance'}, follow=True)
        self.assertContains(r, 'Assign an active field team')
        self.client.post(url, {'action': 'assign', 'team': self.team.pk})
        self.client.post(url, {'action': 'urgency', 'urgency': 'High'})
        self.client.post(url, {'action': 'advance', 'remarks': 'go'})
        self.client.post(url, {'action': 'remark', 'remark_text': 'Working on it', 'visibility': 'Public'})
        self.t.refresh_from_db()
        self.assertEqual((self.t.status, self.t.urgency), ('In Progress', 'High'))
        remark = TicketRemark.objects.get()
        self.client.post(reverse('remark_delete', args=[remark.pk]))
        self.assertEqual(TicketRemark.objects.count(), 0)
        r = self.client.post(url, {'action': 'advance', 'resolution_summary': ''}, follow=True)
        self.assertContains(r, 'resolution summary is required')
