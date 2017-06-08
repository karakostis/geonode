import autocomplete_light
from models import Layer

class LayerAutocomplete(autocomplete_light.AutocompleteModelTemplate):
    choice_template = 'autocomplete_response.html'


autocomplete_light.register(
    Layer,
    LayerAutocomplete,
    search_fields=[
        'title',
        '^typename'],
    order_by=['title'],
    limit_choices=100,
    autocomplete_js_attributes={
        'placeholder': 'Layer name..',
    },
)
