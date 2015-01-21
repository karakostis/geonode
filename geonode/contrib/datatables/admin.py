from django.contrib import admin
from .models import DataTable, TableJoin

class DataTableAdmin(admin.ModelAdmin):
    model = DataTable

class TableJoinAdmin(admin.ModelAdmin):
    model = TableJoin 

admin.site.register(DataTable, DataTableAdmin)
admin.site.register(TableJoin, TableJoinAdmin)
