from django.views import View
from django.views.decorators.http import require_GET


@require_GET
def health(request):
    pass


class Users(View):
    def get(self, request):
        pass

    def post(self, request):
        pass
