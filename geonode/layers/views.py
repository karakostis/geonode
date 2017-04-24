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

import os
import re
import sys
import csv
import logging
import shutil
import traceback
import requests
import psycopg2
from osgeo import ogr
from unidecode import unidecode
from owslib.wfs import WebFeatureService
from guardian.shortcuts import get_perms
from geoserver.catalog import Catalog


from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.urlresolvers import reverse
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import render_to_response
from django.conf import settings
from django.template import Context, RequestContext
from django.template.loader import get_template
from django.utils.translation import ugettext as _
from django.utils import simplejson as json
from django.utils.safestring import mark_safe
from django.utils.html import escape
from django.template.defaultfilters import slugify
from django.forms.models import inlineformset_factory
from django.db.models import F
from django.forms.util import ErrorList

from geonode.tasks.deletion import delete_layer
from geonode.services.models import Service
from geonode.layers.forms import LayerForm, LayerUploadForm, NewLayerUploadForm, LayerAttributeForm
from geonode.base.forms import CategoryForm
from geonode.layers.models import Layer, Attribute, UploadSession
from geonode.base.enumerations import CHARSETS
from geonode.base.models import TopicCategory


from geonode.utils import default_map_config
from geonode.utils import GXPLayer
from geonode.utils import GXPMap
from geonode.layers.utils import file_upload, is_raster, is_vector, process_csv_file, create_empty_layer
from geonode.utils import resolve_object, llbbox_to_mercator
from geonode.people.forms import ProfileForm, PocForm
from geonode.layers.forms import UploadCSVForm, UploadEmptyLayerForm

from geonode.security.views import _perms_info_json
from geonode.documents.models import get_related_documents
from geonode.utils import build_social_links
from geonode.geoserver.helpers import gs_slurp
from geonode.geoserver.signals import geoserver_post_save


CONTEXT_LOG_FILE = None

if 'geonode.geoserver' in settings.INSTALLED_APPS:
    from geonode.geoserver.helpers import _render_thumbnail
    from geonode.geoserver.helpers import ogc_server_settings
    CONTEXT_LOG_FILE = ogc_server_settings.LOG_FILE

logger = logging.getLogger("geonode.layers.views")

DEFAULT_SEARCH_BATCH_SIZE = 10
MAX_SEARCH_BATCH_SIZE = 25
GENERIC_UPLOAD_ERROR = _("There was an error while attempting to upload your data. \
Please try again, or contact and administrator if the problem continues.")

_PERMISSION_MSG_DELETE = _("You are not permitted to delete this layer")
_PERMISSION_MSG_GENERIC = _('You do not have permissions for this layer.')
_PERMISSION_MSG_MODIFY = _("You are not permitted to modify this layer")
_PERMISSION_MSG_METADATA = _(
    "You are not permitted to modify this layer's metadata")
_PERMISSION_MSG_VIEW = _("You are not permitted to view this layer")


def log_snippet(log_file):
    if not os.path.isfile(log_file):
        return "No log file at %s" % log_file

    with open(log_file, "r") as f:
        f.seek(0, 2)  # Seek @ EOF
        fsize = f.tell()  # Get Size
        f.seek(max(fsize - 10024, 0), 0)  # Set pos @ last n chars
        return f.read()


def _resolve_layer(request, typename, permission='base.view_resourcebase',
                   msg=_PERMISSION_MSG_GENERIC, **kwargs):
    """
    Resolve the layer by the provided typename (which may include service name) and check the optional permission.
    """
    service_typename = typename.split(":", 1)

    if Service.objects.filter(name=service_typename[0]).exists():
        service = Service.objects.filter(name=service_typename[0])
        return resolve_object(request,
                              Layer,
                              {'service': service[0],
                               'typename': service_typename[1] if service[0].method != "C" else typename},
                              permission=permission,
                              permission_msg=msg,
                              **kwargs)
    else:
        return resolve_object(request,
                              Layer,
                              {'typename': typename,
                               'service': None},
                              permission=permission,
                              permission_msg=msg,
                              **kwargs)


# Basic Layer Views #

@login_required
def layer_upload(request, template='upload/layer_upload.html'):

    if request.method == 'GET':

        ctx = {
            'charsets': CHARSETS,
            'is_layer': True,
        }

        #category_form = CategoryForm(prefix="category_choice_field", initial=None)
        #return render_to_response(template, {"category_form": category_form}, RequestContext(request, ctx))
        return render_to_response(template, RequestContext(request, ctx))
    elif request.method == 'POST':
        form = NewLayerUploadForm(request.POST, request.FILES)
        tempdir = None
        errormsgs = []
        out = {'success': False}
        if form.is_valid():
            title = form.cleaned_data["layer_title"]

            # Replace dots in filename - GeoServer REST API upload bug
            # and avoid any other invalid characters.
            # Use the title if possible, otherwise default to the filename
            if title is not None and len(title) > 0:
                name_base = title
            else:
                name_base, __ = os.path.splitext(
                    form.cleaned_data["base_file"].name)
            name = slugify(name_base.replace(".", "_"))

            try:
                # Moved this inside the try/except block because it can raise
                # exceptions when unicode characters are present.
                # This should be followed up in upstream Django.
                tempdir, base_file = form.write_files()
                print ("base_file", base_file)

                #topic_id = request.POST['category']
                #topic_category = TopicCategory.objects.get(
                #    id=topic_id
                #)
                saved_layer = file_upload(
                    base_file,
                    name=name,
                    user=request.user,
                    overwrite=False,
                    charset=form.cleaned_data["charset"],
                    abstract=form.cleaned_data["abstract"],
                    title=form.cleaned_data["layer_title"]  #,
                    # category=topic_category.identifier
                )
                print ("saved_layer", saved_layer)
            except Exception as e:
                exception_type, error, tb = sys.exc_info()
                logger.exception(e)
                out['success'] = False
                out['errors'] = str(error)
                # Assign the error message to the latest UploadSession from that user.
                latest_uploads = UploadSession.objects.filter(user=request.user).order_by('-date')
                if latest_uploads.count() > 0:
                    upload_session = latest_uploads[0]
                    upload_session.error = str(error)
                    upload_session.traceback = traceback.format_exc(tb)
                    upload_session.context = log_snippet(CONTEXT_LOG_FILE)
                    upload_session.save()
                    out['traceback'] = upload_session.traceback
                    out['context'] = upload_session.context
                    out['upload_session'] = upload_session.id
            else:
                out['success'] = True
                if hasattr(saved_layer, 'info'):
                    out['info'] = saved_layer.info
                out['url'] = reverse(
                    'layer_detail', args=[
                        saved_layer.service_typename])
                upload_session = saved_layer.upload_session
                upload_session.processed = True
                upload_session.save()
                permissions = form.cleaned_data["permissions"]
                if permissions is not None and len(permissions.keys()) > 0:
                    saved_layer.set_permissions(permissions)
                print ("permissions", permissions)
            finally:
                if tempdir is not None:
                    print ("delete tempdir")
                    shutil.rmtree(tempdir)
        else:
            for e in form.errors.values():
                errormsgs.extend([escape(v) for v in e])
            out['errors'] = form.errors
            out['errormsgs'] = errormsgs
        if out['success']:
            status_code = 200
        else:
            status_code = 400
        return HttpResponse(
            json.dumps(out),
            mimetype='application/json',
            status=status_code)

