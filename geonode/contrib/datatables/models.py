import psycopg2
from django.db import models
from django.db.models import signals
from geonode.base.models import ResourceBase
from geonode.layers.models import Attribute, AttributeManager
from geonode.layers.models import Layer
from django.utils.text import slugify

CATEGORIES = ('Census Tract', 'Census Block', 'Census Block Group')
CATEGORY_CHOICES = [ (slugify(unicode(x.upper())), x) for x in CATEGORIES]

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

    def __unicode__(self):
        return self.table_name

    def remove_table(self):
        conn = psycopg2.connect("dbname=geonode user=geonode")
        cur = conn.cursor()
        cur.execute('drop table if exists %s;' % self.table_name)
        conn.commit()
        cur.close()
        conn.close() 

class JoinTarget(models.Model):
    """
    JoinTarget
    """

    layer = models.ForeignKey(Layer)
    attributes = models.ManyToManyField(Attribute)
    category = models.CharField(max_length=100, choices=CATEGORY_CHOICES)
    
    def __unicode__(self):
        return self.layer.title

    def as_json(self):
        attribute_list = []
        for attribute in self.attributes.all():
            attribute_list.append({'attribute':attribute.attribute, 'type':attribute.attribute_type})
        return dict(
            id=self.id, layer=self.layer.typename,
            attributes=attribute_list,
            category=self.category)

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

    def __unicode__(self):
        return self.view_name

    def remove_joins(self):
        conn = psycopg2.connect("dbname=geonode user=geonode")
        cur = conn.cursor()
        cur.execute('drop view if exists %s;' % self.view_name)
        cur.execute('drop materialized view if exists %s;' % self.view_name.replace('view_', ''))
        conn.commit()
        cur.close()
        conn.close() 

def pre_delete_datatable(instance, sender, **kwargs):
    """
    Remove the table from the Database
    """
    instance.remove_table()    


def pre_delete_tablejoin(instance, sender, **kwargs):
    """
    Remove the existing join in the database
    """
    instance.remove_joins()

signals.pre_delete.connect(pre_delete_tablejoin, sender=TableJoin)
signals.pre_delete.connect(pre_delete_datatable, sender=DataTable)
