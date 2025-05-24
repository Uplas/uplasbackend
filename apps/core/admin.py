from django.contrib import admin
# from .models import SystemSetting, FAQ # Example: Uncomment if you add these models

# Register your concrete models from the 'core' app here.
# Abstract models like BaseModel are not registered directly.

# Example if SystemSetting model was added:
# @admin.register(SystemSetting)
# class SystemSettingAdmin(admin.ModelAdmin):
#     list_display = ('key', 'value', 'description', 'updated_at')
#     search_fields = ('key', 'description')
#     list_filter = ('updated_at',)
#     readonly_fields = ('created_at', 'updated_at')

# Example if FAQ model was added:
# @admin.register(FAQ)
# class FAQAdmin(admin.ModelAdmin):
#     list_display = ('question', 'category', 'is_active', 'display_order', 'updated_at')
#     list_filter = ('is_active', 'category', 'updated_at')
#     search_fields = ('question', 'answer')
#     list_editable = ('is_active', 'display_order')
#     readonly_fields = ('created_at', 'updated_at')

