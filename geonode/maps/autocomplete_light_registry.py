import autocomplete_light
from models import Map

class MapAutocomplete(autocomplete_light.AutocompleteModelTemplate):
    choice_template = 'autocomplete_response.html'


autocomplete_light.register(
    Map,
    MapAutocomplete,
    search_fields=['title'],
    order_by=['title'],
    limit_choices=100,
    autocomplete_js_attributes={
        'placeholder': 'Map name..',
    },
)
