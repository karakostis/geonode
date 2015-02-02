import json
import requests
#from django.contrib.auth import get_user_model
#from django.core.urlresolvers import reverse

client = requests.session()

base_url = "http://23.23.180.177:8000"
login_url = base_url + "/account/login/"

# Retrieve the CSRF token first
client.get(login_url)  # sets the cookie
csrftoken = client.cookies['csrftoken']

login_data = dict(username="admin", password="admin", csrfmiddlewaretoken=csrftoken)
r = client.post(login_url, data=login_data, headers={"Referer": "test-client"})
print r

files = {'uploaded_file': open('scratch/ca_tracts_pop.csv','rb')}
response = client.post(base_url + '/datatables/api/upload', data={'title':'test'}, files=files)
print response.content
resp_dict = json.loads(response.content)
datatable_name = resp_dict['datatable_name']
print datatable_name

files = {
    'base_file': open('scratch/tl_2013_06_tract.shp','rb'),
    'dbf_file': open('scratch/tl_2013_06_tract.dbf','rb'),
    'prj_file': open('scratch/tl_2013_06_tract.prj','rb'),
    'shx_file': open('scratch/tl_2013_06_tract.shx','rb'),
    'xml_file': open('scratch/tl_2013_06_tract.shp.xml','rb')
    }

# Retrieve the CSRF token first
client.get(base_url + '/layers/upload')  # sets the cookie
csrftoken = client.cookies['csrftoken']

response = client.post(base_url + '/layers/upload', files=files, data={'csrfmiddlewaretoken':csrftoken})
print response.content

#join_props = {
#    'table_name': datatable_name, 
#    'layer_typename': saved_layer.typename, 
#    'table_attribute': 'GEO.id2', 
#    'layer_attribute': 'GEOID'
#}

#print join_props

#response = c.post('/datatables/api/join', join_props)
#print response
