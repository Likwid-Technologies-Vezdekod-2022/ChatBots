from django.contrib import admin

from vk_bot import models


@admin.register(models.VkUser)
class VkUserAdmin(admin.ModelAdmin):
    list_display = ('id', 'chat_id', 'name',)
    search_fields = ('id', 'chat_id', 'name',)
    ordering = ['-update_date']
