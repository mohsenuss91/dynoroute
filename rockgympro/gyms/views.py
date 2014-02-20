from django.shortcuts import render, get_object_or_404
from gyms.models import Gym, Route
from django.utils.timezone import now
from django.http import Http404
from django.views.generic import ListView, DetailView
from django.views.generic.detail import SingleObjectMixin

class GymFinderMixin(SingleObjectMixin):

    model = Gym
    slug_url_kwarg = "gym"

    def get(self, request, *args, **kwargs):
        self.object = get_object_or_404(Gym, slug=self.kwargs['gym'])
        return super(GymFinderMixin, self).get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super(GymFinderMixin, self).get_context_data(**kwargs)
        context['gym'] = self.object
        return context

class GymPage(GymFinderMixin, DetailView):

    template_name="gym_page.html"

class RoutesPage(GymFinderMixin, ListView):

    paginate_by = 2
    template_name = "gym_routes.html"

    def get_queryset(self):
        return self.object.routes.all()

class RoutePage(GymPage):

    template_name = "gym_route.html"

    def get_context_data(self, **kwargs):
        context = super(GymFinderMixin, self).get_context_data(**kwargs)
        context['route'] = get_object_or_404(self.object.routes, slug=self.kwargs['route'])
        return context