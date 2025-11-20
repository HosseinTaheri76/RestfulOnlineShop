from rest_framework.viewsets import ModelViewSet
from rest_framework.permissions import IsAuthenticated

from .models import UserAddress
from .serializers import UserAddressSerializer


class UserAddressViewSet(ModelViewSet):
    permission_classes = [IsAuthenticated, ]
    serializer_class = UserAddressSerializer

    def get_queryset(self):
        return UserAddress.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)