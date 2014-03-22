import json

from django import shortcuts
from django.conf import settings
from django.contrib.auth import REDIRECT_FIELD_NAME, login as auth_login, logout as auth_logout, get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm, PasswordResetForm, SetPasswordForm, PasswordChangeForm
from django.contrib.auth.tokens import default_token_generator
from django.contrib.sites.shortcuts import get_current_site
from django.core import urlresolvers
from django.core.urlresolvers import reverse
from django.db import IntegrityError
from django.http import Http404
from django.http import HttpResponse
from django.http import HttpResponseRedirect, QueryDict
from django.shortcuts import render, get_object_or_404
from django.shortcuts import resolve_url
from django.template.response import TemplateResponse
from django.utils.http import is_safe_url, urlsafe_base64_decode
from django.utils.http import urlquote
from django.utils.six.moves.urllib.parse import urlparse, urlunparse
from django.utils.timezone import now
from django.utils.translation import ugettext as _
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.debug import sensitive_post_parameters
from django.views.generic import ListView, DetailView, View
from django.views.generic.base import ContextMixin
from django.views.generic.edit import CreateView, UpdateView, DeleteView
from gyms.forms import *
from gyms.models import *

def about(request):
    return render(request, "about.html")

def gym_list(request):
    context = dict(gyms=Gym.objects.all().order_by("name"))
    return render(request, "gyms_list.html", context)

class GymFinderMixin(ContextMixin):

    perms = None

    @property 
    def gym(self):
        try:
            return self._gym
        except AttributeError:
            self._gym = get_object_or_404(Gym, slug=self.kwargs['gym'])
            return self._gym

    def dispatch(self, request, *args, **kwargs):
        if self.perms is not None:
            if request.user.is_anonymous():
                return shortcuts.redirect("%s?next=%s" % (urlresolvers.reverse("gym_login", kwargs={'gym':self.gym.slug}), urlquote(request.path)))
            elif not (request.user.gym == self.gym and request.user.level >= self.perms):
                raise Http404()
        return super(GymFinderMixin, self).dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super(GymFinderMixin, self).get_context_data(**kwargs)
        context['gym'] = self.gym
        context['logout_next'] = urlresolvers.reverse("gym_page", kwargs=dict(gym=self.kwargs['gym']))
        if self.request.user.is_authenticated():
            context['followed'] = bool(GymFollow.objects.filter(gym=self.gym, user=self.request.user).count())
        return context

    def get_object(self):
        return self.gym

class JSONResponseMixin(object):
    """
    A mixin that can be used to render a JSON response.
    """
    def render_to_json_response(self, context, **response_kwargs):
        """
        Returns a JSON response, transforming 'context' to make the payload.
        """
        return HttpResponse(
            self.convert_context_to_json(context),
            content_type='application/json',
            **response_kwargs
        )

    def convert_context_to_json(self, context):
        "Convert the context dictionary into a JSON object"
        # Note: This is *EXTREMELY* naive; in reality, you'll need
        # to do much more complex handling to ensure that arbitrary
        # objects -- such as Django model instances or querysets
        # -- can be serialized as JSON.
        return json.dumps(context)

    def render_to_response(self, context, **response_kwargs):
        return self.render_to_json_response(context, **response_kwargs)

class GymPage(GymFinderMixin, DetailView):

    template_name="gym_page.html"

class GymAJAX(JSONResponseMixin, GymFinderMixin, View):

    def post(self, request, *args, **kwargs):
        gym = self.gym
        user = request.user
        if user.is_anonymous():
            raise Http404
        elif user.gym is not None and user.gym != self.gym:
            raise Http404
        elif kwargs['action'] == "follow":
            try:
                GymFollow(gym=gym, user=user).save()
            except IntegrityError:
                return self.render_to_response(dict(success=True, new=False))
            return self.render_to_response(dict(success=True, new=True))
        elif kwargs['action'] == "unfollow":
            GymFollow.objects.filter(user=user, gym=gym).delete()
            return self.render_to_response(dict(success=True))

class RoutesPage(GymFinderMixin, ListView):

    template_name = "gym_routes.html"
    sorts = {
        "-date_set":"Most Recent",
        "grade":"Difficulty",
        "location":"Location",
        "-score":"User Rating",
    }

    def get_sort(self):
        sort = self.request.GET.get("sort", "-date_set")
        if not sort in self.sorts:
            sort = "-date_set"
        return sort

    def get_context_data(self, **kwargs):
        context = super(RoutesPage, self).get_context_data(**kwargs)
        context['sort'] = self.get_sort()
        context['sort_name'] = self.sorts[self.get_sort()]
        return context

    def get_queryset(self):
        return self.gym.routes.filter(status="complete").order_by(self.get_sort())

