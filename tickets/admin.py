from django.contrib import admin

from .models import (FieldTeam, IncidentCategory, IncidentTicket, TicketAssignment,
                     TicketAttachment, TicketRemark, TicketStatusLog, Zone)


@admin.register(Zone)
class ZoneAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'is_active')
    list_filter = ('is_active',)


@admin.register(IncidentCategory)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'is_active')
    list_filter = ('is_active',)


@admin.register(FieldTeam)
class FieldTeamAdmin(admin.ModelAdmin):
    list_display = ('name', 'specialization', 'contact_number', 'is_active')
    list_filter = ('is_active',)


@admin.register(IncidentTicket)
class TicketAdmin(admin.ModelAdmin):
    list_display = ('ticket_no', 'title', 'reporter', 'status', 'urgency', 'zone', 'created_at')
    list_filter = ('status', 'urgency', 'zone', 'category')
    search_fields = ('ticket_no', 'title')


@admin.register(TicketStatusLog)
class StatusLogAdmin(admin.ModelAdmin):
    list_display = ('ticket', 'old_status', 'new_status', 'changed_by', 'changed_at')

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


admin.site.register(TicketAssignment)
admin.site.register(TicketAttachment)
admin.site.register(TicketRemark)
