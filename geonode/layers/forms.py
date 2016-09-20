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
import tempfile
import zipfile
import psycopg2
import autocomplete_light

from django.conf import settings
from django import forms
from django.utils.translation import ugettext_lazy as _
from django.utils import simplejson as json
from geonode.layers.utils import unzip_file
from geonode.layers.models import Layer, Attribute

autocomplete_light.autodiscover() # flake8: noqa

from geonode.base.forms import ResourceBaseForm


class JSONField(forms.CharField):

    def clean(self, text):
        text = super(JSONField, self).clean(text)
        try:
            return json.loads(text)
        except ValueError:
            raise forms.ValidationError("this field must be valid JSON")


class LayerForm(ResourceBaseForm):

    class Meta(ResourceBaseForm.Meta):
        model = Layer
        exclude = ResourceBaseForm.Meta.exclude + (
            'workspace',
            'store',
            'storeType',
            'typename',
            'default_style',
            'styles',
            'upload_session',
            'service',)


class LayerUploadForm(forms.Form):
    base_file = forms.FileField()
    dbf_file = forms.FileField(required=False)
    shx_file = forms.FileField(required=False)
    prj_file = forms.FileField(required=False)
    xml_file = forms.FileField(required=False)

    charset = forms.CharField(required=False)

    spatial_files = (
        "base_file",
        "dbf_file",
        "shx_file",
        "prj_file")

    def clean(self):
        cleaned = super(LayerUploadForm, self).clean()
        dbf_file = shx_file = prj_file = xml_file = None
        base_name = base_ext = None
        if zipfile.is_zipfile(cleaned["base_file"]):
            filenames = zipfile.ZipFile(cleaned["base_file"]).namelist()
            for filename in filenames:
                name, ext = os.path.splitext(filename)
                if ext.lower() == '.shp':
                    if base_name is not None:
                        raise forms.ValidationError(
                            "Only one shapefile per zip is allowed")
                    base_name = name
                    base_ext = ext
                elif ext.lower() == '.dbf':
                    dbf_file = filename
                elif ext.lower() == '.shx':
                    shx_file = filename
                elif ext.lower() == '.prj':
                    prj_file = filename
                elif ext.lower() == '.xml':
                    xml_file = filename
            if base_name is None:
                raise forms.ValidationError(
                    "Zip files can only contain shapefile.")
        else:
            base_name, base_ext = os.path.splitext(cleaned["base_file"].name)
            if cleaned["dbf_file"] is not None:
                dbf_file = cleaned["dbf_file"].name
            if cleaned["shx_file"] is not None:
                shx_file = cleaned["shx_file"].name
            if cleaned["prj_file"] is not None:
                prj_file = cleaned["prj_file"].name
            if cleaned["xml_file"] is not None:
                xml_file = cleaned["xml_file"].name

        if base_ext.lower() not in (".shp", ".tif", ".tiff", ".geotif", ".geotiff"):
            raise forms.ValidationError(
                "Only Shapefiles and GeoTiffs are supported. You uploaded a %s file" %
                base_ext)
        if base_ext.lower() == ".shp":
            if dbf_file is None or shx_file is None:
                raise forms.ValidationError(
                    "When uploading Shapefiles, .shx and .dbf files are also required.")
            dbf_name, __ = os.path.splitext(dbf_file)
            shx_name, __ = os.path.splitext(shx_file)
            if dbf_name != base_name or shx_name != base_name:
                raise forms.ValidationError(
                    "It looks like you're uploading "
                    "components from different Shapefiles. Please "
                    "double-check your file selections.")
            if prj_file is not None:
                if os.path.splitext(prj_file)[0] != base_name:
                    raise forms.ValidationError(
                        "It looks like you're "
                        "uploading components from different Shapefiles. "
                        "Please double-check your file selections.")
            if xml_file is not None:
                if os.path.splitext(xml_file)[0] != base_name:
                    if xml_file.find('.shp') != -1:
                        # force rename of file so that file.shp.xml doesn't
                        # overwrite as file.shp
                        if cleaned.get("xml_file"):
                            cleaned["xml_file"].name = '%s.xml' % base_name

        return cleaned

    def write_files(self):

        absolute_base_file = None
        tempdir = tempfile.mkdtemp()

        if zipfile.is_zipfile(self.cleaned_data['base_file']):
            absolute_base_file = unzip_file(self.cleaned_data['base_file'], '.shp', tempdir=tempdir)

        else:
            for field in self.spatial_files:
                f = self.cleaned_data[field]
                if f is not None:
                    path = os.path.join(tempdir, f.name)
                    with open(path, 'wb') as writable:
                        for c in f.chunks():
                            writable.write(c)
            absolute_base_file = os.path.join(tempdir,
                                              self.cleaned_data["base_file"].name)
        return tempdir, absolute_base_file


