import sys
import os
import json
import traceback
from django.shortcuts import render
from django.http import HttpResponse, HttpResponseRedirect
from django.contrib.auth.decorators import login_required
from django.utils.text import slugify
from django.views.decorators.csrf import csrf_exempt

from .models import DataTable
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
            dt = process_csv_file(instance)
            return_dict = {
                'datatable_id': dt.pk,
                'datatable_name': dt.table_name
            }
            return HttpResponse(json.dumps(return_dict), mimetype="text/plain", status=200) 
        else:
            print form.errors 
            return HttpResponse("Invalid Request", mimetype="text/plain", status=500)

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
