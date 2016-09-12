# -*- coding: utf-8 -*-
#########################################################################
#
# Copyright (C) 2012 OpenPlans
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.
#
#########################################################################

from django.conf.urls import patterns, url
from django.conf import settings
from django.views.generic import TemplateView

js_info_dict = {
    'packages': ('geonode.layers',),
}

urlpatterns = patterns(
    'geonode.layers.views',
    url(r'^$', TemplateView.as_view(template_name='layers/layer_list.html'), name='layer_browse'),
    url(r'^upload$', 'layer_upload', name='layer_upload'),
    url(r'^create$', 'layer_create', name='layer_create'),
    url(r'^download_csv$', 'download_csv', name='download_csv'),
    url(r'^save_edits$', 'save_edits', name='save_edits'),
    url(r'^load_layer_data$', 'load_layer_data', name='load_layer_data'),
    url(r'^save_geom_edits$', 'save_geom_edits', name='save_geom_edits'),
    url(r'^save_added_row$', 'save_added_row', name='save_added_row'),
    url(r'^(?P<layername>[^/]*)$', 'layer_detail', name="layer_detail"),
    url(r'^(?P<layername>[^/]*)/edit_data$', 'layer_edit_data', name="layer_edit_data"),
    url(r'^(?P<layername>[^/]*)/metadata$', 'layer_metadata', name="layer_metadata"),
    url(r'^(?P<layername>[^/]*)/remove$', 'layer_remove', name="layer_remove"),
    url(r'^(?P<layername>[^/]*)/replace$', 'layer_replace', name="layer_replace"),
    url(r'^(?P<layername>[^/]*)/thumbnail$', 'layer_thumbnail', name='layer_thumbnail'),

    # url(r'^api/batch_permissions/?$', 'batch_permissions',
    #    name='batch_permssions'),
    # url(r'^api/batch_delete/?$', 'batch_delete', name='batch_delete'),
)

# -- Deprecated url routes for Geoserver authentication -- remove after GeoNode 2.1
# -- Use /gs/acls, gs/resolve_user/, gs/download instead
if 'geonode.geoserver' in settings.INSTALLED_APPS:
    urlpatterns = patterns('geonode.geoserver.views',
                           url(r'^acls/?$', 'layer_acls', name='layer_acls_dep'),
                           url(r'^resolve_user/?$', 'resolve_user', name='layer_resolve_user_dep'),
                           url(r'^download$', 'layer_batch_download', name='layer_batch_download_dep'),
                           ) + urlpatterns
