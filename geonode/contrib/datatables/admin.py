from django.contrib import admin
from .models import DataTable, TableJoin, JoinTarget

class DataTableAdmin(admin.ModelAdmin):
    model = DataTable
    list_display = (
        'id',
        'title',
        'table_name',
        'tablespace')
    list_display_links = ('title',)


class TableJoinAdmin(admin.ModelAdmin):
    model = TableJoin 

class JoinTargetAdmin(admin.ModelAdmin):
    model = JoinTarget

admin.site.register(DataTable, DataTableAdmin)
admin.site.register(TableJoin, TableJoinAdmin)
admin.site.register(JoinTarget, JoinTargetAdmin)
