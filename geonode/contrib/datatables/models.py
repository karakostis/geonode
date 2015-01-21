from django.db import models
from geonode.base.models import ResourceBase
from geonode.layers.models import Attribute, AttributeManager
from geonode.layers.models import Layer

class DataTable(ResourceBase):

    """
    DataTable (inherits ResourceBase fields)
    """

    # internal fields
    table_name = models.CharField(max_length=255, unique=True)
    tablespace = models.CharField(max_length=255)
    uploaded_file = models.FileField(upload_to="datatables")
    create_table_sql = models.TextField(null=True, blank=True)

    @property
    def attributes(self):
        return self.attribute_set.exclude(attribute='the_geom')

    objects = AttributeManager()

class TableJoin(models.Model):
    """
    TableJoin 
    """

    datatable = models.ForeignKey(DataTable)
    source_layer = models.ForeignKey(Layer, related_name="source_layer")
    table_attribute = models.ForeignKey(Attribute, related_name="table_attribute")
    layer_attribute = models.ForeignKey(Attribute, related_name="layer_attribute")
    view_name = models.CharField(max_length=255, null=True, blank=True)
    view_sql = models.TextField(null=True, blank=True)
    join_layer = models.ForeignKey(Layer, related_name="join_layer", null=True, blank=True)
