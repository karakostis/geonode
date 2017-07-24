# -*- coding: utf-8 -*-
#########################################################################
#
# Copyright (C) 2012 OpenPlans
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.
#
#########################################################################

LAYER_ATTRIBUTE_NUMERIC_DATA_TYPES = [
    'xsd:byte',
    'xsd:decimal',
    'xsd:double',
    'xsd:int',
    'xsd:integer',
    'xsd:long',
    'xsd:negativeInteger',
    'xsd:nonNegativeInteger',
    'xsd:nonPositiveInteger',
    'xsd:positiveInteger',
    'xsd:short',
    'xsd:unsignedLong',
    'xsd:unsignedInt',
    'xsd:unsignedShort',
    'xsd:unsignedByte',
]

ATTRIBUTES_LABEL = {
    'osm_id': 'osm id',
    'sourceid': 'source',
    'notes': 'notes',
    'onme': 'official road name',
    'rtenme': 'route name',
    'ntlclass': 'OSM "highway" tag',
    'fclass': 'functional class',
    'numlanes': 'number of lanes',
    'srftpe': 'surface type',
    'srfcond': 'surface condition',
    'isseasonal': 'seasonality',
    'curntprac': 'current practicability',
    'gnralspeed': 'general speed',
    'rdwidthm': 'road width in meters',
    'status': 'current road status',
    'iselevated': 'Is the road a bridge?',
    'iso3': 'iso3 country code',
    'country': 'country name',
    'last_update': 'last update date',
}

ATTRIBUTES_DESCRIPTION = {
    'fclass': '1=Highway; 2=Primary; 3=Secondary; 4=Tertiary; 5=Residential; 6=Track/Trail; 7=Pathway',
    'isseasonal': 'Is the road affected by season?; 1=Yes; 2=No; 0=Unspecified',
    'curntprac': 'Non-motorized; Motorbike; 4WD<3.5mt; Light Truck(<10mt); Heavy Truck(<20mt); Truck + Trailer(>20mt); Unspecified',
    'status': 'Open, Restricted, Closed',
    'iselevated': 'yes=1, no=0',
    'last_update': 'last update date',
}
