import logging

from django.conf import settings
from django import template
from django.db import models
from django.utils.encoding import smart_str
from django.utils.safestring import mark_safe
from django.template.defaultfilters import stringfilter

from ella.core.models import Listing, Category, LISTING_UNIQUE_DEFAULT_SET
from ella.core.cache.utils import get_cached_object
from ella.core.cache.invalidate import CACHE_DELETER
from ella.core.box import BOX_INFO, Box
from ella.core.middleware import ECACHE_INFO


log = logging.getLogger('ella.core.templatetags')
register = template.Library()

DOUBLE_RENDER = getattr(settings, 'DOUBLE_RENDER', False)

class ListingNode(template.Node):
    def __init__(self, var_name, parameters, parameters_to_resolve):
        self.var_name = var_name
        self.parameters = parameters
        self.parameters_to_resolve = parameters_to_resolve

    def render(self, context):
        unique_var_name = None
        for key in self.parameters_to_resolve:
            if key == 'unique':
                unique_var_name = self.parameters[key]
            if key == 'unique' and unique_var_name not in context.dicts[-1]: # autocreate variable in context
                self.parameters[key] = context.dicts[-1][ unique_var_name ] = set()
                continue
            self.parameters[key] = template.Variable(self.parameters[key]).resolve(context)
        if self.parameters.has_key('category') and isinstance(self.parameters['category'], basestring):
            self.parameters['category'] = get_cached_object(Category, tree_path=self.parameters['category'], site__id=settings.SITE_ID)
        out = Listing.objects.get_listing(**self.parameters)

        if 'unique' in self.parameters:
            unique = self.parameters['unique'] #context[unique_var_name]
            map(lambda x: unique.add(x.placement_id),out)
        context[self.var_name] = out
        return ''

@register.tag
def listing(parser, token):
    """
    Tag that will obtain listing of top (priority-wise) objects for a given category and store them in context under given name.

    Usage::

        {% listing <limit>[ from <offset>][of <app.model>[, <app.model>[, ...]]][ for <category> ] [with children|descendents] as <result> %}

    Parameters:

        ==================================  ================================================
        Option                              Description
        ==================================  ================================================
        ``limit``                           Number of objects to retrieve.
        ``from offset``                     Starting with number (1-based), starts from first
                                            if no offset specified.
        ``of app.model, ...``               List of allowed models, all if omitted.
        ``for category``                    Category of the listing, all categories if not
                                            specified. Can be either string (tree path),
                                            or variable containing a Category object.
        ``with children``                   Include items from direct subcategories.
        ``with descendents``                Include items from all descend subcategories.
        ``as result``                       Store the resulting list in context under given
                                            name.
        ``unique [unique_set_name]``        Unique items across multiple listings.
                                            Name of context variable used to hold the data is optional.
        ==================================  ================================================

    Examples::

        {% listing 10 of articles.article for "home_page" as obj_list %}
        {% listing 10 of articles.article for category as obj_list %}
        {% listing 10 of articles.article for category with children as obj_list %}
        {% listing 10 of articles.article for category with descendents as obj_list %}
        {% listing 10 from 10 of articles.article as obj_list %}
        {% listing 10 of articles.article, photos.photo as obj_list %}

        Unique items across multiple listnings::
        {% listing 10 for category_uno as obj_list unique %}
        {% listing 4 for category_duo as obj_list unique %}
        {% listing 10 for category_uno as obj_list unique unique_set_name %}
        {% listing 4 for category_duo as obj_list unique unique_set_name %}
    """
    var_name, parameters, parameters_to_resolve = listing_parse(token.split_contents())
    return ListingNode(var_name, parameters, parameters_to_resolve)

def listing_parse(input):
    params={}
    params_to_resolve=[]
    if len(input) < 4:
        raise template.TemplateSyntaxError, "%r tag argument should have at least 4 arguments" % input[0]
    o=1
    # limit
    params['count'] = input[o]
    params_to_resolve.append('count')
    o=2
    # offset
    if input[o] == 'from':
        params['offset'] = input[o+1]
        params_to_resolve.append('offset')
        o=o+2
    # from - models definition
    if input[o] == 'of':
        o=o+1
        if 'for' in input:
            mc = input.index('for')
        elif 'as' in input:
            mc = input.index('as')
        if mc > 0:
            l = []
            for mod in ''.join(input[o:mc]).split(','):
                m = models.get_model(*mod.split('.'))
                if m is None:
                    raise template.TemplateSyntaxError, "%r tag cannot list objects of unknown model %r" % (input[0], mod)
                l.append(m)
            params['mods'] = l
        o=mc
    # for - category definition
    if input[o] == 'for':
        params['category'] = input[o+1]
        params_to_resolve.append('category')
        o=o+2
    # with
    if input[o] == 'with':
        o=o+1
        if input[o] == 'children':
            params['children'] = Listing.objects.IMMEDIATE
        elif input[o] == 'descendents':
            params['children'] = Listing.objects.ALL
        else:
            raise template.TemplateSyntaxError, "%r tag's argument 'with' required specification (with children|with descendents)" % input[0]
        o=o+1

    # as
    if input[o] == 'as':
        var_name = input[o+1]
    else:
        raise template.TemplateSyntaxError, "%r tag requires 'as' argument" % input[0]

    # unique
    if input[-2].lower() == 'unique':
        params['unique'] = input[-1]
        params_to_resolve.append('unique')
    elif input[-1].lower() == 'unique':
        params['unique'] = LISTING_UNIQUE_DEFAULT_SET
        params_to_resolve.append('unique')

    return var_name, params, params_to_resolve

