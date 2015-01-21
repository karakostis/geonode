import os
import os
import glob
import uuid
import csvkit
from decimal import Decimal
from csvkit import sql
from csvkit import table
from csvkit import CSVKitWriter
from csvkit.cli import CSVKitUtility
from geoserver.catalog import Catalog
from geoserver.store import datastore_from_index

import psycopg2
from psycopg2.extensions import QuotedString

from django.utils.text import slugify
from django.core.files import File

from geonode.layers.models import Layer, Attribute
from geonode.contrib.datatables.models import DataTable, TableJoin
from geonode.geoserver.helpers import set_attributes

def process_file(csv_filename):

    table_name = slugify(unicode(os.path.splitext(os.path.basename(csv_filename))[0])).replace('-','_')
    if table_name[:1].isdigit():
        table_name = 'x' + table_name

    f = open(csv_filename, 'rb')
    
    csv_table = table.Table.from_csv(f,name=table_name)

    dt, created = DataTable.objects.get_or_create(title=table_name, table_name=table_name)
    csv_file = File(f)
    dt.uploaded_file.save(csv_filename, csv_file)
    dt.save()
    f.close()
    

    for column in csv_table: 
        attribute, created = Attribute.objects.get_or_create(resource=dt, 
            attribute=column.name, 
            attribute_label=column.name, 
            attribute_type=column.type.__name__, 
            display_order=column.order)

    # Create Database Table
    sql_table = sql.make_table(csv_table,table_name)
    create_table_sql = sql.make_create_table_statement(sql_table, dialect="postgresql")
    dt.create_table_sql = create_table_sql
    dt.save()
    conn = psycopg2.connect("dbname=geonode user=geonode")
    cur = conn.cursor()
    cur.execute('drop table if exists %s CASCADE;' % table_name) 
    cur.execute(create_table_sql)
    conn.commit()
    cur.close()
    conn.close()
    
    # Copy Data to postgres
    connection_string = "postgresql://geonode:geonode@localhost:5432/geonode"
    try:
        engine, metadata = sql.get_connection(connection_string)
    except ImportError:
        print "Unable to connect"
        return

    conn = engine.connect()
    trans = conn.begin()
 
    if csv_table.count_rows() > 0:
        insert = sql_table.insert()
        headers = csv_table.headers()
        conn.execute(insert, [dict(zip(headers, row)) for row in csv_table.to_rows()])

    trans.commit()
    conn.close()
    f.close()
    
    return table_name

def setup_join():
    dt = DataTable.objects.get(title='ca_tracts_pop')
    layer = Layer.objects.get(typename="geonode:tl_2013_06_tract")

    layer_attribute = layer.attributes.get(resource=layer, attribute_label="Geoid")
    table_attribute = dt.attributes.get(resource=dt,attribute_label="GEO.id2")

    layer_name = layer.typename.split(':')[1]
    view_name = "join_%s_%s" % (layer_name, dt.table_name)
    print view_name

    view_sql = 'create materialized view %s as select %s.*, %s.* from %s inner join %s on %s."%s" = %s."%s";' %  (view_name, layer_name, dt.table_name, layer_name, dt.table_name, layer_name, layer_attribute.attribute, dt.table_name, table_attribute.attribute)
    double_view_name = "view_%s" % view_name
    double_view_sql = "create view %s as select * from %s" % (double_view_name, view_name)
    tj, created = TableJoin.objects.get_or_create(source_layer=layer,datatable=dt, table_attribute=table_attribute, layer_attribute=layer_attribute, view_name=double_view_name)
    tj.view_sql = view_sql
    conn = psycopg2.connect("dbname=geonode user=geonode")
    cur = conn.cursor()
    cur.execute('drop view if exists %s;' % double_view_name) 
    cur.execute('drop materialized view if exists %s;' % view_name) 
    cur.execute(view_sql)
    cur.execute(double_view_sql)
    conn.commit()
    cur.close()
    conn.close()

    cat = Catalog('http://localhost:8080/geoserver/rest')
    workspace = cat.get_workspace("geonode")
    ds_list = cat.get_xml(workspace.datastore_url)
    datastores = [datastore_from_index(cat, workspace, n) for n in ds_list.findall("dataStore")]
    ds = None
    for datastore in datastores:
        if datastore.name == "datastore":
            ds = datastore
    ft = cat.publish_featuretype(double_view_name, ds, layer.srid, srs=layer.srid)
    cat.save(ft)

    layer, created = Layer.objects.get_or_create(name=view_name, defaults={
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
    set_attributes(layer, overwrite=True)
    print layer
    tj.join_layer = layer
    tj.save()
    print tj

csv_list = glob.glob('scratch/*.csv')
for csv in csv_list:
    print csv
    table_name = process_file(csv)
    print table_name
