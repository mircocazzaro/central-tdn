from django import forms
from django.core.validators import RegexValidator
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

DISEASE_CHOICES = [(code, label) for label, code in DISEASE_MAP.items()]

# Same grammars the endpoints enforce (tdn-endpoint/myapp/catalog.py). A value
# outside them would be silently dropped by every endpoint, so Central rejects
# it up front and tells the user.
_AGE = RegexValidator(r'^[0-9]{1,3}(?:\.[0-9]{1,2})?$', "Age in years, e.g. 40 or 40.5.")
_SEX = RegexValidator(r'^[A-Za-z]{1,16}$', "Letters only, e.g. female.")
_ATC = RegexValidator(r'^[A-Z](?:[0-9]{2}(?:[A-Z](?:[A-Z](?:[0-9]{2})?)?)?)?$',
                      "An ATC code in capitals, e.g. N07 or N07XX02.")


def _text(label, validator):
    return forms.CharField(label=label, validators=[validator], strip=True,
                           widget=forms.TextInput(attrs={'class': 'form-control'}))


def _field_for(param):
    if param == 'disease':
        return forms.ChoiceField(choices=DISEASE_CHOICES, label="Select disease",
                                 widget=forms.Select(attrs={'class': 'form-control'}))
    if param == 'question':
        return forms.ChoiceField(choices=QUESTION_CHOICES, label="Select ALSFRS question",
                                 widget=forms.Select(attrs={'class': 'form-control'}))
    if param == 'age' or (param.startswith('age') and param[3:].isdigit()):
        return _text(param.capitalize(), _AGE)
    if param == 'sex':
        return _text("Sex", _SEX)
    if param == 'atc':
        return _text("ATC group", _ATC)
    if param.endswith('date'):
        return forms.DateField(label=param.replace('_', ' ').capitalize(),
                               widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}))
    raise ValueError(f"no validation rule for template parameter {param!r}")


class QueryForm(forms.Form):
    """One validated field per template parameter.

    ``cleaned_data`` holds the strings to substitute into the template.
    Every catalog parameter must have a rule in ``_field_for``.
    """
    def __init__(self, *args, params=None, **kwargs):
        super().__init__(*args, **kwargs)
        for p in (params or []):
            self.fields[p] = _field_for(p)

    def clean(self):
        data = super().clean()
        return {k: v.isoformat() if hasattr(v, 'isoformat') else v for k, v in data.items()}


class LoginForm(AuthenticationForm):
    username = forms.CharField(widget=forms.TextInput(attrs={
        'class': 'form-control',
        'placeholder': 'Username',
    }))
    password = forms.CharField(widget=forms.PasswordInput(attrs={
        'class': 'form-control',
        'placeholder': 'Password',
    }))