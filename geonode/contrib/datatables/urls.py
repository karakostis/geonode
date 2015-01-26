from django.conf.urls import patterns, url
from django.views.generic import TemplateView

js_info_dict = {
    'packages': ('geonode.contrib.datatables',),
}

urlpatterns = patterns('geonode.contrib.datatables.views',
                       url(r'^api/upload/?$', 'datatable_upload_api', name='datatable_upload_api'),
                       url(r'^api/join/?$', 'tablejoin_api', name='tablejoin_api'),
                       )
