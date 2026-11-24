"""First-start registration of the Central administrator.

No account is shipped or created from a password in the environment. While no
user exists, /login/ and every page that needs a login lead to /setup/, where
the administrator chooses a username and password; the account is then stored
in the local database (never versioned). /setup/ closes for good once a user
exists.
"""
from django.contrib.auth import get_user_model, login
from django.contrib.auth import views as auth_views
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import transaction
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods


@require_http_methods(['GET', 'POST'])
def setup_view(request):
    User = get_user_model()
    if User.objects.exists():
        return redirect('login')
    errors = []
    username = ''
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        p1 = request.POST.get('password1', '')
        p2 = request.POST.get('password2', '')
        if not (3 <= len(username) <= 150):
            errors.append('The username must have 3 to 150 characters.')
        if p1 != p2:
            errors.append('The two passwords do not match.')
        if not errors:
            candidate = User(username=username)
            try:
                validate_password(p1, candidate)
            except ValidationError as exc:
                errors.extend(exc.messages)
        if not errors:
            with transaction.atomic():
                # Two simultaneous first visitors: only one account is created.
                if User.objects.select_for_update().exists():
                    return redirect('login')
                user = User.objects.create_superuser(username, '', p1)
            login(request, user)
            return redirect('central_catalog')
    return render(request, 'catalogapp/setup.html', {'errors': errors, 'username': username})


class FirstStartLoginView(auth_views.LoginView):
    """The standard login, except that with no user it sends to /setup/."""
    template_name = 'catalogapp/login.html'

    def dispatch(self, request, *args, **kwargs):
        if not get_user_model().objects.exists():
            return redirect('setup')
        return super().dispatch(request, *args, **kwargs)
