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
import sys
import csv
import logging
import shutil
import traceback
import psycopg2
from osgeo import ogr
from owslib.wfs import WebFeatureService
from guardian.shortcuts import get_perms
from geoserver.catalog import Catalog


from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.urlresolvers import reverse
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import render_to_response
from django.conf import settings
from django.template import RequestContext
from django.utils.translation import ugettext as _
from django.utils import simplejson as json
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
from geonode.layers.utils import file_upload, is_raster, is_vector, process_csv_file
from geonode.utils import resolve_object, llbbox_to_mercator
from geonode.people.forms import ProfileForm, PocForm
from geonode.layers.forms import UploadCSVForm
from geonode.security.views import _perms_info_json
from geonode.documents.models import get_related_documents
from geonode.utils import build_social_links
from geonode.geoserver.helpers import cascading_delete, gs_catalog, gs_slurp
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
            finally:
                if tempdir is not None:
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
    config["title"] = 'layer.title'
    config["queryable"] = True

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
    }

    context_dict["viewer"] = json.dumps(
        map_obj.viewer_json(request.user, * (NON_WMS_BASE_LAYERS + [maplayer])))
    context_dict["preview"] = getattr(
        settings,
        'LAYER_PREVIEW_LIBRARY',
        'leaflet')

    if request.user.has_perm('download_resourcebase', layer.get_self_resource()):
        if layer.storeType == 'dataStore':
            links = layer.link_set.download().filter(
                name__in=settings.DOWNLOAD_FORMATS_VECTOR)
        else:
            links = layer.link_set.download().filter(
                name__in=settings.DOWNLOAD_FORMATS_RASTER)
        context_dict["links"] = links

    if settings.SOCIAL_ORIGINS:
        context_dict["social_links"] = build_social_links(request, layer)

    layers_names = layer.typename
    workspace, name = layers_names.split(':')

    location = "{location}{service}".format(** {
        'location': settings.OGC_SERVER['default']['LOCATION'],
        'service': 'wms',
    })

    try:
        wfs = WebFeatureService(location, version='1.1.0')
        schema = wfs.get_schema(name)

        if 'the_geom' in schema['properties']:
            schema['properties'].pop('the_geom', None)
        elif 'geom' in schema['properties']:
            schema['properties'].pop("geom", None)

        layer_properties = []
        for key in schema['properties'].keys():
            layer_properties.append(key)
        context_dict["schema"] = schema
        response = wfs.getfeature(typename=name, propertyname=layer_properties, outputFormat='application/json')

        features_response = json.dumps(json.loads(response.read()))
        decoded = json.loads(features_response)
        decoded_features = decoded['features']

        properties = {}
        for key in decoded_features[0]['properties']:
            properties[key] = []

        # loop the dictionary based on the values on the list and add the propertie
        # in the dictionary (if doesn't exist) together with the value

        for i in range(len(decoded_features)):
            for key, value in decoded_features[i]['properties'].iteritems():
                if (value not in properties[key] and value != '' and (isinstance(value, (str, int, float)))):
                    properties[key].append(value)


        context_dict["feature_properties"] = properties

        print "OWSLib worked as expected"
    except:
        print "Possible error with OWSLib. Turning all available properties to string"

    return render_to_response(template, RequestContext(request, context_dict))


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

        form = UploadCSVForm()
        ctx['form'] = form
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


        form = UploadCSVForm(request.POST, request.FILES)
        errormsgs = []
        ctx['success'] = False

        if form.is_valid():

            try:
                title = form.cleaned_data["title"]

                layer_based_info = {
                    "1": {
                        "wrld_table": "wld_bnd_adm0_gaul_2015",
                        "id": "adm0_code",
                        "columns": "wld_bnd_adm0_gaul_2015.adm0_code, wld_bnd_adm0_gaul_2015.adm0_name, wld_bnd_adm0_gaul_2015.wkb_geometry",
                        "geom": "wkb_geometry"
                        },
                    "2": {
                        "wrld_table": "wld_bnd_adm1_gaul_2015",
                        "id": "adm1_code",
                        "columns": "wld_bnd_adm1_gaul_2015.adm0_code, wld_bnd_adm1_gaul_2015.adm0_name, wld_bnd_adm1_gaul_2015.adm1_code, wld_bnd_adm1_gaul_2015.adm1_name, wld_bnd_adm1_gaul_2015.geom",
                        "geom": "geom"
                        },
                    "3": {
                        "wrld_table": "wld_bnd_adm2_gaul_2015",
                        "id": "adm2_code",
                        "columns": "wld_bnd_adm2_gaul_2015.adm0_code, wld_bnd_adm2_gaul_2015.adm0_name, wld_bnd_adm2_gaul_2015.adm1_code, wld_bnd_adm2_gaul_2015.adm1_name, wld_bnd_adm2_gaul_2015.adm2_code, wld_bnd_adm2_gaul_2015.adm2_name, wld_bnd_adm2_gaul_2015.geom",
                        "geom": "geom"
                        }
                }

                layer_type = form.cleaned_data["layer_type"]

                wrld_table_name = layer_based_info[layer_type[0]]['wrld_table']
                wrld_table_id = layer_based_info[layer_type[0]]['id']
                wrld_table_geom = layer_based_info[layer_type[0]]['geom']
                wrld_table_columns = layer_based_info[layer_type[0]]['columns']
                selected_country = form.cleaned_data["selected_country"]
                cntr_name = slugify(selected_country[0].replace(" ", "_"))
                table_name_temp = "%s_%s_temp" % (cntr_name, title)
                table_name = "%s_%s" % (cntr_name, title)
                table_name_temp = table_name_temp
                new_table = table_name

                # Write CSV in the server
                tempdir, absolute_base_file = form.write_files()

                errormsgs_val, status_code = process_csv_file(absolute_base_file, table_name_temp, new_table, wrld_table_name, wrld_table_id, wrld_table_columns, wrld_table_geom)

                if status_code == '400':
                    errormsgs.append(errormsgs_val)
                    ctx['errormsgs'] = errormsgs
                    return render_to_response(template, RequestContext(request, {'form': form, 'countries': countries, 'errormsgs': errormsgs}))


                # CREATE LAYER IN GEOSERVER AND IN GEONODE
                _create_geoserver_geonode_layer(new_table)

                ctx['success'] = True

            except Exception as e:
                ctx['success'] = False
                ctx['errors'] = str(e)

            finally:

                if tempdir is not None:
                    shutil.rmtree(tempdir)

            if ctx['success']:
                status_code = 200
                #template = '/layers/geonode:' + new_table + '/metadata'
                #print template
                layer = 'geonode:' + new_table
                #return HttpResponseRedirect(template)

                return HttpResponseRedirect(
                    reverse(
                        'layer_metadata',
                        args=(
                            layer,
                        )))

                #return render_to_response(template, RequestContext(request, {'form': form}))
        else:

            for e in form.errors.values():
                errormsgs.append([escape(v) for v in e])

            ctx['errors'] = form.errors
            ctx['errormsgs'] = errormsgs
            ctx['success'] = False
            return render_to_response(template, RequestContext(request, {'form': form, 'countries': countries}))


