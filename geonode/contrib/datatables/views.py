import sys
import os
import json
import traceback
from django.core import serializers
from django.core.serializers.json import Serializer
from django.shortcuts import render, get_object_or_404
from django.http import HttpResponse, HttpResponseRedirect
from django.contrib.auth.decorators import login_required
from django.utils.text import slugify
from django.views.decorators.csrf import csrf_exempt

from .models import DataTable, JoinTarget
from .forms import UploadDataTableForm
from .utils import process_csv_file, setup_join

@login_required
@csrf_exempt
def datatable_upload_api(request):
    if request.method != 'POST':
        return HttpResponse("Invalid Request", mimetype="text/plain", status=500)
    else:
        form = UploadDataTableForm(request.POST, request.FILES)
        if form.is_valid():
            table_name = slugify(unicode(os.path.splitext(os.path.basename(request.FILES['uploaded_file'].name))[0])).replace('-','_')
            instance = DataTable(uploaded_file=request.FILES['uploaded_file'], table_name=table_name, title=table_name)
            instance.save()
            dt, msg = process_csv_file(instance)
            if dt:
                return_dict = {
                    'datatable_id': dt.pk,
                    'datatable_name': dt.table_name,
                    'success': True,
                    'msg': ""
                }
                return HttpResponse(json.dumps(return_dict), mimetype="text/plain", status=200) 
            else:
                return_dict = {
                    'datatable_id': None,
                    'datatable_name': None,
                    'success': False,
                    'msg': msg
                } 
                return HttpResponse(json.dumps(return_dict), mimetype="text/plain", status=400) 
        else:
            return HttpResponse("Form Errors: %s" % str(form.errors), mimetype="text/plain", status=400)

@login_required
@csrf_exempt
def datatable_detail(request, dt_id):
    dt = get_object_or_404(DataTable, pk=dt_id)
    object = json.loads(serializers.serialize("json", (dt,), fields=('uploaded_file', 'table_name')))[0]
    attributes = json.loads(serializers.serialize("json", dt.attributes.all()))
    attribute_list = []
    for attribute in attributes:
        attribute_list.append({'attribute':attribute['fields']['attribute'], 'type':attribute['fields']['attribute_type']})
    object["attributes"] = attribute_list
    data = json.dumps(object) 
    return HttpResponse(data)

@login_required
def jointargets(request):
    jts = JoinTarget.objects.all()
    results = [ob.as_json() for ob in JoinTarget.objects.all()] 
    return HttpResponse(json.dumps(results), mimetype="application/json")

@login_required
@csrf_exempt
def tablejoin_api(request):
    if request.method == 'GET':
         return HttpResponse("Unsupported Method", mimetype="text/plain", status=500) 
    elif request.method == 'POST':
        table_name = request.POST.get("table_name", None)
        layer_typename = request.POST.get("layer_typename", None)
        table_attribute = request.POST.get("table_attribute", None)
        layer_attribute = request.POST.get("layer_attribute", None)
        if table_name and layer_typename and table_attribute and layer_attribute:
            try:
                tj = setup_join(table_name, layer_typename, table_attribute, layer_attribute)
                return_dict = {
                    'join_id': tj.pk,
                    'view_name': tj.view_name,
                    'datatable': tj.datatable.table_name,
                    'source_layer': tj.source_layer.typename,
                    'table_attribute': tj.table_attribute.attribute,
                    'layer_attribute': tj.layer_attribute.attribute,
                    'join_layer': tj.join_layer.typename,
                    'layer_url': tj.join_layer.get_absolute_url()
                }                  
                return HttpResponse(json.dumps(return_dict), mimetype="text/plain", status=200)
            except:
                traceback.print_exc(file=sys.stdout) 
                return HttpResponse("Unexpected Error", mimetype="text/plain", status=500) 
        else:
            return HttpResponse("Invalid Request", mimetype="text/plain", status=500) 