def layer_detail(request, layername, template='layers/layer_detail.html'):
    layer = _resolve_layer(
        request,
        layername,
        'base.view_resourcebase',
        _PERMISSION_MSG_VIEW)

    # assert False, str(layer_bbox)
    config = layer.attribute_config()
    # Add required parameters for GXP lazy-loading
    layer_bbox = layer.bbox
    bbox = [float(coord) for coord in list(layer_bbox[0:4])]

    config["srs"] = getattr(settings, 'DEFAULT_MAP_CRS', 'EPSG:900913')
    config["bbox"] = bbox if config["srs"] != 'EPSG:900913' \
        else llbbox_to_mercator([float(coord) for coord in bbox])
    config["title"] = layer.title
    config["queryable"] = True
    config["tiled"] = False


    if layer.storeType == "remoteStore":
        service = layer.service
        source_params = {
            "ptype": service.ptype,
            "remote": True,
            "url": service.base_url,
            "name": service.name}
        maplayer = GXPLayer(
            name=layer.typename,
            ows_url=layer.ows_url,
            layer_params=json.dumps(config),
            source_params=json.dumps(source_params))
    else:
        maplayer = GXPLayer(
            name=layer.typename,
            ows_url=layer.ows_url,
            layer_params=json.dumps(config))

    # build WMS URL link
    wms_url = "{ows_url}/?SERVICE=WMS&REQUEST=GetMap&VERSION=1.1.0&LAYERS={layername}&STYLES=&FORMAT=image/png&HEIGHT=256&WIDTH=256&BBOX={bbox_0},{bbox_1},{bbox_2},{bbox_3}".format(** {
        'ows_url': layer.ows_url,
        'layername': layername,
        'bbox_0': bbox[0],
        'bbox_1': bbox[1],
        'bbox_2': bbox[2],
        'bbox_3': bbox[3],
    })


    # Update count for popularity ranking,
    # but do not includes admins or resource owners
    if request.user != layer.owner and not request.user.is_superuser:
        Layer.objects.filter(
            id=layer.id).update(popular_count=F('popular_count') + 1)

    # center/zoom don't matter; the viewer will center on the layer bounds
    map_obj = GXPMap(projection=getattr(settings, 'DEFAULT_MAP_CRS', 'EPSG:900913'))

    NON_WMS_BASE_LAYERS = [
        la for la in default_map_config()[1] if la.ows_url is None]

    metadata = layer.link_set.metadata().filter(
        name__in=settings.DOWNLOAD_FORMATS_METADATA)

    context_dict = {
        "resource": layer,
        'perms_list': get_perms(request.user, layer.get_self_resource()),
        "permissions_json": _perms_info_json(layer),
        "documents": get_related_documents(layer),
        "metadata": metadata,
        "is_layer": True,
        "wps_enabled": settings.OGC_SERVER['default']['WPS_ENABLED'],
        "wms_url": wms_url,
        "site_url": settings.SITEURL,
        "layername": layername,
    }

    context_dict["viewer"] = json.dumps(
        map_obj.viewer_json(request.user, * (NON_WMS_BASE_LAYERS + [maplayer])))
    context_dict["preview"] = getattr(
        settings,
        'LAYER_PREVIEW_LIBRARY',
        'leaflet')

    if request.user.has_perm('download_resourcebase', layer.get_self_resource()):
        if layer.storeType == 'dataStore' or layer.storeType == 'remoteStore': # assumes that all layers from remoteStore are vector layers
            links = layer.link_set.download().filter(
                name__in=settings.DOWNLOAD_FORMATS_VECTOR)
        else:
            links = layer.link_set.download().filter(
                name__in=settings.DOWNLOAD_FORMATS_RASTER)
        context_dict["links"] = links

    if settings.SOCIAL_ORIGINS:
        context_dict["social_links"] = build_social_links(request, layer)

    layers_names = layer.typename

    try:
        if 'geonode' in layers_names:
            workspace, name = layers_names.split(':', 1)
            print ("tutto bene")
            print ("workspace", workspace)
            print ("layers_names", layers_names)
        else:
            #workspace = "arc"
            workspace = ""
            name = layers_names
            print ("workspace", workspace)
            print ("layers_names", layers_names)
    except:
        print "Can not identify workspace type and layername"

    context_dict["layer_name"] = json.dumps(layers_names)

    try:
        # get type of layer (raster or vector)
        cat = Catalog(settings.OGC_SERVER['default']['LOCATION'] + "rest", settings.OGC_SERVER['default']['USER'], settings.OGC_SERVER['default']['PASSWORD'])
        resource = cat.get_resource(name, workspace=workspace)

        if (type(resource).__name__ == 'Coverage'):
            context_dict["layer_type"] = "raster"
        elif (type(resource).__name__ == 'FeatureType'):
            context_dict["layer_type"] = "vector"

            # get layer's attributes with display_order gt 0
            attr_to_display = layer.attribute_set.filter(display_order__gt=0)

            layers_attributes = []
            for values in attr_to_display.values('attribute'):
                layers_attributes.append(values['attribute'])

            location = "{location}{service}".format(** {
                'location': settings.OGC_SERVER['default']['LOCATION'],
                'service': 'wms',
            })

            # get schema for specific layer
            from owslib.feature.schema import get_schema
            username = settings.OGC_SERVER['default']['USER']
            password = settings.OGC_SERVER['default']['PASSWORD']
            schema = get_schema(location, name, username=username, password=password)

            # get the name of the column which holds the geometry
            #geomName = schema.keys()[schema.values().index('Point')] or schema.keys()[schema.values().index('MultiLineString')]
            #print ("geomName", geomName)

            if 'the_geom' in schema['properties']:
                schema['properties'].pop('the_geom', None)
            elif 'geom' in schema['properties']:
                schema['properties'].pop("geom", None)

            # filter the schema dict based on the values of layers_attributes
            layer_attributes_schema = []
            for key in schema['properties'].keys():
                if key in layers_attributes:
                    layer_attributes_schema.append(key)
                else:
                    schema['properties'].pop(key, None)

            filtered_attributes = list(set(layers_attributes).intersection(layer_attributes_schema))
            context_dict["schema"] = schema
            context_dict["filtered_attributes"] = filtered_attributes

    except:
        print "Possible error with OWSLib. Turning all available properties to string"


    return render_to_response(template, RequestContext(request, context_dict))