def _create_geoserver_geonode_layer(new_table):
    # Create the Layer in GeoServer from the table

    ## to be added: check if layer name already exists
    try:
        cat = Catalog(settings.OGC_SERVER['default']['LOCATION'] + "rest")
        workspace = cat.get_workspace(settings.DEFAULT_WORKSPACE)
        ds = cat.get_store("uploaded") # name of store in WFP-Geonode

        ds.connection_parameters.update(host=settings.DATABASES['uploaded']['HOST'], port=settings.DATABASES['uploaded']['PORT'], database=settings.DATABASES['uploaded']['NAME'], user=settings.DATABASES['uploaded']['USER'], passwd=settings.DATABASES['uploaded']['PASSWORD'], dbtype='postgis', schema='public')

        ft = cat.publish_featuretype(new_table, ds, "EPSG:4326", srs="EPSG:4326")

        print 'something'
    except Exception as e:
        print 'somethng else'
        msg = "Error creating GeoServer layer for %s: %s" % (new_table, str(e))
        return None, msg


    # Create the Layer in GeoNode from the GeoServer Layer
    try:

        # get the sld for this layer
        #style = cat.get_style("polygon")
        #print style.href

        '''
        sld_polygon = '<?xml version="1.0" encoding="ISO-8859-1"?><StyledLayerDescriptor version="1.0.0" xsi:schemaLocation="http://www.opengis.net/sld StyledLayerDescriptor.xsd" xmlns="http://www.opengis.net/sld" xmlns:ogc="http://www.opengis.net/ogc" xmlns:xlink="http://www.w3.org/1999/xlink" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"><!-- a Named Layer is the basic building block of an SLD document --><NamedLayer><Name>default_polygon</Name><UserStyle><!-- Styles can have names, titles and abstracts --><Title>Default Polygon</Title><Abstract>A sample style that draws a polygon</Abstract><!-- FeatureTypeStyles describe how to render different features --><!-- A FeatureTypeStyle for rendering polygons --><FeatureTypeStyle><Rule><Name>rule1</Name><Title>test</Title><Abstract>A polygon with a gray fill and a 1 pixel black outline</Abstract><PolygonSymbolizer><Fill><CssParameter name="fill">#AAAAAA</CssParameter></Fill><Stroke><CssParameter name="stroke">#000000</CssParameter><CssParameter name="stroke-width">1</CssParameter></Stroke></PolygonSymbolizer></Rule></FeatureTypeStyle></UserStyle></NamedLayer></StyledLayerDescriptor>'
        '''
        import requests

        r = requests.get('http://staging.geonode.wfp.org/geoserver/styles/polygon.sld')
        sld_polygon = r.text
        cat.create_style(new_table, sld_polygon, overwrite=True)
        style = cat.get_style(new_table)
        layer = cat.get_layer(new_table)
        layer.default_style = style
        cat.save(layer)

        #print sld_polygon

        #test = cat.create_style("testing_sld", style)
        #print test

        gsslurp_output = gs_slurp(filter=new_table)
        from geonode.base.models import ResourceBase
        #print gsslurp_output
        layer = ResourceBase.objects.get(title=new_table)
        #print layer

        output_2 = geoserver_post_save(layer, ResourceBase)
        #print output_2


        # create the geonode layer manually
        '''
        layer, created = Layer.objects.get_or_create(name=new_table, defaults={
            "workspace": workspace.name,
            "store": ds.name,
            "storeType": ds.resource_type,
            "typename": "%s:%s" % (workspace.name.encode('utf-8'), ft.name.encode('utf-8')),
            "title": ft.title or 'No title provided',
            "abstract": ft.abstract or 'No abstract provided',
            "uuid": str(uuid.uuid4()),
            "bbox_x0": Decimal(ft.latlon_bbox[0]),
            "bbox_x1": Decimal(ft.latlon_bbox[1]),
            "bbox_y0": Decimal(ft.latlon_bbox[2]),
            "bbox_y1": Decimal(ft.latlon_bbox[3])
        })
        '''
        #set_attributes(layer, overwrite=True)
    except Exception as e:
        msg = "Error creating GeoNode layer for %s: %s" % (new_table, str(e))
        return None, msg


@login_required
def download_xls(request):

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
        #areas = request.GET.get('areas')
        #areas = areas.replace(",", "','")
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
                #'areas': areas,
                'table': corresponding_data[btn]["table_name"],
                'column_1': corresponding_data[btn]["column_1"],
            })

        cur.execute(sqlstr)
        rows = cur.fetchall()

        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = "attachment; filename={file}".format(** {
            'file': corresponding_data[btn]["table_name"] + ".csv"
        })

        writer = csv.writer(response)
        writer.writerow(tuple(corresponding_data[btn]["columns"].split(',')))

        for row in rows:
            field_1 = row[0]
            field_2 = row[1].encode(encoding='UTF-8')
            fields = [field_1, field_2]
            writer.writerows([fields])
        return response
