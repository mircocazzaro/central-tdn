from django import forms
from .models import Endpoint
from django.contrib.auth.forms import AuthenticationForm


QUESTION_CHOICES = [
    ('<https://w3id.org/brainteaser/ontology/schema/alsfrs1>',  "I have been less alert"),
    ('<https://w3id.org/brainteaser/ontology/schema/alsfrs2>',  "I have had difficulty paying attention for long periods of time"),
    ('<https://w3id.org/brainteaser/ontology/schema/alsfrs3>',  "I have been unable to think clearly"),
    ('<https://w3id.org/brainteaser/ontology/schema/alsfrs4>',  "I have been clumsy and uncoordinated"),
    ('<https://w3id.org/brainteaser/ontology/schema/alsfrs5>',  "I have been forgetful"),
    ('<https://w3id.org/brainteaser/ontology/schema/alsfrs6>',  "I have had to pace myself in my physical activities"),
    ('<https://w3id.org/brainteaser/ontology/schema/alsfrs7>',  "I have been less motivated to do anything that requires physical effort"),
    ('<https://w3id.org/brainteaser/ontology/schema/alsfrs8>',  "I have been less motivated to participate in social activities"),
    ('<https://w3id.org/brainteaser/ontology/schema/alsfrs9>',  "I have been limited in my ability to do things away from home"),
    ('<https://w3id.org/brainteaser/ontology/schema/alsfrs10>', "I have trouble maintaining physical effort for long periods"),
    ('<https://w3id.org/brainteaser/ontology/schema/alsfrs11>', "I have had difficulty making decisions"),
    ('<https://w3id.org/brainteaser/ontology/schema/alsfrs12>', "I have been less motivated to do anything that requires thinking"),
]

DISEASE_MAP = {
    'Amyotrophic Lateral Sclerosis':     'NCIT:C34373',
    'Multiple Sclerosis':     'NCIT:C3243',
    'Parkinson\'s Disease':     'NCIT:C26845',
}

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
        print(params)
        for p in (params or []):
            if p == 'question':
                # 2) For `question`, render a dropdown
                self.fields[p] = forms.ChoiceField(
                    choices=QUESTION_CHOICES,
                    label="Select ALSFRS question",
                    widget=forms.Select(attrs={'class': 'form-control'}),
                    required=True,
                )
            else:
                # 3) Fallback to your existing text input
                self.fields[p] = forms.CharField(
                    label=p.replace('_', ' ').capitalize(),
                    widget=forms.TextInput(attrs={'class':'form-control'}),
                    required=True,
                )


class LoginForm(AuthenticationForm):
    username = forms.CharField(widget=forms.TextInput(attrs={
        'class': 'form-control',
        'placeholder': 'Username',
    }))
    password = forms.CharField(widget=forms.PasswordInput(attrs={
        'class': 'form-control',
        'placeholder': 'Password',
    }))