# Loads the data using the OWS lib when the "Do you want to filter it" button is clicked.
def load_layer_data(request, template='layers/layer_detail.html'):

    import time
    start_time = time.time()
    context_dict = {}
    data_dict = json.loads(request.POST.get('json_data'))
    layername = data_dict['layer_name']
    filtered_attributes = data_dict['filtered_attributes']
    workspace, name = layername.split(':')
    location = "{location}{service}".format(** {
        'location': settings.OGC_SERVER['default']['LOCATION'],
        'service': 'wms',
    })

    try:
        username = settings.OGC_SERVER['default']['USER']
        password = settings.OGC_SERVER['default']['PASSWORD']
        wfs = WebFeatureService(location, version='1.1.0', username=username, password=password)

        response = wfs.getfeature(typename=name, propertyname=filtered_attributes, outputFormat='application/json')

        x = response.read()
        x = json.loads(x)
        features_response = json.dumps(x)
        decoded = json.loads(features_response)
        decoded_features = decoded['features']


        properties = {}
        for key in decoded_features[0]['properties']:
            properties[key] = []

        # loop the dictionary based on the values on the list and add the properties
        # in the dictionary (if doesn't exist) together with the value

        for i in range(len(decoded_features)):
            for key, value in decoded_features[i]['properties'].iteritems():
                if value != '' and isinstance(value, (str, int, float)):
                    properties[key].append(value)

        for key in properties:
            properties[key] = list(set(properties[key]))
            properties[key].sort()

        context_dict["feature_properties"] = properties
        print "OWSLib worked as expected"

    except:
        print "Possible error with OWSLib. Turning all available properties to string"
    print("--- %s seconds ---" % (time.time() - start_time))
    return HttpResponse(json.dumps(context_dict), mimetype="application/json")



@login_required
def layer_metadata(request, layername, template='layers/layer_metadata.html'):
    layer = _resolve_layer(
        request,
        layername,
        'base.change_resourcebase_metadata',
        _PERMISSION_MSG_METADATA)
    layer_attribute_set = inlineformset_factory(
        Layer,
        Attribute,
        extra=0,
        form=LayerAttributeForm,
    )
    topic_category = layer.category

    poc = layer.poc
    metadata_author = layer.metadata_author
    if request.method == "POST":
        layer_form = LayerForm(request.POST, instance=layer, prefix="resource")
        attribute_form = layer_attribute_set(
            request.POST,
            instance=layer,
            prefix="layer_attribute_set",
            queryset=Attribute.objects.order_by('display_order'))
        category_form = CategoryForm(
            request.POST,
            prefix="category_choice_field",
            initial=int(
                request.POST["category_choice_field"]) if "category_choice_field" in request.POST else None)

    else:
        layer_form = LayerForm(instance=layer, prefix="resource")
        attribute_form = layer_attribute_set(
            instance=layer,
            prefix="layer_attribute_set",
            queryset=Attribute.objects.order_by('display_order'))
        category_form = CategoryForm(
            prefix="category_choice_field",
            initial=topic_category.id if topic_category else None)

    if request.method == "POST" and layer_form.is_valid(
    ) and attribute_form.is_valid() and category_form.is_valid():

        new_poc = layer_form.cleaned_data['poc']
        new_author = layer_form.cleaned_data['metadata_author']
        new_keywords = layer_form.cleaned_data['keywords']

        if new_poc is None:
            if poc is None:
                poc_form = ProfileForm(
                    request.POST,
                    prefix="poc",
                    instance=poc)
            else:
                poc_form = ProfileForm(request.POST, prefix="poc")
            if poc_form.is_valid():
                if len(poc_form.cleaned_data['profile']) == 0:
                    # FIXME use form.add_error in django > 1.7
                    errors = poc_form._errors.setdefault('profile', ErrorList())
                    errors.append(_('You must set a point of contact for this resource'))
                    poc = None
            if poc_form.has_changed and poc_form.is_valid():
                new_poc = poc_form.save()

        if new_author is None:
            if metadata_author is None:
                author_form = ProfileForm(request.POST, prefix="author",
                                          instance=metadata_author)
            else:
                author_form = ProfileForm(request.POST, prefix="author")
            if author_form.is_valid():
                if len(author_form.cleaned_data['profile']) == 0:
                    # FIXME use form.add_error in django > 1.7
                    errors = author_form._errors.setdefault('profile', ErrorList())
                    errors.append(_('You must set an author for this resource'))
                    metadata_author = None
            if author_form.has_changed and author_form.is_valid():
                new_author = author_form.save()

        new_category = TopicCategory.objects.get(
            id=category_form.cleaned_data['category_choice_field'])

        for form in attribute_form.cleaned_data:
            la = Attribute.objects.get(id=int(form['id'].id))
            la.description = form["description"]
            la.attribute_label = form["attribute_label"]
            la.visible = form["visible"]
            la.display_order = form["display_order"]
            la.save()

        if new_poc is not None and new_author is not None:
            new_keywords = layer_form.cleaned_data['keywords']
            layer.keywords.clear()
            layer.keywords.add(*new_keywords)
            the_layer = layer_form.save()

            up_sessions = UploadSession.objects.filter(layer=the_layer.id)
            if up_sessions.count() > 0 and up_sessions[0].user != the_layer.owner:
                up_sessions.update(user=the_layer.owner)
            the_layer.poc = new_poc
            the_layer.metadata_author = new_author
            Layer.objects.filter(id=the_layer.id).update(
                category=new_category
                )

            if getattr(settings, 'SLACK_ENABLED', False):
                try:
                    from geonode.contrib.slack.utils import build_slack_message_layer, send_slack_messages
                    send_slack_messages(build_slack_message_layer("layer_edit", the_layer))
                except:
                    print "Could not send slack message."

            return HttpResponseRedirect(
                reverse(
                    'layer_detail',
                    args=(
                        layer.service_typename,
                    )))

    if poc is not None:
        layer_form.fields['poc'].initial = poc.id
        poc_form = ProfileForm(prefix="poc")
        poc_form.hidden = True

    if metadata_author is not None:
        layer_form.fields['metadata_author'].initial = metadata_author.id
        author_form = ProfileForm(prefix="author")
        author_form.hidden = True

    return render_to_response(template, RequestContext(request, {
        "layer": layer,
        "layer_form": layer_form,
        "poc_form": poc_form,
        "author_form": author_form,
        "attribute_form": attribute_form,
        "category_form": category_form,
    }))


@login_required
def layer_change_poc(request, ids, template='layers/layer_change_poc.html'):
    layers = Layer.objects.filter(id__in=ids.split('_'))
    if request.method == 'POST':
        form = PocForm(request.POST)
        if form.is_valid():
            for layer in layers:
                layer.poc = form.cleaned_data['contact']
                layer.save()
            # Process the data in form.cleaned_data
            # ...
            # Redirect after POST
            return HttpResponseRedirect('/admin/maps/layer')
    else:
        form = PocForm()  # An unbound form
    return render_to_response(
        template, RequestContext(
            request, {
                'layers': layers, 'form': form}))


