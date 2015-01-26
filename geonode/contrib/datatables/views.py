import os
from django.shortcuts import render
from django.http import HttpResponseRedirect
from django.contrib.auth.decorators import login_required
from django.utils.text import slugify

from .models import DataTable
from .forms import UploadDataTableForm
from .utils import process_file

@login_required
def datatable_upload(request, template='datatables/datatable_upload.html'):
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
    return render(request, template, {'form': form})

def datatable_detail(request, dtid, template='datatables/datatable_defail.html'):
    pass

def datatable_metadata(request, dtid, template='datatables/datatable_metadata.html'):
    pass

def datatable_view(request, dtid, template='datatables/datatable_view.html'):
    pass

def datatable_replace(request, dtid, template='datatables/datatable_replace.html'):
    pass

def datatable_remove(request, dtid, template='datatables/datatable_remove.html'):
    pass

def tablejoin_create(request, template='datatables/join_create.html'):
    pass

def tablejoin_update(request, template='datatables/join_update.html'):
    pass

def tablejoin_detail(request, template='datatables/join_detail.html'):
    pass

def tablejoin_remove(request, template='datatables/join_remove.html'):
    pass

def join_layers(request, template='datatables/join_layers.html'):
    pass
