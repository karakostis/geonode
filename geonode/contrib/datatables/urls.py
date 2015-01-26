from django.conf.urls import patterns, url
from django.views.generic import TemplateView

js_info_dict = {
    'packages': ('geonode.contrib.datatables',),
}

urlpatterns = patterns('geonode.contrib.datatables.views',
                       url(r'^$', TemplateView.as_view(template_name='datatables/datatable_list.html'),
                           name='datatable_browse'),
                       url(r'^(?P<dtid>\d+)/?$', 'datatable_detail', name='datatable_detail'),
                       url(r'^(?P<dtid>\d+)/replace$', 'datatable_replace', name='datatable_replace'), 
                       url(r'^(?P<dtid>\d+)/remove$', 'datatable_remove', name="datatable_remove"),
                       url(r'^upload/?$', 'datatable_upload', name='datatable_upload'),
                       url(r'^(?P<dtid>\d+)/metadata$', 'datatable_metadata', name='datatable_metadata'),
                       )
