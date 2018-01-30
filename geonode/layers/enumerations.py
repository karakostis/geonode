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
    # osm
    'osm_id': 'osm id',
    'sourceid': 'source',
    'notes': 'notes',
    'onme': 'official road name',
    'rtenme': 'route name',
    'ntlclass': '"highway" tag',
    'fclass': 'functional class',
    'numlanes': 'number of lanes',
    'srftpe': 'surface type',
    'srfcond': 'surface condition',
    'isseasonal': 'seasonality',
    'curntprac': 'current practicability',
    'gnralspeed': 'general speed',
    'rdwidthm': 'road width in meters',
    'iselevated': 'Is the road a bridge?',
    'iso3': 'iso3 country code',
    'country': 'country name',
    'last_update': 'last update date',
    # admin boundaries
    'adm0_code': 'adm0_code',
    'adm0_name': 'adm0_name',
    'adm1_code': 'adm1_code',
    'adm1_name': 'adm1_name',
    'adm2_code': 'adm2_code',
    'adm2_name': 'adm2_name'
}

ATTRIBUTES_DESCRIPTION = {
    # osm
    'fclass': '1=Highway; 2=Primary; 3=Secondary; 4=Tertiary; 5=Residential; 6=Track/Trail; 7=Pathway',
    'isseasonal': 'Is the road affected by season?; 1=Yes; 2=No; 0=Unspecified',
    'curntprac': 'Non-motorized; Motorbike; 4WD<3.5mt; Light Truck(<10mt); Heavy Truck(<20mt); Truck + Trailer(>20mt); Unspecified',
    'iselevated': 'yes=1, no=0',
    'last_update': 'last update date',
    
    # admin boundaries
    'adm0_code': 'Code of country',
    'adm0_name': 'Name of country',
    'adm1_code': 'Code of region',
    'adm1_name': 'Name of region',
    'adm2_code': 'Code of province',
    'adm2_name': 'Name of province',

    # ica
    'Adm1_NAME' : 'Province name',
    'Adm2_NAME' : 'District name',
    'NPGS' : 'Number of poor growing seasons',
    'NPGS_Class' : 'Number of poor growing seasons, reclassified',
    'PGSArea' : 'Drought affected area',
    'PercDrArea' : 'Percentage of drought affected area',
    'PercDrClas' : 'Percentage of drought affected area, reclassified',
    'Dr_Risk' : 'Drought risk',
    'Dr_Class' : 'Drought risk, reclassified',
    'FLMaxFreq' : 'Maximum expected frequency of flood events',
    'FLMaxClas' : 'Maximum expected frequency of flood events, reclassified',
    'AreaFLRisk' : 'Flood affected area',
    'PercFLRisk' : 'Percentage of flood affected area',
    'PercFLClas' : 'Percentage of flood affected area, reclassified',
    'FloodRisk' : 'Flood risk',
    'FloodClass' : 'Flood risk, reclassified',
    'LSMaxFreq' : 'Maximum expected frequency of landslide events',
    'LSMaxClas' : 'Maximum expected frequency of landslide events, reclassified',
    'AreaLSRisk' : 'Landslide affected area',
    'PercLSRisk' : 'Percentage of landslide affected area',
    'PercLSClas' : 'Percentage of landslide affected area, reclassified',
    'LS_Risk' : 'Landslide risk',
    'LS_Class' : 'Landslide risk, reclassified',
    'FL_LS_Risk' : 'Rapid on-set shocks risk',
    'FL_LS_Clas' : 'Rapid on-set shocks risk, reclassified',
    'NS_Risk' : 'Natural shocks risk',
    'NS_Class' : 'Natural shocks risk, reclassified',
    'FI_Class' : 'Recurrence of food insecurity, reclassified',
    'FI_Var' : 'Food insecurity variability',
    'FI_Var_Cla' : 'Food insecurity variability, reclassified',
    'LTPlanPop' : 'Estimated number of food insecure people for long-term planning',
    'LTPlanPerc' : 'Percentage of food insecure people for long-term planning',
    'AdInsecPop' : 'Estimated number of additional food insecure people in case of a major shock',
    'ICA_Areas' : 'ICA Areas',
    'ICA_Categ' : 'ICA Categories',
    'PosMeanCha' : 'Positive ecological change',
    'PosMeanCla' : 'Positive ecological change, reclassified',
    'NegMeanCha' : 'Negative ecological change',
    'NegMeanCla' : 'Negative ecological change, reclassified',
    'ErosPr' : 'Percentage of surface prone to erosion',
    'ErosPrClas' : 'Percentage of surface prone to erosion, reclassified',
    'Stunt_Prev' : 'Prevalence of stunting in children below 5 years of age',
    'Stunt_Clas' : 'Prevalence of stunting in children below 5 years of age, reclassified',
    'Wast_Prev' : 'Prevalence of wasting in children below 5 years of age',
    'Wast_Clas' : 'Prevalence of wasting in children below 5 years of age, reclassified',
    'Und_Prev' : 'Prevalence of underweight in children below 5 years of age',
    'Und_Clas' : 'Prevalence of underweight in children below 5 years of age, reclassified'


}
