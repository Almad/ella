from django.conf import settings

def newman_media(request):
    """
    Inject NEWMAN_MEDIA_URL to template. Use NEWMAN_MEDIA_PREFIX value from
    settings, if not available, use MEDIA_URL + 'newman_media/' combination
    """
    uri = getattr(settings, 'NEWMAN_MEDIA_PREFIX', None)
    debug = settings.DEBUG
    if not uri:
        uri = getattr(settings, 'MEDIA_URL') + 'newman_media/'
    return {
        'NEWMAN_MEDIA_URL' : uri,
        'DJANGO_MEDIA_URL': getattr(settings, 'MEDIA_URL', ''),
        'DEBUG': settings.DEBUG
    }
