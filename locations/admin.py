from django.contrib import admin
from .models import Province, City


# =========================
#   City Inline
# =========================
class CityInline(admin.TabularInline):
    model = City
    extra = 1
    fields = ("title", "is_active")
    show_change_link = True
    ordering = ("title",)
    autocomplete_fields = ()
    verbose_name = "City"
    verbose_name_plural = "Cities"


# =========================
#   Province Admin
# =========================
@admin.register(Province)
class ProvinceAdmin(admin.ModelAdmin):
    list_display = ("title", "is_active", "active_city_count")
    list_filter = ("is_active",)
    search_fields = ("title",)
    ordering = ("title",)

    inlines = [CityInline]

    @admin.display(description="Active cities")
    def active_city_count(self, obj):
        return obj.cities.filter(is_active=True).count()


# =========================
#   City Admin
# =========================
@admin.register(City)
class CityAdmin(admin.ModelAdmin):
    list_display = ("title", "province", "is_active")
    list_filter = ("is_active", "province")
    search_fields = ("title", "province__title")
    autocomplete_fields = ("province",)
    ordering = ("province__title", "title")
