import sys
import os
import json
import traceback
from django.shortcuts import render
from django.http import HttpResponse, HttpResponseRedirect
from django.contrib.auth.decorators import login_required
from django.utils.text import slugify

from .models import DataTable
from .forms import UploadDataTableForm
from .utils import process_file, setup_join

@login_required
def datatable_upload_api(request):
    if request.method != 'POST':
        return HttpResponse("Invalid Request", mimetype="text/plain", status=500)
    else:
        form = UploadDataTableForm(request.POST, request.FILES)
        if form.is_valid():
            table_name = slugify(unicode(os.path.splitext(os.path.basename(request.FILES['file'].name))[0])).replace('-','_')
            instance = DataTable(uploaded_file=request.FILES['file'], table_name=table_name, title=table_name)
            instance.save()
            dt = process_file(instance)
            return_dict = {
                'datatable_id': dt.pk,
                'datatable_name': dt.table_name
            }
            return HttpResponse(json.dumps(return_dict), mimetype="text/plain", status=200) 
        else:
            return HttpResponse("Invalid Request", mimetype="text/plain", status=500)

@login_required
def datatable_upload(request): 
    if request.method == 'POST':
        form = UploadDataTableForm(request.POST, request.FILES)
        if form.is_valid():
            table_name = slugify(unicode(os.path.splitext(os.path.basename(request.FILES['file'].name))[0])).replace('-','_')
            instance = DataTable(uploaded_file=request.FILES['file'], table_name=table_name, title=table_name)
            instance.save()
            process_file(instance)
            return HttpResponseRedirect('/datatables/')
    else:
        form = UploadDataTableForm()
    return render(request, 'datatables/datatable_upload.html', {'form': form})

def datatable_detail(request, dtid, template='datatables/datatable_detail.html'):
    pass

def datatable_metadata(request, dtid, template='datatables/datatable_metadata.html'):
    pass

def datatable_view(request, dtid, template='datatables/datatable_view.html'):
    pass

@login_required
def datatable_replace(request, dtid, template='datatables/datatable_replace.html'):
    pass

@login_required
def datatable_remove(request, dtid, template='datatables/datatable_remove.html'):
    pass

@login_required
def tablejoin_create(request, template='datatables/join_create.html'):
    pass

@login_required
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

@login_required
def tablejoin_update(request, template='datatables/join_update.html'):
    pass

def tablejoin_detail(request, template='datatables/join_detail.html'):
    pass

@login_required
def tablejoin_remove(request, template='datatables/join_remove.html'):
    pass

def join_layers(request, template='datatables/join_layers.html'):
    pass
