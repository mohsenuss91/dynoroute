from gyms.models import Route, Gym
from django.forms import ModelForm
from users.models import User
from django.utils import timezone
from django import forms

from django.forms.widgets import RadioSelect
from django.utils.safestring import mark_safe
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth import authenticate
from django.contrib.auth.forms import UserCreationForm, UserChangeForm

class RouteForm(ModelForm):

    location = forms.ChoiceField()

    def __init__(self, gym, user, *args, **kwargs):
        super(RouteForm, self).__init__(*args, **kwargs)
        self.fields['setter'].queryset = gym.staff.filter(level__gte=1000)
        self.fields['date_set'].initial = timezone.now()
        self.fields['status'].initial = 'complete'
        self.fields['type'].initial = 'bouldering'
        self.fields['location'].choices = tuple([(x.strip(),x.strip()) for x in gym.location_options.split('\n')])
        self.instance.gym = gym
        self.fields['setter'].initial = user

    class Meta:
        fields = ['type', 'image', 'grade', 'location', 'date_set', 'setter', 'name', 'notes', 'status', 'color1', 'color2']
        model = Route
        widgets = {
        'notes': forms.Textarea(attrs={'rows':3, 'cols':10}),
        'color1': forms.Select(attrs=dict(id="route-color")),
        'color2': forms.Select(attrs=dict(id="route-color2")),
        'image': forms.FileInput(),
        'date_set': forms.DateInput(attrs=dict(id="route-date-set"), format="%m/%d/%Y"),
        'type': forms.RadioSelect(),
        }

class GymSettingsForm(ModelForm):

    class Meta:
        fields = ['name', 'named_routes', 'location_options']
        model=Gym

class GymAuthForm(AuthenticationForm):

    def __init__(self, request, gym=None, *args, **kwargs):
        self.gym = gym or None
        super(GymAuthForm, self).__init__(request, *args, **kwargs)

    def clean(self):
        username = self.cleaned_data.get('username')
        password = self.cleaned_data.get('password')

        if username and password:
            self.user_cache = authenticate(username=username,
                                           password=password, gym=self.gym)
            if self.user_cache is None:
                raise forms.ValidationError(
                    self.error_messages['invalid_login'],
                    code='invalid_login',
                    params={'username': self.username_field.verbose_name},
                )
            else:
                self.confirm_login_allowed(self.user_cache)

        return self.cleaned_data

class EmployeeCreationForm(UserCreationForm):

    first_name = forms.CharField(required=True)
    last_name = forms.CharField(required=True)

    class Meta:
        model = User
        fields = ('username', 'first_name', 'last_name', 'level')

    def __init__(self, gym, *args, **kwargs):
        super(EmployeeCreationForm, self).__init__(*args, **kwargs)
        self.instance.gym = gym
        self.fields['level'].choices = self.fields['level'].choices[2:]

    def clean_username(self):
        # Since User.username is unique, this check is redundant,
        # but it sets a nicer error message than the ORM. See #13147.
        username = self.cleaned_data["username"]
        try:
            User.objects.get(username=username, gym=self.instance.gym or None)
        except User.DoesNotExist:
            return username
        raise forms.ValidationError(
            self.error_messages['duplicate_username'],
            code='duplicate_username',
        )

class EmployeeUpdateForm(UserChangeForm):

    password = None
    username = None

    first_name = forms.CharField(required=True)
    last_name = forms.CharField(required=True)

    class Meta:
        model = User
        fields = ('first_name', 'last_name', 'level')

    def __init__(self, *args, **kwargs):
        super(EmployeeUpdateForm, self).__init__(*args, **kwargs)
        self.fields['level'].choices = self.fields['level'].choices[2:]
        if self.instance.level == 10000:
            del self.fields['level']

    def clean_username(self):
        # Since User.username is unique, this check is redundant,
        # but it sets a nicer error message than the ORM. See #13147.
        username = self.cleaned_data["username"]
        try:
            User.objects.get(username=username, gym=self.instance.gym or None)
        except User.DoesNotExist:
            return username
        raise forms.ValidationError(
            self.error_messages['duplicate_username'],
            code='duplicate_username',
        )
