from django import forms
from .models import Endpoint

class EndpointForm(forms.ModelForm):
    class Meta:
        model = Endpoint
        fields = ['name', 'url', 'logo']
        widgets = {
            'name': forms.TextInput(attrs={'class':'form-control'}),
            'url':  forms.URLInput(attrs={'class':'form-control'}),
            'logo': forms.ClearableFileInput(attrs={'class':'form-control'}),
        }

class QueryForm(forms.Form):
    """
    Dynamically builds one field per SPARQL-template parameter.
     - `params` is a list of parameter names (strings) to expose.
    """
    def __init__(self, *args, params=None, **kwargs):
        super().__init__(*args, **kwargs)
        for p in (params or []):
            self.fields[p] = forms.CharField(
                label=p.replace('_', ' ').capitalize(),
                widget=forms.TextInput(attrs={'class':'form-control'}),
                required=True,
            )
