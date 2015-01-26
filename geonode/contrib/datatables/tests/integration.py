import json
from django.test import Client
from django.contrib.auth import get_user_model
from django.core.urlresolvers import reverse

from geonode.layers.utils import file_upload

c = Client()
c.login(username='admin', password='admin')

with open('scratch/ca_tracts_pop.csv') as fp:
    response = c.post('/datatables/upload/api/', {'title': 'test', 'file': fp})
    resp_dict = json.loads(response.content)
    datatable_name = resp_dict['datatable_name']


admin = get_user_model().objects.get(username="admin")
saved_layer = file_upload(
    "scratch/tl_2013_06_tract.shp",
    name="tl_2013_06_tract",
    user=admin,
    overwrite=True,
)

join_props = {
    'table_name': datatable_name, 
    'layer_typename': saved_layer.typename, 
    'table_attribute': 'GEO.id2', 
    'layer_attribute': 'GEOID'
}

print join_props

response = c.post('/datatables/api/join', join_props)
print response
