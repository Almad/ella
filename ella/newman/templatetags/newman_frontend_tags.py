from django import template
from django.conf import settings
from django.contrib.contenttypes.models import ContentType

from ella.newman import config as newman_config
from ella.core.models.publishable import HitCount
from ella.positions.models import Position

register = template.Library()

def get_newman_url(obj):
    """ Assembles edit-object url for Newman admin. """
    ct = ContentType.objects.get_for_model(obj)
    url = '%(base)s#/%(app)s/%(model)s/%(pk)d/' % {
        'base': newman_config.BASE_URL,
        'app': ct.app_label,
        'model': ct.model,
        'pk': obj.pk
    }
    return url

@register.inclusion_tag('newman/tpl_tags/newman_frontend_admin.html', takes_context=True)
def newman_frontend_admin(context):
    user = context['user']
    vars = {}

    if not user or not user.is_staff:
        return vars

    #vars['logout_url'] = reverse('newman:logout')
    obj = context.get('object')
    if 'gallery' in context:
        obj = context.get('gallery')
    placement = context.get('placement')

    vars['user'] = user
    vars['STATIC_URL'] = context.get('STATIC_URL')
    vars['NEWMAN_MEDIA_URL'] = context.get('NEWMAN_MEDIA_URL')
    vars['placement'] = placement
    vars['category'] = context.get('category')
    vars['newman_index_url'] = newman_config.BASE_URL
    category = vars['category']
    if not category or not category.pk:
        return vars

    from django.db.models import Q
    import datetime
    now = datetime.datetime.now()
    lookup = (Q(active_from__isnull=True) | Q(active_from__lte=now)) & (Q(active_till__isnull=True) | Q(active_till__gt=now))
    positions = Position.objects.filter(lookup, category=category.pk, disabled=False, target_id__isnull=False)
    #print positions.query
    vars['positions'] = positions

    if obj:
        vars['object'] = obj
        vars['newman_object_url'] = get_newman_url(obj)
        if placement:
            vars['hitcount'] = HitCount.objects.get(placement=placement.pk)

    return vars


logout_url = newman_config.BASE_URL + 'logout/'
class NewmanLogoutNode(template.Node):
    def render(self, context):
        return logout_url

@register.tag
def newman_frontend_logout(parser, token):
    return NewmanLogoutNode()
