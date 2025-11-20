from rest_framework.generics import ListAPIView

from .models import Province
from .serializers import ProvinceSerializer


class ProvinceListView(ListAPIView):
    serializer_class = ProvinceSerializer
    queryset = Province.objects.prefetch_related('cities')
