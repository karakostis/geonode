from django import forms

class UploadDataTableForm(forms.Form):
    title = forms.CharField(max_length=255)
    uploaded_file = forms.FileField()