class AdminRoutesPage(RoutesPage):

    perms = 500

    template_name = "gym_routes_admin.html"

    def get_queryset(self):
        return self.gym.routes.order_by(self.get_sort())

class RouteFinderMixin(GymFinderMixin):

    @property 
    def route(self):
        try:
            return self._route
        except AttributeError:
            self._route = get_object_or_404(self.gym.routes, slug=self.kwargs['route'])
            return self._route

    def get_context_data(self, **kwargs):
        context = super(RouteFinderMixin, self).get_context_data(**kwargs)
        context['route'] = self.route
        context['sent'] = bool(self.route.sends.filter(id=self.request.user.id).count())
        context['favorited'] = bool(self.route.favorites.filter(id=self.request.user.id).count())
        if self.request.user.is_authenticated():
            try:
                context['score'] = self.route.rating_set.get(user=self.request.user).score
            except Rating.DoesNotExist:
                pass
        return context

    def get_object(self):
        return self.route

class RoutePage(RouteFinderMixin, DetailView):

    template_name = "gym_route.html"

    def get_object(self):
        route = super(RoutePage, self).get_object()
        route.views += 1
        route.save()
        return route

class RouteSendList(RouteFinderMixin, ListView):
    template_name = "gym_route_sends.html"

    def get_queryset(self):
        return self.route.send_set.order_by("-created")

class RouteAJAX(JSONResponseMixin, RouteFinderMixin, View):

    def post(self, request, *args, **kwargs):
        route = self.route
        user = request.user
        if user.is_anonymous():
            raise Http404
        elif user.gym is not None:
            raise Http404
        elif kwargs['action'] == "send":
            try:
                Send(route=route, user=user).save()
            except IntegrityError:
                return self.render_to_response(dict(success=True, new=False))
            return self.render_to_response(dict(success=True, new=True))
        elif kwargs['action'] == "unsend":
            Send.objects.filter(user=user, route=route).delete()
            return self.render_to_response(dict(success=True))
        elif kwargs['action'] == "favorite":
            try:
                Favorite(route=route, user=user).save()
                return self.render_to_response(dict(success=True))
            except IntegrityError:
                return self.render_to_response(dict(success=True, new=False))
            return self.render_to_response(dict(success=True, new=True))
        elif kwargs['action'] == "unfavorite":
            Favorite.objects.filter(user=user, route=route).delete()
            return self.render_to_response(dict(success=True))
        elif kwargs['action'] == "rate":
            score = int(request.POST['score'])
            Rating.objects.filter(route=route, user=user).delete()
            if(not 0<score<=5):
                return self.render_to_response(dict(success=False))
            else:
                Rating(user=user, route=route, score=score).save()
            return self.render_to_response(dict(success=True))

class GymDashboard(GymPage):

    perms = 500

    template_name="gym_dashboard.html"

    def get_context_data(self, **kwargs):
        context = super(GymDashboard, self).get_context_data(**kwargs)
        context['routes'] = self.gym.routes.order_by("-created")[:5]
        return context

class GymStats(JSONResponseMixin, GymFinderMixin, DetailView):

    perms = 500

    def split(self, d):
        return [dict(label=k, data=v) for k,v in d.items()]

    def get_context_data(self, **kwargs):
        context = {}
        d = {}
        for k,v in self.gym.grades(type="top_rope").items():
            d[round(k)] = d.get(round(k), 0)+v
        context['top_rope_grades'] = self.split({Route(grade=k).get_grade_display():v for k,v in d.items()})
        d = {}
        for k,v in self.gym.grades(type="bouldering").items():
            d[round(k)] = d.get(round(k), 0)+v
        context['bouldering_grades'] = self.split({Route(grade=k).get_grade_display():v for k,v in d.items()})
        context['types'] = self.split(self.gym.types())
        context['setters'] = self.split(self.gym.setters())
        context['locations'] = self.split(self.gym.locations())
        return context

class AdminRouteAdd(GymFinderMixin, CreateView):

    model = Route

    perms = 1000

    form_class = RouteForm

    def get_form_kwargs(self):
        kwargs = super(AdminRouteAdd, self).get_form_kwargs()
        kwargs['gym'] = self.gym
        kwargs['user'] = self.request.user
        return kwargs

    def get_success_url(self):
        return urlresolvers.reverse("gym_routes_admin", kwargs=dict(gym=self.kwargs['gym']))

