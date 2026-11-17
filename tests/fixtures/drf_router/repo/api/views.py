from rest_framework.viewsets import ModelViewSet, ReadOnlyModelViewSet
from rest_framework.decorators import action


class Users(ModelViewSet):
    @action(detail=True, methods=["post"], url_path="activate")
    def activate(self, request, pk=None):
        pass

    @action(detail=False)
    def recent(self, request):
        pass


class Reports(ReadOnlyModelViewSet):
    pass