@login_required
def layer_replace(request, layername, template='layers/layer_replace.html'):
    layer = _resolve_layer(
        request,
        layername,
        'base.change_resourcebase',
        _PERMISSION_MSG_MODIFY)

    if request.method == 'GET':
        ctx = {
            'charsets': CHARSETS,
            'layer': layer,
            'is_featuretype': layer.is_vector(),
            'is_layer': True,
        }
        return render_to_response(template,
                                  RequestContext(request, ctx))
    elif request.method == 'POST':

        form = LayerUploadForm(request.POST, request.FILES)
        tempdir = None
        out = {}

        if form.is_valid():

            try:
                tempdir, base_file = form.write_files()

                if layer.is_vector() and is_raster(base_file):
                    out['success'] = False
                    out['errors'] = _("You are attempting to replace a vector layer with a raster.")
                elif (not layer.is_vector()) and is_vector(base_file):
                    out['success'] = False
                    out['errors'] = _("You are attempting to replace a raster layer with a vector.")
                else:
                    layers_names = layer.typename
                    workspace, name = layers_names.split(':')

                    constr = "dbname='{dbname}' user='{user}' host='{host}' password='{password}'".format(** {
                        'dbname': settings.DATABASES['uploaded']['NAME'],
                        'user': settings.DATABASES['uploaded']['USER'],
                        'host': settings.DATABASES['uploaded']['HOST'],
                        'password': settings.DATABASES['uploaded']['PASSWORD']
                    })

                    conn = psycopg2.connect(constr)
                    cur = conn.cursor()

                    sqlstr = "SELECT EXISTS(SELECT * FROM information_schema.tables WHERE table_name='{table}');".format(** {
                        'table': name
                    })
                    cur.execute(sqlstr)
                    exists = cur.fetchone()[0]

                    # if true use psycopg2 and ogr2ogr to replace the content of the table
                    if(exists):

                        geometry_dict = {  # geometry_shape:geometry_table
                            'POLYGON': 'MULTIPOLYGON',
                            'LINESTRING': 'MULTILINESTRING',
                            'POINT': 'POINT'
                        }

                        # get geometry of shapefile
                        shapefile = ogr.Open(base_file)
                        layer_shape = shapefile.GetLayer(0)
                        feature_shape = layer_shape.GetFeature(0)
                        geometry_shape_ref = feature_shape.GetGeometryRef()
                        geometry_shape = geometry_shape_ref.GetGeometryName()

                        sqlstr = "SELECT type FROM geometry_columns WHERE f_table_schema = 'public' AND f_table_name = '{table}' AND f_geometry_column = 'the_geom';".format(** {
                            'table': name
                        })
                        cur.execute(sqlstr)
                        geometry_type = cur.fetchone()[0]

                        match_geom = False
                        for key, value in geometry_dict.iteritems():
                            if((key == geometry_shape) and (value == geometry_type)):
                                match_geom = True
                                break

                        if match_geom:

                            sqlstr = 'DELETE FROM "{table}";'.format(** {
                                'table': name
                            })
                            cur.execute(sqlstr)
                            conn.commit()  # psycopg2 needs to commit to delete features

                            sqlstr = "SELECT Find_SRID('public', '{table}', 'the_geom');".format(**{
                                'table': name
                            })
                            cur.execute(sqlstr)
                            srid = cur.fetchone()[0]

                            sqlstr = 'ogr2ogr -append -preserve_fid -f "PostgreSQL" -t_srs "EPSG:{srid}" PG:"host={host} user={user} dbname={dbname} password={password}" -nln "{table}" -nlt {geometry_type} "{shp}"'.format(** {
                                'srid': srid,
                                'shp': base_file,
                                'table': name,
                                'geometry_type': geometry_type,
                                'host': settings.DATABASES['uploaded']['HOST'],
                                'dbname': settings.DATABASES['uploaded']['NAME'],
                                'user': settings.DATABASES['uploaded']['USER'],
                                'password': settings.DATABASES['uploaded']['PASSWORD']
                            })
                            os.system(sqlstr)
                            out['success'] = True
                            out['url'] = reverse(
                                'layer_detail', args=[
                                    layer.service_typename])
                        else:
                            raise Exception('Table geometry does not match with shapefile geometry')
                    else:
                        raise Exception('Table does not exist in PostgreSQL')
            except Exception as e:
                out['success'] = False
                out['errors'] = str(e)
            finally:
                if tempdir is not None:
                    shutil.rmtree(tempdir)
        else:
            errormsgs = []
            for e in form.errors.values():
                errormsgs.append([escape(v) for v in e])

            out['errors'] = form.errors
            out['errormsgs'] = errormsgs

        if out['success']:
            status_code = 200
        else:
            status_code = 400
        return HttpResponse(
            json.dumps(out),
            mimetype='application/json',
            status=status_code)



@login_required
def layer_remove(request, layername, template='layers/layer_remove.html'):
    layer = _resolve_layer(
        request,
        layername,
        'base.delete_resourcebase',
        _PERMISSION_MSG_DELETE)

    if (request.method == 'GET'):
        return render_to_response(template, RequestContext(request, {
            "layer": layer
        }))
    if (request.method == 'POST'):
        try:
            delete_layer.delay(object_id=layer.id)
        except Exception as e:
            message = '{0}: {1}.'.format(_('Unable to delete layer'), layer.typename)

            if 'referenced by layer group' in getattr(e, 'message', ''):
                message = _('This layer is a member of a layer group, you must remove the layer from the group '
                            'before deleting.')

            messages.error(request, message)
            return render_to_response(template, RequestContext(request, {"layer": layer}))
        return HttpResponseRedirect(reverse("layer_browse"))
    else:
        return HttpResponse("Not allowed", status=403)


def layer_thumbnail(request, layername):
    if request.method == 'POST':
        layer_obj = _resolve_layer(request, layername)
        try:
            image = _render_thumbnail(request.body)

            if not image:
                return
            filename = "layer-%s-thumb.png" % layer_obj.uuid
            layer_obj.save_thumbnail(filename, image)

            return HttpResponse('Thumbnail saved')
        except:
            return HttpResponse(
                content='error saving thumbnail',
                status=500,
                mimetype='text/plain'
            )



