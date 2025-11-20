from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()

app_name = 'addresses'

urlpatterns = []

router.register('', views.UserAddressViewSet, basename='address')

urlpatterns += router.urls
