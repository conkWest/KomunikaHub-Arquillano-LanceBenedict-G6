import os

from django import forms
from django.db.models import Q

from .models import (ALLOWED_PHOTO_TYPES, MAX_PHOTO_BYTES, MAX_PHOTOS, FieldTeam, IncidentCategory,
                     IncidentTicket, TicketRemark, Zone)


class BootstrapMixin:
    def _style(self):
        for f in self.fields.values():
            w = f.widget
            if isinstance(w, forms.CheckboxInput):
                w.attrs['class'] = 'form-check-input'
            elif isinstance(w, (forms.Select, forms.SelectMultiple)):
                w.attrs['class'] = 'form-select'
            else:
                w.attrs['class'] = 'form-control'


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleFileField(forms.FileField):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault('widget', MultipleFileInput(attrs={'accept': '.jpg,.jpeg,.png,.webp'}))
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        single = super().clean
        if isinstance(data, (list, tuple)):
            return [single(d, initial) for d in data if d]
        return [single(data, initial)] if data else []


class TicketForm(BootstrapMixin, forms.ModelForm):
    photos = MultipleFileField(
        required=False, label='Photo evidence',
        help_text=f'Optional. Up to {MAX_PHOTOS} photos (JPEG, PNG or WebP, max 5 MB each).')

    class Meta:
        model = IncidentTicket
        fields = ['title', 'category', 'zone', 'location_details', 'description']
        widgets = {'description': forms.Textarea(attrs={'rows': 5})}
        help_texts = {
            'location_details': 'Street, block or landmark inside the selected zone.',
            'description': 'At least 20 characters. Describe what happened and how urgent it feels.',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        inst = self.instance
        # Only active categories/zones can be chosen for new records (BR-35),
        # but keep the current value selectable when editing.
        self.fields['category'].queryset = IncidentCategory.objects.filter(
            Q(is_active=True) | Q(pk=inst.category_id) if inst.pk else Q(is_active=True))
        self.fields['zone'].queryset = Zone.objects.filter(
            Q(is_active=True) | Q(pk=inst.zone_id) if inst.pk else Q(is_active=True))
        self.fields['category'].empty_label = 'Select a category'
        self.fields['zone'].empty_label = 'Select a zone'
        self._style()
        self.fields['photos'].widget.attrs['class'] = 'form-control'

    def clean_photos(self):
        files = self.cleaned_data.get('photos') or []
        existing = self.instance.attachments.count() if self.instance.pk else 0
        if existing + len(files) > MAX_PHOTOS:
            raise forms.ValidationError(
                f"A ticket can have at most {MAX_PHOTOS} photos "
                f"({existing} already attached, {len(files)} selected).")
        for f in files:
            ext = os.path.splitext(f.name)[1].lower()
            if ext not in ALLOWED_PHOTO_TYPES:
                raise forms.ValidationError(f"'{f.name}' is not allowed. Use JPEG, PNG or WebP photos.")
            if f.size > MAX_PHOTO_BYTES:
                raise forms.ValidationError(f"'{f.name}' is larger than 5 MB.")
            if f.size == 0:
                raise forms.ValidationError(f"'{f.name}' is empty.")
        return files

    def clean_title(self):
        title = self.cleaned_data['title'].strip()
        if len(title) < 5:
            raise forms.ValidationError("Please enter a title of at least 5 characters.")
        return title

    def clean_description(self):
        text = self.cleaned_data['description'].strip()
        if len(text) < 20:
            raise forms.ValidationError("The description must be at least 20 characters long.")
        return text


class TicketFilterForm(BootstrapMixin, forms.Form):
    """Used by both the resident list (status only) and the staff dispatch panel."""
    q = forms.CharField(required=False, label='Search',
                        widget=forms.TextInput(attrs={'placeholder': 'Ticket no. or title'}))
    status = forms.ChoiceField(required=False, choices=[('', 'All statuses')] + IncidentTicket.STATUS_CHOICES)
    urgency = forms.ChoiceField(required=False, choices=[('', 'All urgencies')] + IncidentTicket.URGENCY_CHOICES)
    zone = forms.ModelChoiceField(required=False, queryset=Zone.objects.all(), empty_label='All zones')
    category = forms.ModelChoiceField(required=False, queryset=IncidentCategory.objects.all(),
                                      empty_label='All categories')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._style()


class UrgencyForm(BootstrapMixin, forms.Form):
    urgency = forms.ChoiceField(choices=IncidentTicket.URGENCY_CHOICES)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._style()


class AssignTeamForm(BootstrapMixin, forms.Form):
    team = forms.ModelChoiceField(queryset=FieldTeam.objects.filter(is_active=True),
                                  empty_label='Select a field team')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['team'].queryset = FieldTeam.objects.filter(is_active=True)
        self._style()


class AdvanceStatusForm(BootstrapMixin, forms.Form):
    resolution_summary = forms.CharField(
        required=False, label='Resolution summary', widget=forms.Textarea(attrs={'rows': 3}),
        help_text='Required only when moving the ticket to Resolved.')
    remarks = forms.CharField(required=False, max_length=500, label='Note for the status log')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._style()


class RemarkForm(BootstrapMixin, forms.ModelForm):
    class Meta:
        model = TicketRemark
        fields = ['remark_text', 'visibility']
        labels = {'remark_text': 'Remark', 'visibility': 'Visibility'}
        widgets = {'remark_text': forms.Textarea(attrs={'rows': 3})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._style()

    def clean_remark_text(self):
        text = self.cleaned_data['remark_text'].strip()
        if not text:
            raise forms.ValidationError("A remark cannot be empty.")
        return text