@login_required
def layer_create(request, template='layers/layer_create.html'):

    if request.method == 'GET':
        ctx = {
            'charsets': CHARSETS,
            "is_layer": True,
        }

        # Get the values for the dropdown menus of regions and provinces
        constr = "dbname='{dbname}' user='{user}' host='{host}' password='{password}'".format(** {
            'dbname': settings.DATABASES['uploaded']['NAME'],
            'user': settings.DATABASES['uploaded']['USER'],
            'host': settings.DATABASES['uploaded']['HOST'],
            'password': settings.DATABASES['uploaded']['PASSWORD']
        })

        conn = psycopg2.connect(constr)
        cur = conn.cursor()

        sqlstr = "SELECT DISTINCT adm0_name FROM wld_bnd_adm0_gaul_2015 ORDER BY adm0_name;"
        cur.execute(sqlstr)
        countries = cur.fetchall()
        countries = [c[0] for c in countries]
        ctx['countries'] = countries

        form_csv_layer = UploadCSVForm()
        form_empty_layer = UploadEmptyLayerForm()
        ctx['form_csv_layer'] = form_csv_layer
        ctx['form_empty_layer'] = form_empty_layer
        return render_to_response(template, RequestContext(request, ctx))

    elif request.method == 'POST':

        # Get the values for the dropdown menus of regions and provinces
        ctx = {}
        constr = "dbname='{dbname}' user='{user}' host='{host}' password='{password}'".format(** {
            'dbname': settings.DATABASES['uploaded']['NAME'],
            'user': settings.DATABASES['uploaded']['USER'],
            'host': settings.DATABASES['uploaded']['HOST'],
            'password': settings.DATABASES['uploaded']['PASSWORD']
        })

        conn = psycopg2.connect(constr)
        cur = conn.cursor()

        sqlstr = "SELECT DISTINCT adm0_name FROM wld_bnd_adm0_gaul_2015 ORDER BY adm0_name;"
        cur.execute(sqlstr)
        countries = cur.fetchall()
        countries = [c[0] for c in countries]
        ctx['countries'] = countries

        if 'fromlayerbtn' in request.POST:
            the_user = request.user
            form_csv_layer = UploadCSVForm(request.POST, request.FILES)
            form_empty_layer = UploadEmptyLayerForm(request.POST, request.FILES)

            errormsgs = []
            ctx['success'] = False

            if form_csv_layer.is_valid():
                try:
                    title = form_csv_layer.cleaned_data["title"]
                    permissions = form_csv_layer.cleaned_data["permissions_json"]

                    layer_based_info = {
                        "1": {
                            "geom_table": "wld_bnd_adm0_gaul_2015 AS g",
                            "id": "adm0_code",
                            "columns": "g.adm0_code, g.adm0_name, g.the_geom",
                            "geom": "the_geom"
                            },
                        "2": {
                            "geom_table": "wld_bnd_adm1_gaul_2015 AS g",
                            "id": "adm1_code",
                            "columns": "g.adm0_code, g.adm0_name, g.adm1_code, g.adm1_name, g.the_geom",
                            "geom": "the_geom"
                            },
                        "3": {
                            "geom_table": "wld_bnd_adm2_gaul_2015 AS g",
                            "id": "adm2_code",
                            "columns": "g.adm0_code, g.adm0_name, g.adm1_code, g.adm1_name, g.adm2_code, g.adm2_name, g.the_geom",
                            "geom": "the_geom"
                            }
                    }

                    layer_type = form_csv_layer.cleaned_data["layer_type"]

                    geom_table_name = layer_based_info[layer_type[0]]['geom_table']
                    geom_table_id = layer_based_info[layer_type[0]]['id']
                    geom_table_geom = layer_based_info[layer_type[0]]['geom']
                    geom_table_columns = layer_based_info[layer_type[0]]['columns']
                    selected_country = form_csv_layer.cleaned_data["selected_country"]
                    cntr_name = slugify(selected_country[0].replace(" ", "_"))
                    slugified_title = slugify(title.replace(" ", "_"))
                    table_name_temp = "%s_%s_temp" % (cntr_name, slugified_title)
                    table_name = "%s_%s" % (cntr_name, slugified_title)
                    table_name_temp = table_name_temp
                    new_table = table_name

                    # Write CSV in the server
                    tempdir, absolute_base_file = form_csv_layer.write_files()
                    errormsgs_val, status_code = process_csv_file(absolute_base_file, table_name_temp, new_table, geom_table_name, geom_table_id, geom_table_columns, geom_table_geom)

                    if status_code == '400':
                        errormsgs.append(errormsgs_val)
                        ctx['errormsgs'] = errormsgs
                        return render_to_response(template, RequestContext(request, {'form_csv_layer': form_csv_layer, 'form_empty_layer': form_empty_layer, 'countries': countries, 'errormsgs': errormsgs, 'status_msg': json.dumps('400_csv'), "is_layer": True}))

                    # Create layer in geoserver
                    sld_style = 'polygon_style.sld'
                    _create_geoserver_geonode_layer(new_table, sld_style, title, the_user, permissions)

                    ctx['success'] = True

                except Exception as e:
                    ctx['success'] = False
                    ctx['errors'] = str(e)

                finally:
                    if tempdir is not None:
                        shutil.rmtree(tempdir)

                if ctx['success']:
                    status_code = 200
                    layer = 'geonode:' + new_table

                    return HttpResponseRedirect(
                        reverse(
                            'layer_metadata',
                            args=(
                                layer,
                            )))
            else:

                for e in form_csv_layer.errors.values():
                    errormsgs.append([escape(v) for v in e])

                ctx['errors'] = form_csv_layer.errors
                ctx['errormsgs'] = errormsgs
                ctx['success'] = False
                return render_to_response(template, RequestContext(request, {'form_csv_layer': form_csv_layer, 'form_empty_layer': form_empty_layer, 'countries': countries, 'status_msg': json.dumps('400_csv'), "is_layer": True}))


        elif 'emptylayerbtn' in request.POST:

            the_user = request.user
            ctx = {}
            form_csv_layer = UploadCSVForm(request.POST, request.FILES)
            form_empty_layer = UploadEmptyLayerForm(request.POST, extra=request.POST.get('total_input_fields'))

            errormsgs = []
            ctx['success'] = False

            if form_empty_layer.is_valid():

                field_types_info = {
                    "Integer": "integer",
                    "Character": "character varying(254)",
                    "Double": "double precision"
                }

                create_empty_layer_data = form_empty_layer.cleaned_data
                title = create_empty_layer_data['empty_layer_name']
                permissions = form_empty_layer.cleaned_data["permissions_json"]

                table_name = (create_empty_layer_data['empty_layer_name'].lower()).replace(" ", "_")
                # check table name for special characters
                if not re.match("^[\w\d_]+$", table_name) or table_name[0].isdigit():
                    status_code = '400'
                    errormsgs_val = "Not valid name for layer name. Use only characters or numbers for a name. Name can not start with a number."
                    errormsgs.append(errormsgs_val)
                    ctx['errormsgs'] = errormsgs
                    return render_to_response(template, RequestContext(request, {'form_csv_layer': form_csv_layer, 'form_empty_layer': form_empty_layer, 'countries': countries, 'errormsgs': errormsgs, 'status_msg': json.dumps('400_empty_layer'), "is_layer": True}))

                table_geom = create_empty_layer_data['geom_type']

                table_fields_list = ['fid serial NOT NULL']

                create_empty_layer_data_lngth = (len(create_empty_layer_data) - 3)/2  # need only field names and types divided by 2
                # check if user has added at least one column
                if (int(create_empty_layer_data['total_input_fields']) < 1):
                    status_code = '400'
                    if status_code == '400':
                        errormsgs_val = "You haven't added any additional columns. At least one column is required."
                        errormsgs.append(errormsgs_val)
                        ctx['errormsgs'] = errormsgs
                        return render_to_response(template, RequestContext(request, {'form_csv_layer': form_csv_layer, 'form_empty_layer': form_empty_layer, 'countries': countries, 'errormsgs': errormsgs, 'status_msg': json.dumps('400_empty_layer'), "is_layer": True}))

                field_types = []
                for key in create_empty_layer_data:
                    for i in range(create_empty_layer_data_lngth):
                        if key.startswith("extra_field_%s" % i):

                            field_name = create_empty_layer_data['extra_field_%s' % i].replace(" ", "_")

                            # check if string has special characters
                            if not re.match("^[\w\d_]+$", field_name) or field_name[0].isdigit():
                                status_code = '400'
                                errormsgs_val = "Not valid naming for attributes. Use only characters or numbers for a name. Name can not start with a number."
                                errormsgs.append(errormsgs_val)
                                ctx['errormsgs'] = errormsgs
                                return render_to_response(template, RequestContext(request, {'form_csv_layer': form_csv_layer, 'form_empty_layer': form_empty_layer, 'countries': countries, 'errormsgs': errormsgs, 'status_msg': json.dumps('400_empty_layer'), "is_layer": True}))

                            field_type_short = create_empty_layer_data['field_type_%s' % i] # get field type for this field name

                            field_type = field_types_info[field_type_short] # build the complete field type

                            field_name_type = field_name + " " + field_type
                            field_types.append(field_name)
                            table_fields_list.append(field_name_type.lower())

                # check if there are duplicate columns
                if (len(field_types) != len(set(field_types))):
                    status_code = '400'
                    if status_code == '400':
                        errormsgs_val = "There are one or more columns with the same name."
                        errormsgs.append(errormsgs_val)
                        ctx['errormsgs'] = errormsgs
                        return render_to_response(template, RequestContext(request, {'form_csv_layer': form_csv_layer, 'form_empty_layer': form_empty_layer, 'countries': countries, 'errormsgs': errormsgs, 'status_msg': json.dumps('400_empty_layer'), "is_layer": True}))

                geom = "the_geom geometry(%s,4326)" % table_geom
                table_fields_list.append(geom)
                primary_key = "CONSTRAINT %s_pkey PRIMARY KEY (fid)" % table_name
                table_fields_list.append(primary_key)
                table_fields_list = ','.join(map(str, table_fields_list))

                # create table in postgis for empty_layer
                errormsgs_val, status_code = create_empty_layer(table_name, table_fields_list)

                if status_code == '400':
                    errormsgs.append(errormsgs_val)
                    ctx['errormsgs'] = errormsgs
                    return render_to_response(template, RequestContext(request, {'form_csv_layer': form_csv_layer, 'form_empty_layer': form_empty_layer, 'countries': countries, 'errormsgs': errormsgs, 'status_msg': json.dumps('400_empty_layer'), "is_layer": True}))


                available_sld_styles = {
                    'POINT': 'point_style.sld',
                    'MULTILINESTRING': 'line_style.sld',
                    'MULTIPOLYGON': 'polygon_style.sld',
                }
                sld_style = available_sld_styles[table_geom]
                # create geoserver and geonode layer
                _create_geoserver_geonode_layer(table_name, sld_style, title, the_user, permissions)

                ctx['success'] = True
                if ctx['success']:
                    status_code = 200
                    layer = 'geonode:' + table_name

                    return HttpResponseRedirect(
                        reverse(
                            'layer_metadata',
                            args=(
                                layer,
                            )))
            else:
                for e in form_empty_layer.errors.values():
                    errormsgs.append([escape(v) for v in e])

                ctx['errors'] = form_csv_layer.errors
                ctx['errormsgs'] = errormsgs
                ctx['success'] = False
                return render_to_response(template, RequestContext(request, {'form_csv_layer': form_csv_layer, 'form_empty_layer': form_empty_layer, 'countries': countries, 'status_msg': json.dumps('400_empty_layer'), "is_layer": True}))



