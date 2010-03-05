from django.conf.urls.defaults import patterns, url
from django.utils.translation import ugettext_lazy as _
from django.utils.datastructures import SortedDict
from django.forms import models as modelforms
from django import forms
from django.forms.fields import DateTimeField, IntegerField, HiddenInput
from django.core import signals as core_signals
from django.http import HttpResponse
from django.shortcuts import render_to_response

from ella import newman
from ella.newman import widgets, config
from ella.ellaexports import models, timeline


class ExportPositionInlineAdmin(newman.NewmanTabularInline):
    model = models.ExportPosition
    extra = 1

class ExportAdmin(newman.NewmanModelAdmin):
    prepopulated_fields = {'slug': ('title',)}
    raw_id_fields = ('photo_format',)
    list_filter = ('category',)
    search_fields = ('title', 'slug',)
    suggest_fields = {
        'category': ('__unicode__', 'title', 'slug',),
    }

    def get_urls(self):

        info = self.model._meta.app_label, self.model._meta.module_name

        urlpatterns = patterns('',
            url(r'^timeline/$',
                self.timeline_changelist_view,
                name='%s_%s_timeline' % info),
            url(r'^timeline/insert/(?P<position>\d+)/(?P<id_item>\d+)/(?P<id_export>\d+)/(?P<visible_from>.*)/(?P<id_publishable>\d+)/$',
                timeline.insert_view,
                name='%s_%s_timeline_insert' % info),
            url(r'^timeline/append/(?P<position>\d+)/(?P<id_item>\d+)/(?P<id_export>\d+)/(?P<visible_from>.*)/(?P<id_publishable>\d+)/$',
                timeline.append_view,
                name='%s_%s_timeline_append' % info),
        )
        urlpatterns += super(ExportAdmin, self).get_urls()
        return urlpatterns

    def timeline_changelist_view(self, request, extra_context=None):
        """
        Returns timeline view (more powerful interface to maintain export positions).
        """
        return timeline.timeline_view(request, extra_context)

class ExportMetaAdmin(newman.NewmanModelAdmin):
    inlines = (ExportPositionInlineAdmin,)
    raw_id_fields = ('photo',)
    suggest_fields = {
        'publishable': ('__unicode__', 'title', 'slug',),
    }
    fieldsets = (
        (None, {'fields': ('publishable', )}) ,
        (_('Export meta options'), {
            'fields': ('title', 'photo', 'description'),
            'classes': ('collapsed',)
        })
    )

class HiddenIntegerField(IntegerField):
    widget = HiddenInput