class NewLayerUploadForm(LayerUploadForm):
    sld_file = forms.FileField(required=False)
    xml_file = forms.FileField(required=False)

    abstract = forms.CharField(required=False)
    layer_title = forms.CharField(required=False)
    permissions = JSONField()
    charset = forms.CharField(required=False)

    spatial_files = (
        "base_file",
        "dbf_file",
        "shx_file",
        "prj_file",
        "sld_file",
        "xml_file")


class LayerDescriptionForm(forms.Form):
    title = forms.CharField(300)
    abstract = forms.CharField(1000, widget=forms.Textarea, required=False)
    keywords = forms.CharField(500, required=False)


class LayerAttributeForm(forms.ModelForm):

    def __init__(self, *args, **kwargs):
        super(LayerAttributeForm, self).__init__(*args, **kwargs)
        self.fields['attribute'].widget.attrs['readonly'] = True
        self.fields['display_order'].widget.attrs['size'] = 3

    class Meta:
        model = Attribute
        exclude = (
            'attribute_type',
            'count',
            'min',
            'max',
            'average',
            'median',
            'stddev',
            'sum',
            'unique_values',
            'last_stats_updated',
            'objects')


class LayerStyleUploadForm(forms.Form):
    layerid = forms.IntegerField()
    name = forms.CharField(required=False)
    update = forms.BooleanField(required=False)
    sld = forms.FileField()


def get_country_names():

    constr = "dbname='{dbname}' user='{user}' host='{host}' password='{password}'".format(** {
        'dbname': settings.DATABASES['uploaded']['NAME'],
        'user': settings.DATABASES['uploaded']['USER'],
        'host': settings.DATABASES['uploaded']['HOST'],
        'password': settings.DATABASES['uploaded']['PASSWORD']
    })

    conn = psycopg2.connect(constr)
    cur = conn.cursor()

    sqlstr = "SELECT DISTINCT ({country_names}) FROM {table} ORDER BY {country_names};".format(** {
        'country_names': 'adm0_name',
        'table': 'wld_bnd_adm0_gaul_2015'
    })

    cur.execute(sqlstr)
    countries = cur.fetchall()
    choices_list = []
    cntr = ['World','World']
    choices_list.append(cntr)
    for i in range(len(countries)):

        cntr = [countries[i][0],countries[i][0]]
        choices_list.append(cntr)

    return choices_list

class UploadCSVForm(forms.Form):

    def __init__(self, *args, **kwargs):
        super(UploadCSVForm, self).__init__(*args, **kwargs)
        self.fields['selected_country'] = forms.MultipleChoiceField(choices=get_country_names(), required=True)

    title = forms.CharField(max_length=80, required=True)

    LAYER_TYPE = (
        ('1', 'Global Layer'),
        ('2', 'Layer by Region'),
        ('3', 'Layer by Province'),
    )
    layer_type = forms.ChoiceField(choices=LAYER_TYPE, required=True)

    csv = forms.FileField(required=True)


    def write_files(self):

        absolute_base_file = None
        tempdir = tempfile.mkdtemp()

        f = self.cleaned_data['csv']

        if f is not None:
            path = os.path.join(tempdir, f.name)
            with open(path, 'wb') as writable:
                for c in f.chunks():
                    writable.write(c)
        absolute_base_file = os.path.join(tempdir,self.cleaned_data["csv"].name)



        return tempdir, absolute_base_file


    def clean(self):
        cleaned_data = super(UploadCSVForm, self).clean()
        csv_file = self.cleaned_data.get('csv')
        if not csv_file:
            raise forms.ValidationError(_("Please select a CSV file."))
        else:
            csv_file_type = str(csv_file).split('.')
            if csv_file_type[1] not in ['csv','CSV']:
                raise forms.ValidationError(_("This is not a supported format. Please upload a CSV file."))
        return cleaned_data


class UploadEmptyLayerForm(forms.Form):

    empty_layer_name = forms.CharField(max_length=80, required=True, label="Name of new Layer")

    GEOM_TYPE = (
        ('POINT', 'Points'),
        ('MULTILINESTRING', 'Lines'),
        ('MULTIPOLYGON', 'Polygons')
    )

    geom_type = forms.ChoiceField(choices=GEOM_TYPE, required=True, label="Type of Data")
    total_input_fields = forms.CharField(widget=forms.HiddenInput())
    permissions_json = forms.CharField(max_length=500) #  stores the permissions json from the permissions form

    def __init__(self, *args, **kwargs):

        FIELD_TYPE = (
            ('Integer', 'Integer'),
            ('Double', 'Double'),
            ('Character', 'Character')
        )

        extra_fields = kwargs.pop('extra', 0)

        if not extra_fields:
            extra_fields = 0

        super(UploadEmptyLayerForm, self).__init__(*args, **kwargs)
        self.fields['total_input_fields'].initial = extra_fields

        for index in range(int(extra_fields)):
            # generate extra fields in the number specified via extra_fields
            self.fields['extra_field_{index}'.format(index=index)] = forms.CharField(min_length=3, max_length=15, label="Attribute %s" % index)
            self.fields['field_type_{index}'.format(index=index)] = forms.ChoiceField(choices=FIELD_TYPE, label="")