def _create_geoserver_geonode_layer(new_table, sld_type, title, the_user, permissions):
    # Create the Layer in GeoServer from the table
    try:
        cat = Catalog(settings.OGC_SERVER['default']['LOCATION'] + "rest", settings.OGC_SERVER['default']['USER'], settings.OGC_SERVER['default']['PASSWORD'])
        ds = cat.get_store("uploaded")  # name of store in WFP-Geonode
        cat.publish_featuretype(new_table, ds, "EPSG:4326", srs="EPSG:4326")

        # changing the layer's title in the title set by the user
        resource = cat.get_resource(new_table, workspace="geonode")
        resource.title = title
        cat.save(resource)

    except Exception as e:

        msg = "Error creating GeoServer layer for %s: %s" % (new_table, str(e))
        print msg
        return None, msg

    # Create the Layer in GeoNode from the GeoServer Layer
    try:

        link_to_sld = "{location}styles/{sld_type}".format(** {
            'location': settings.OGC_SERVER['default']['LOCATION'],
            'sld_type': sld_type
        })

        r = requests.get(link_to_sld)
        sld = r.text
        sld = sld.replace("name_of_layer", new_table)  # "name_of_layer" is set in the predefined sld in geoserver (polygon_style, line_style, point_style)
        cat.create_style(new_table, sld, overwrite=True)
        style = cat.get_style(new_table)
        layer = cat.get_layer(new_table)
        layer.default_style = style
        cat.save(layer)
        gs_slurp(owner=the_user, filter=new_table)

        from geonode.base.models import ResourceBase
        layer = ResourceBase.objects.get(title=title)
        geoserver_post_save(layer, ResourceBase)

        # assign permissions for this layer
        permissions_dict = json.loads(permissions)  # needs to be dictionary
        if permissions_dict is not None and len(permissions_dict.keys()) > 0:
            layer.set_permissions(permissions_dict)


    except Exception as e:
        msg = "Error creating GeoNode layer for %s: %s" % (new_table, str(e))
        return None, msg

@login_required
def download_csv(request):

    if request.method == 'GET':
        corresponding_data = {
            "country": {
                "columns": "adm0_code,adm0_name",
                "table_name": "wld_bnd_adm0_gaul_2015"
            },
            "region": {
                "columns": "adm1_code,adm1_name",
                "table_name": "wld_bnd_adm1_gaul_2015",
                "column_1": "adm0_name"
            },
            "province": {
                "columns": "adm2_code,adm2_name",
                "table_name": "wld_bnd_adm2_gaul_2015",
                "column_1": "adm0_name"
            }
        }
        country = request.GET.get('country')
        btn = request.GET.get('btn')

        constr = "dbname='{dbname}' user='{user}' host='{host}' password='{password}'".format(** {
            'dbname': settings.DATABASES['uploaded']['NAME'],
            'user': settings.DATABASES['uploaded']['USER'],
            'host': settings.DATABASES['uploaded']['HOST'],
            'password': settings.DATABASES['uploaded']['PASSWORD']
        })

        conn = psycopg2.connect(constr)
        cur = conn.cursor()

        if (btn == "country"):
            sqlstr = "SELECT {columns} FROM {table} ORDER BY 2".format(** {
                'columns': corresponding_data[btn]["columns"],
                'table': corresponding_data[btn]["table_name"]
            })
        else:
            sqlstr = "SELECT {columns} FROM {table} WHERE {column_1} = '{country}' ORDER BY 2".format(** {
                'columns': corresponding_data[btn]["columns"],
                'country': country,
                'table': corresponding_data[btn]["table_name"],
                'column_1': corresponding_data[btn]["column_1"],
            })

        cur.execute(sqlstr)
        rows = cur.fetchall()

        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = "attachment; filename={file}".format(** {
            'file': corresponding_data[btn]["table_name"] + ".csv"
        })

        writer = csv.writer(response, dialect='excel')
        writer.writerow(tuple(corresponding_data[btn]["columns"].split(',')))

        for row in rows:
            field_1 = row[0]
            field_2 = unidecode(row[1]).encode(encoding='UTF-8')
            fields = [field_1, field_2]
            writer.writerows([fields])
        return response