class EmptyNode(template.Node):
    def render(self, context):
        return u''

class ObjectNotFoundOrInvalid(Exception): pass

class BoxNode(template.Node):

    def __init__(self, box_type, nodelist, model=None, lookup=None, var_name=None):
        self.box_type, self.nodelist, self.var_name, self.lookup, self.model = box_type, nodelist, var_name, lookup, model

    def get_obj(self, context=None):
        if self.model and self.lookup:
            if context:
                try:
                    lookup_val = template.Variable(self.lookup[1]).resolve(context)
                except template.VariableDoesNotExist:
                    lookup_val = self.lookup[1]
            else:
                lookup_val = self.lookup[1]

            try:
                obj = get_cached_object(self.model, **{self.lookup[0] : lookup_val})
            except models.ObjectDoesNotExist, e:
                log.error('BoxNode: %s (%s : %s)' % (str(e), self.lookup[0], lookup_val))
                raise ObjectNotFoundOrInvalid()
            except AssertionError, e:
                log.error('BoxNode: %s (%s : %s)' % (str(e), self.lookup[0], lookup_val))
                raise ObjectNotFoundOrInvalid()
        else:
            if not context:
                raise ObjectNotFoundOrInvalid()
            try:
                obj = template.Variable(self.var_name).resolve(context)
            except template.VariableDoesNotExist, e:
                log.error('BoxNode: Template variable does not exist. var_name=%s' % self.var_name)
                raise ObjectNotFoundOrInvalid()
        return obj

    def render(self, context):

        try:
            obj = self.get_obj()
        except ObjectNotFoundOrInvalid, e:
            return ''

        box = getattr(obj, 'box_class', Box)(obj, self.box_type, self.nodelist)

        if not box or not box.obj:
            log.warning('BoxNode: Box does not exists.')
            return ''

        # render the box itself
        box.prepare(context)
        # set the name of this box so that its children can pick up the dependencies
        box_key = box.get_cache_key()

        # push context stack
        context.push()
        context[BOX_INFO] = box_key

        # render the box
        result = box.render()
        # restore the context
        context.pop()

        # record parent box dependecy on child box or cached full-page on box
        if not (DOUBLE_RENDER and box.can_double_render) and (BOX_INFO in context or ECACHE_INFO in context):
            if BOX_INFO in context:
                source_key = context[BOX_INFO]
            elif ECACHE_INFO in context:
                source_key = context[ECACHE_INFO]
            CACHE_DELETER.register_dependency(source_key, box_key)

        return result

@register.tag('box')
def do_box(parser, token):
    """
    Tag Node representing our idea of a reusable box. It can handle multiple paramters in its body, that can
    contain other django template. The boxing facility keeps track of box dependencies which allows it to invalidate
    the cache of a parent box when the box itself is being invalidated.

    The object is passed in context as ``object`` when rendering the box parameters.

    Usage::

        {% box BOXTYPE for APP_LABEL.MODEL_NAME with FIELD VALUE %}
        {% box BOXTYPE for var_name %}

    Examples::

        {% box home_listing for articles.article with slug "some-slug" %}{% endbox %}

        {% box home_listing for articles.article with pk object_id %}
            template_name : {{object.get_box_template}}
        {% endbox %}

        {% box home_listing for article %}{% endbox %}
    """
    bits = token.split_contents()

    nodelist = parser.parse(('end' + bits[0],))
    parser.delete_first_token()
    return _parse_box(nodelist, bits)

def _parse_box(nodelist, bits):
    # {% box BOXTYPE for var_name %}                {% box BOXTYPE for content.type with PK_FIELD PK_VALUE %}
    if (len(bits) != 4 or bits[2] != 'for') and (len(bits) != 7 or bits[2] != 'for' or bits[4] != 'with'):
        raise template.TemplateSyntaxError, "{% box BOXTYPE for content.type with FIELD VALUE %} or {% box BOXTYPE for var_name %}"

    if len(bits) == 4:
        # var_name
        return BoxNode(bits[1], nodelist, var_name=bits[3])
    else:
        model = models.get_model(*bits[3].split('.'))
        if model is None:
            return EmptyNode()

        return BoxNode(bits[1], nodelist, model=model, lookup=(smart_str(bits[5]), bits[6]))

class RenderNode(template.Node):
    def __init__(self, var):
        self.var = template.Variable(var)

    def render(self, context):
        try:
            text = self.var.resolve(context)
        except template.VariableDoesNotExist:
            return ''

        return template.Template(text).render(context)

@register.tag('render')
def do_render(parser, token):
    """
    {% render some_var %}
    """
    bits = token.split_contents()

    if len(bits) != 2:
        raise template.TemplateSyntaxError()

    return RenderNode(bits[1])

@register.filter
@stringfilter
def ipblur(text): # brutalizer ;-)
    """ blurs IP address  """
    import re
    m = re.match(r'^(\d{1,3}\.\d{1,3}\.\d{1,3}\.)\d{1,3}.*', text)
    if not m:
        return text
    return '%sxxx' % m.group(1)

@register.filter
@stringfilter
def emailblur(email):
    "Obfuscates e-mail addresses - only @ and dot"
    return mark_safe(email.replace('@', '&#64;').replace('.', '&#46;'))

