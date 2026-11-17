from rest_framework import mixins, viewsets
from rest_framework.decorators import api_view


class Base(mixins.ListModelMixin, mixins.CreateModelMixin, viewsets.GenericViewSet):
    pass


class Items(Base):
    http_method_names = ["get"]


@api_view(["GET", "POST"])
def status(request):
    pass
