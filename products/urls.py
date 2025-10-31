"""
urls.py

URL configuration for the product app.
"""
from django.urls import path
from . import views

app_name = "products"

urlpatterns = [
    # Category endpoints
    path(
        "categories/",
        views.CategoryListView.as_view(),
        name="category-list",
    ),
    # Product endpoints (scoped by category)
    path(
        "categories/<slug:product_category_slug>/products/",
        views.ProductListByCategoryView.as_view(),
        name="product-list-by-category",
    ),
    # Attribute filters by category
    path(
        "categories/<slug:product_category_slug>/filters/",
        views.ProductAttributeOptionListByCategoryView.as_view(),
        name="attribute-options-by-category",
    ),
    path(
        "compare/",
        views.ProductCompareView.as_view(),
        name="product-compare",
    ),
    # Product detail
    path(
        "<slug:product_slug>/",
        views.ProductDetailView.as_view(),
        name="product-detail",
    ),

]
