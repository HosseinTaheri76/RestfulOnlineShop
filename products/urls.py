from django.urls import path

from . import views

from rest_framework.routers import DefaultRouter

app_name = 'products'

router = DefaultRouter()

urlpatterns = []

router.register('categories', views.CategoryViewSet, basename='category')
router.register('', views.ProductViewSet, basename='product')

urlpatterns += router.urls
