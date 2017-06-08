import autocomplete_light
from models import Document

class DocumentAutocomplete(autocomplete_light.AutocompleteModelTemplate):
    choice_template = 'autocomplete_response.html'


autocomplete_light.register(
    Document,
    DocumentAutocomplete,
    search_fields=['title'],
    order_by=['title'],
    limit_choices=100,
    autocomplete_js_attributes={
        'placeholder': 'Document name..',
    },
)
