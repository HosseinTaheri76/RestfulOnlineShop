from django.urls import path

from . import views

app_name = 'locations'

urlpatterns = [
    path('', views.ProvinceListView.as_view(), name='province-city-list'),
]