@login_required
def layer_edit_data(request, layername, template='layers/layer_edit_data.html'):

    import time
    start_time = time.time()

    context_dict = {}
    layer = _resolve_layer(
        request,
        layername,
        'base.view_resourcebase',
        _PERMISSION_MSG_VIEW)

    layers_names = layer.typename
    workspace, name = layers_names.split(':')

    location = "{location}{service}".format(** {
        'location': settings.OGC_SERVER['default']['LOCATION'],
        'service': 'wms',
    })

    # get layer's attributes with display_order gt 0
    attr_to_display = layer.attribute_set.filter(display_order__gt=0)
    layers_attributes = []
    for values in attr_to_display.values('attribute'):
        layers_attributes.append(values['attribute'])

    username = settings.OGC_SERVER['default']['USER']
    password = settings.OGC_SERVER['default']['PASSWORD']

    wfs = WebFeatureService(location, version='1.1.0', username=username, password=password)

    from owslib.feature.schema import get_schema
    schema = get_schema(location, name, username=username, password=password)

    # acquire the geometry of layer - requires improvement
    geom_dict = {
        'Point': 'Point',
        'MultiPoint': 'Point',
        'MultiSurfacePropertyType': 'Polygon',
        'MultiPolygon': 'Polygon',
        'MultiLineString': 'Linestring'
    }
    geom_type = schema.get('geometry') or schema['properties'].get('the_geom')
    context_dict["layer_geom"] = json.dumps(geom_dict.get(geom_type, 'unknown'))
    schema.pop("geometry")
    # remove the_geom/geom parameter
    if 'the_geom' in schema['properties']:
        schema['properties'].pop('the_geom', None)

    # filter the schema dict based on the values of layers_attributes
    layer_attributes_schema = []
    for key in schema['properties'].keys():
        if key in layers_attributes:
            layer_attributes_schema.append(key)
        else:
            schema['properties'].pop(key, None)

    filtered_attributes = list(set(layers_attributes).intersection(layer_attributes_schema))

    # get the metadata description
    attribute_description = {}
    display_order_dict = {}
    for idx, value in enumerate(filtered_attributes):
        description = layer.attribute_set.values('description').filter(attribute=value)
        display_order = layer.attribute_set.values('display_order').filter(attribute=value)
        attribute_description[value] = description[0]['description']
        display_order_dict[value] = display_order[0]['display_order']

    context_dict["schema"] = schema

    response = wfs.getfeature(typename=name, propertyname=filtered_attributes, outputFormat='application/json')

    features_response = json.dumps(json.loads(response.read()))
    decoded = json.loads(features_response)
    decoded_features = decoded['features']

    # order the list and create ordered dictionary
    import operator
    display_order_list_sorted = sorted(display_order_dict.items(), key=operator.itemgetter(1))
    from collections import OrderedDict
    display_order_dict_sorted = OrderedDict(display_order_list_sorted)

    # display_order_dict_sorted = dict(display_order_list_sorted)
    context_dict["feature_properties"] = json.dumps(decoded_features)
    context_dict["attribute_description"] = json.dumps(attribute_description)
    context_dict["display_order_dict_sorted"] = json.dumps(display_order_dict_sorted)
    context_dict["resource"] = layer
    context_dict["layer_name"] = json.dumps(name)
    context_dict["name"] = name
    context_dict["url"] = json.dumps(settings.OGC_SERVER['default']['LOCATION'])
    context_dict["site_url"] = json.dumps(settings.SITEURL)
    context_dict["default_workspace"] = json.dumps(settings.DEFAULT_WORKSPACE)
    print("--- %s seconds ---" % (time.time() - start_time))
    return render_to_response(template, RequestContext(request, context_dict))



@login_required
def delete_edits(request, template='layers/layer_edit_data.html'):

    data_dict = json.loads(request.POST.get('json_data'))
    feature_id = data_dict['feature_id']
    layer_name = data_dict['layer_name']

    xml_path = "layers/wfs_delete_row.xml"
    xmlstr = get_template(xml_path).render(Context({
            'layer_name': layer_name,
            'feature_id': feature_id})).strip()

    url = settings.OGC_SERVER['default']['LOCATION'] + 'wfs'
    headers = {'Content-Type': 'application/xml'}  # set what your server accepts
    status_code = requests.post(url, data=xmlstr, headers=headers, auth=(settings.OGC_SERVER['default']['USER'], settings.OGC_SERVER['default']['PASSWORD'])).status_code

    if (status_code != 200):
        message = "Failed to delete row."
        success = False
        return HttpResponse(json.dumps({'success': success, 'message': message}), mimetype="application/json")
    else:
        message = "Row was deleted successfully."
        success = True
        return HttpResponse(json.dumps({'success': success, 'message': message}), mimetype="application/json")

    return HttpResponse(json.dumps({'success': success, 'message': message}), mimetype="application/json")



@login_required
def save_edits(request, template='layers/layer_edit_data.html'):

    data_dict = json.loads(request.POST.get('json_data'))

    feature_id = data_dict['feature_id']
    layer_name = data_dict['layer_name']
    data = data_dict['data']
    data = data.split(",")

    url = settings.OGC_SERVER['default']['LOCATION'] + 'wfs'
    property_element = ""
    # concatenate all the properties
    for i, val in enumerate(data):
        attribute, value = data[i].split("=")
        # xml string with property element
        property_element_1 = """<wfs:Property>
          <wfs:Name>{}</wfs:Name>
          <wfs:Value>{}</wfs:Value>
        </wfs:Property>\n""".format(attribute, value)
        property_element = property_element + property_element_1
    # build the update wfs-t request
    xml_path = "layers/wfs_edit_data.xml"
    xmlstr = get_template(xml_path).render(Context({
            'layer_name': layer_name,
            'feature_id': feature_id,
            'property_element': mark_safe(property_element)})).strip()

    headers = {'Content-Type': 'application/xml'}  # set what your server accepts

    status_code = requests.post(url, data=xmlstr, headers=headers, auth=(settings.OGC_SERVER['default']['USER'], settings.OGC_SERVER['default']['PASSWORD'])).status_code

    if (status_code != 200):
        message = "Failed to save edited data."
        success = False
        return HttpResponse(json.dumps({'success': success, 'message': message}), mimetype="application/json")
    else:
        message = "Edits were saved successfully."
        success = True
        return HttpResponse(json.dumps({'success': success, 'message': message}), mimetype="application/json")

@login_required
def save_geom_edits(request, template='layers/layer_edit_data.html'):

    data_dict = json.loads(request.POST.get('json_data'))
    feature_id = data_dict['feature_id']
    layer_name = data_dict['layer_name']
    coords = ' '.join(map(str, data_dict['coords']))

    full_layer_name = "geonode:" + layer_name
    layer = _resolve_layer(
        request,
        full_layer_name,
        'base.change_resourcebase_metadata',
        _PERMISSION_MSG_METADATA)

    store_name, geometry_clm = get_store_name(layer_name)
    xml_path = "layers/wfs_edit_point_geom.xml"
    xmlstr = get_template(xml_path).render(Context({
            'layer_name': layer_name,
            'coords': coords,
            'feature_id': feature_id,
            'geometry_clm': geometry_clm})).strip()

    url = settings.OGC_SERVER['default']['LOCATION'] + 'wfs'
    headers = {'Content-Type': 'application/xml'} # set what your server accepts
    status_code = requests.post(url, data=xmlstr, headers=headers, auth=(settings.OGC_SERVER['default']['USER'], settings.OGC_SERVER['default']['PASSWORD'])).status_code

    store_name, geometry_clm = get_store_name(layer_name)

    status_code_bbox, status_code_seed = update_bbox_and_seed(headers, layer_name, store_name)
    if (status_code != 200):
        message = "Error saving the geometry."
        success = False
        return HttpResponse(json.dumps({'success': success, 'message': message}), mimetype="application/json")
    else:
        message = "Edits were saved successfully."
        success = True
        update_bbox_in_CSW(layer, layer_name)
        return HttpResponse(json.dumps({'success': success,  'message': message}), mimetype="application/json")


