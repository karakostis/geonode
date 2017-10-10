# -*- coding: utf-8 -*-

###############################################
# Geosite master local_settings
###############################################

# path for static and uploaded files
SERVE_PATH = '/static/'

# share a database
"""
DATABASES = {
    'default' : {
        'ENGINE': 'django.contrib.gis.db.backends.postgis',
        'NAME': '',
        'USER' : '',
        'PASSWORD' : '',
        'HOST' : 'localhost',
        'PORT' : '5432',
    }
    # vector datastore for uploads
    # 'datastore' : {
    #    'ENGINE': 'django.contrib.gis.db.backends.postgis',
    #    'NAME': '',
    #    'USER' : '',
    #    'PASSWORD' : '',
    #    'HOST' : '',
    #    'PORT' : '',
    # }
}
"""

DATABASES = {
    'default': {
        'ENGINE': 'django.contrib.gis.db.backends.postgis',
        'NAME': wallet.DATABASES.default.NAME,
        'USER': wallet.DATABASES.default.USER,
        'PASSWORD': wallet.DATABASES.default.PASSWORD,
        'HOST': wallet.DATABASES.default.HOST,
        'PORT': '5432',
    },
    # vector datastore for uploads
    'uploaded' : {
        'ENGINE': 'django.contrib.gis.db.backends.postgis',
        'NAME': wallet.DATABASES.uploaded.NAME,
        'USER' : wallet.DATABASES.uploaded.USER,
        'PASSWORD' : wallet.DATABASES.uploaded.PASSWORD,
        'HOST' : wallet.DATABASES.uploaded.HOST,
        'PORT' : '5432',
    }
}

# internal url to GeoServer
GEOSERVER_URL = 'http://localhost:8080/geoserver/'