class MetaInlineForm(modelforms.ModelForm):
    position_id = HiddenIntegerField(required=False)
    position_from =  DateTimeField(label=_('Visible From'), widget=widgets.DateTimeWidget)
    position_to =  DateTimeField(label=_('Visible To'), widget=widgets.DateTimeWidget, required=False)
    export =  modelforms.ModelChoiceField(models.Export.objects.all(), label=_('Export'))
    _export_stack = dict()
    # override base_fields and include all the other declared fields
    declared_fields = SortedDict(
        (
            ('title', HiddenIntegerField(label=u'', required=False)),
            ('position_id', HiddenIntegerField(label=u'', required=False)),
            ('position_from', DateTimeField(label=_('Visible From'), widget=widgets.DateTimeWidget)),
            ('position_to', DateTimeField(label=_('Visible To'), widget=widgets.DateTimeWidget, required=False)),
            ('export', modelforms.ModelChoiceField(models.Export.objects.all(), initial=None, label=_('Export'), show_hidden_initial=True))
        )
    )

    def __init__(self, *args, **kwargs):
        super(MetaInlineForm, self).__init__(*args, **kwargs)
        self.show_edit_url = True # shows edit button
        core_signals.request_finished.connect(receiver=MetaInlineForm.reset_export_enumerator)
        existing_object = False
        new_object = False
        id_initial = None
        from_initial = to_initial = ''
        export_initial = None
        export_qs = models.Export.objects.all()
        if 'instance' in kwargs and 'data' not in kwargs:
            existing_object = True
            instance = kwargs['instance']
            if instance:
                id_initial, from_initial, to_initial, export_initial = self.get_initial_data(instance)
        elif 'data' not in kwargs:
            new_object = True

        self.assign_init_field(
            'position_id',
            HiddenIntegerField(initial=id_initial, label=u'', required=False)
        )
        self.assign_init_field(
            'position_from', 
            DateTimeField(initial=from_initial, label=_('Visible From'), widget=widgets.DateTimeWidget)
        )
        self.assign_init_field(
            'position_to', 
            DateTimeField(initial=to_initial, label=_('Visible To'), widget=widgets.DateTimeWidget, required=False)
        )
        self.assign_init_field(
            'export',
            modelforms.ModelChoiceField(export_qs, initial=export_initial, label=_('Export'), show_hidden_initial=True)
        )

    def assign_init_field(self, field_name, value):
        self.fields[field_name] = self.base_fields[field_name] = value

    def get_initial_data(self, instance):
        " @return tuple (visible_from, visible_to, export_initial) "
        positions = models.ExportPosition.objects.filter(object=instance)
        if not positions:
            return ('', '', None)
        pcount = positions.count()
        if pcount > 1 and not MetaInlineForm._export_stack.get(instance, False):
            MetaInlineForm._export_stack[instance] = list()
            map( lambda p: MetaInlineForm._export_stack[instance].insert(0, p), positions )
        if pcount == 1:
            pos = positions[0]
        elif pcount > 1:
            pos = MetaInlineForm._export_stack[instance].pop()
        out = (pos.pk, pos.visible_from, pos.visible_to, pos.export.pk)
        return out

    @staticmethod
    def reset_export_enumerator(*args, **kwargs):
        " Clears _export_stack at the end of HTTP request. "
        core_signals.request_finished.disconnect(receiver=MetaInlineForm.reset_export_enumerator)
        MetaInlineForm._export_stack.clear()

    def get_date_field_key(self, field):
        return '%s-%s' % (self.prefix, field)

    def clean(self):
        """
        if not self.is_valid() or not self.cleaned_data or not self.instance:
            return self.cleaned_data
        """
        self.cleaned_data['position_id'] = self.data[self.get_date_field_key('position_id')]
        self.cleaned_data['position_from'] = self.data[self.get_date_field_key('position_from')]
        data_position_to = self.data[self.get_date_field_key('position_to')]
        if data_position_to:
            self.cleaned_data['position_to'] = data_position_to
            print 'Position to: [%s]' %  self.cleaned_data['position_to']
        self.cleaned_data['export'] = self.data[self.get_date_field_key('export')]
        return self.cleaned_data

    def save(self, commit=True):
        out = super(MetaInlineForm, self).save(commit=commit)

        def save_them():
            export = models.Export.objects.get(pk=int(self.cleaned_data['export']))
            positions = models.ExportPosition.objects.filter(
                object=self.instance,
                export=export
            )
            if not self.cleaned_data['position_id']:
                position = models.ExportPosition(
                    object=self.instance,
                )
            else:
                pos_id = int(self.cleaned_data['position_id'])
                position = models.ExportPosition.objects.get(pk=pos_id)
            position.export = export
            position.visible_from = self.cleaned_data['position_from']
            position.visible_to = self.cleaned_data['position_to']
            position.save()

        if commit:
            save_them()
        else:
            save_m2m = getattr(self, 'save_m2m', None)
            def save_all():
                if save_m2m:
                    save_m2m()
                save_them()
            self.save_m2m = save_all
        return out

class ExportMetaInline(newman.NewmanStackedInline):
    form = MetaInlineForm
    model = models.ExportMeta
    #suggest_fields = {'photo': ('__unicode__', 'title', 'slug',)}
    raw_id_fields = ('photo',)
    extra = 1
    """
    fieldsets = (
        (None, {'fields': tuple()}) ,
        (_('Export meta options'), {
            'fields': ('position_from', 'position_to', 'title', 'photo', 'description'),
            'classes': ('collapsed',)
        })
    ) #FIXME add title, photo, description fields to MetaInlineForm, then fieldsets will work
    """


newman.site.register(models.Export, ExportAdmin)
newman.site.register(models.ExportPosition)
newman.site.register(models.ExportMeta, ExportMetaAdmin)

# Register ExportMetaInline in standard PublishableAdmin
newman.site.append_inline(config.TAGGED_MODELS, ExportMetaInline) # removed due to user interface is too dificult for an user