@login_required
def save_added_row(request, template='layers/layer_edit_data.html'):

    data_dict = json.loads(request.POST.get('json_data'))
    feature_type = data_dict['feature_type']
    layer_name = data_dict['layer_name']
    data = data_dict['data']
    data = data.split(",")

    full_layer_name = "geonode:" + layer_name
    layer = _resolve_layer(
        request,
        full_layer_name,
        'base.change_resourcebase_metadata',
        _PERMISSION_MSG_METADATA)

    # concatenate all the properties
    property_element = ""
    for i, val in enumerate(data):
        attribute, value = data[i].split("=")
        if value == "":
            continue
        # xml string with property element
        property_element_1 = """<{}>{}</{}>\n\t\t""".format(attribute, value, attribute)
        property_element = property_element + property_element_1

    headers = {'Content-Type': 'application/xml'} # set what your server accepts

    # Make a Describe Feature request to get the correct link for the xmlns:geonode
    xml_path = "layers/wfs_describe_feature.xml"
    xmlstr = get_template(xml_path).render(Context({
            'layer_name': layer_name})).strip()
    url = settings.OGC_SERVER['default']['LOCATION'] + 'wfs'
    describe_feature_response = requests.post(url, data=xmlstr, headers=headers, auth=(settings.OGC_SERVER['default']['USER'], settings.OGC_SERVER['default']['PASSWORD'])).text

    from lxml import etree
    xml = bytes(bytearray(describe_feature_response, encoding='utf-8'))  # encode it and force the same encoder in the parser
    doc = etree.XML(xml)
    nsmap = {}
    for ns in doc.xpath('//namespace::*'):
        nsmap[ns[0]] = ns[1]
    if nsmap['geonode']:
        geonode_url = nsmap['geonode']

    # Prepare the WFS-T insert request depending on the geometry
    if feature_type == 'Point':
        coords = ','.join(map(str, data_dict['coords']))
        coords = coords.replace(",", " ")
        xml_path = "layers/wfs_add_new_point.xml"
    elif feature_type == 'LineString':
        coords = ','.join(map(str, data_dict['coords']))
        coords = re.sub('(,[^,]*),', r'\1 ', coords)
        xml_path = "layers/wfs_add_new_line.xml"
    elif feature_type == 'Polygon':
        coords = [item for sublist in data_dict['coords'] for item in sublist]
        coords = ','.join(map(str, coords))
        coords = coords.replace(",", " ")
        xml_path = "layers/wfs_add_new_polygon.xml"

    store_name, geometry_clm = get_store_name(layer_name)
    xmlstr = get_template(xml_path).render(Context({
            'geonode_url': geonode_url,
            'layer_name': layer_name,
            'coords': coords,
            'property_element': mark_safe(property_element),
            'geometry_clm': geometry_clm})).strip()

    url = settings.OGC_SERVER['default']['LOCATION'] + 'geonode/wfs'
    status_code = requests.post(url, data=xmlstr, headers=headers, auth=(settings.OGC_SERVER['default']['USER'], settings.OGC_SERVER['default']['PASSWORD'])).status_code

    store_name, geometry_clm = get_store_name(layer_name)

    status_code_bbox, status_code_seed = update_bbox_and_seed(headers, layer_name, store_name)
    if (status_code != 200):
        message = "Error adding data."
        success = False
        return HttpResponse(json.dumps({'success': success, 'message': message}), mimetype="application/json")
    else:
        message = "New data were added succesfully."
        success = True
        update_bbox_in_CSW(layer, layer_name)
        return HttpResponse(json.dumps({'success': success,  'message': message}), mimetype="application/json")

# Used to update the BBOX of geoserver and send a see request
# Takes as input the headers and the layer_name
# Returns status_code of each request
def update_bbox_and_seed(headers, layer_name, store_name):
    # Update the BBOX of layer in geoserver (use of recalculate)
    url = settings.OGC_SERVER['default']['LOCATION'] + "rest/workspaces/geonode/datastores/{store_name}/featuretypes/{layer_name}.xml?recalculate=nativebbox,latlonbbox".format(** {
        'store_name': store_name.strip(),
        'layer_name': layer_name
    })

    xmlstr = """<featureType><enabled>true</enabled></featureType>"""
    status_code_bbox = requests.put(url, headers=headers, data=xmlstr, auth=(settings.OGC_SERVER['default']['USER'], settings.OGC_SERVER['default']['PASSWORD'])).status_code

    # Seed the cache for this layer
    url = settings.OGC_SERVER['default']['LOCATION'] + "gwc/rest/seed/geonode:{layer_name}.xml".format(** {
        'layer_name': layer_name
    })
    xml_path = "layers/seedRequest_geom.xml"
    xmlstr = get_template(xml_path).render(Context({
            'workspace': 'geonode',
            'layer_name': layer_name
            }))
    status_code_seed = requests.post(url, data=xmlstr, headers=headers, auth=(settings.OGC_SERVER['default']['USER'], settings.OGC_SERVER['default']['PASSWORD'])).status_code
    return status_code_bbox, status_code_seed

# Update the values for BBOX in CSW with the values calculated in geoserver layer
def update_bbox_in_CSW(layer, layer_name):

    # Get the coords from geoserver layer and update the base_resourceBase table
    from geoserver.catalog import Catalog
    cat = Catalog(settings.OGC_SERVER['default']['LOCATION'] + "rest", settings.OGC_SERVER['default']['USER'], settings.OGC_SERVER['default']['PASSWORD'])
    resource = cat.get_resource(layer_name, workspace="geonode")
    # use bbox_to_wkt to convert the BBOX coords to the wkt format
    from geonode.utils import bbox_to_wkt
    r = bbox_to_wkt(resource.latlon_bbox[0], resource.latlon_bbox[1], resource.latlon_bbox[2], resource.latlon_bbox[3], "4326")
    csw_wkt_geometry = r.split(";", 1)[1]
    # update the base_resourceBase
    from geonode.base.models import ResourceBase
    resources = ResourceBase.objects.filter(pk=layer.id)
    resources.update(bbox_x0=resource.latlon_bbox[0], bbox_x1=resource.latlon_bbox[1], bbox_y0=resource.latlon_bbox[2], bbox_y1=resource.latlon_bbox[3], csw_wkt_geometry=csw_wkt_geometry)

    return csw_wkt_geometry

#  Returns the store name based on the workspace and the layer name
def get_store_name(layer_name):
    # get the name of the store
    cat = Catalog(settings.OGC_SERVER['default']['LOCATION'] + "rest", settings.OGC_SERVER['default']['USER'], settings.OGC_SERVER['default']['PASSWORD'])
    resource = cat.get_resource(layer_name, workspace='geonode')
    store_name = resource.store.name

    # select the name of the geometry column based on the store type
    if (store_name == "uploaded"):
        geometry_clm = "the_geom"
    else:
        geometry_clm = "shape"


    return store_name, geometry_clm
