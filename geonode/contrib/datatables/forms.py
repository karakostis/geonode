from django import forms

class UploadDataTableForm(forms.Form):
    title = forms.CharField(max_length=50)
    uploaded_file = forms.FileField()