class AdminRouteEdit(RouteFinderMixin, UpdateView):

    perms = 1000
    template_name = 'gyms/route_update_form.html'

    form_class = RouteForm

    def get_form_kwargs(self):
        kwargs = super(AdminRouteEdit, self).get_form_kwargs()
        kwargs['gym'] = self.gym
        kwargs['user'] = self.request.user
        return kwargs

    def get_success_url(self):
        return urlresolvers.reverse("gym_routes_admin", kwargs=dict(gym=self.kwargs['gym']))

class GymSettings(UpdateView):

    perms = 10000
    
    template_name="gym_settings.html"
    form_class = GymSettingsForm
    model = Gym
    slug_url_kwarg = "gym"

    def get_success_url(self):
        return urlresolvers.reverse("gym_dashboard", kwargs=dict(gym=self.kwargs['gym']))

class AdminStaffPage(GymFinderMixin, ListView):

    perms = 10000

    template_name = "gym_staff_admin.html"

    def get_queryset(self):
        return self.gym.staff.order_by("-level")

class EmployeeFinderMixin(GymFinderMixin):

    no_owner = False

    @property 
    def employee(self):
        try:
            employee = self._employee
        except AttributeError:
            employee = self._employee = get_object_or_404(self.gym.staff, username=self.kwargs['user'])
        if self.no_owner and employee.level == 10000:
            raise Http404
        return employee

    def get_context_data(self, **kwargs):
        context = super(EmployeeFinderMixin, self).get_context_data(**kwargs)
        context['employee'] = self.employee
        return context

    def get_object(self):
        return self.employee

class AdminEmployeeAdd(GymFinderMixin, CreateView):

    perms = 10000

    form_class = EmployeeCreationForm
    template_name="gyms/employee_form.html"

    def get_form_kwargs(self):
        kwargs = super(AdminEmployeeAdd, self).get_form_kwargs()
        kwargs['gym'] = self.gym
        return kwargs

    def get_success_url(self):
        return urlresolvers.reverse("gym_staff_admin", kwargs=dict(gym=self.kwargs['gym']))

class AdminEmployeeUpdate(EmployeeFinderMixin, UpdateView):

    perms = 10000

    form_class = EmployeeUpdateForm
    template_name="gyms/employee_update_form.html"

    def get_form_kwargs(self):
        kwargs = super(AdminEmployeeUpdate, self).get_form_kwargs()
        kwargs['gym'] = self.gym
        return kwargs

    def get_success_url(self):
        return urlresolvers.reverse("gym_staff_admin", kwargs=dict(gym=self.kwargs['gym']))

class AdminEmployeeDelete(EmployeeFinderMixin, DeleteView):

    no_owner = True

    perms = 10000

    template_name = "gyms/employee_confirm_delete.html"

    def get_success_url(self):
        return urlresolvers.reverse("gym_staff_admin", kwargs=dict(gym=self.kwargs['gym']))

def redirect(request, to, *args, **kwargs):
    return shortcuts.redirect(to, *args, **kwargs)

@sensitive_post_parameters()
@csrf_protect
@never_cache
def login(request, gym, template_name='registration/login.html',
          redirect_field_name=REDIRECT_FIELD_NAME,
          authentication_form=GymAuthForm,
          current_app=None, extra_context=None):
    """
    Displays the login form and handles the login action.
    """

    gym = get_object_or_404(Gym, slug=gym)
    redirect_to = request.POST.get(redirect_field_name,
                                   request.GET.get(redirect_field_name, ''))

    if request.method == "POST":
        form = authentication_form(request, data=request.POST, gym=gym)
        if form.is_valid():

            # Ensure the user-originating redirection url is safe.
            if not is_safe_url(url=redirect_to, host=request.get_host()):
                redirect_to = resolve_url(settings.LOGIN_REDIRECT_URL)

            # Okay, security check complete. Log the user in.
            auth_login(request, form.get_user())

            return HttpResponseRedirect(redirect_to)
    else:
        form = authentication_form(request)

    current_site = get_current_site(request)

    context = {
        'form': form,
        redirect_field_name: redirect_to,
        'site': current_site,
        'site_name': current_site.name,
        'gym': gym,
    }
    if extra_context is not None:
        context.update(extra_context)
    return TemplateResponse(request, template_name, context,
                            current_app=current_app)