from django.http import JsonResponse
from django.views.decorators.http import require_GET
from rest_framework.views import APIView


@require_GET
def health(request):
    return JsonResponse({"status": "ok"})


class UserList(APIView):
    def get(self, request):
        return JsonResponse({"users": []})
