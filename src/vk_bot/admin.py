from django.contrib import admin

from vk_bot import models


@admin.register(models.VkUser)
class VkUserAdmin(admin.ModelAdmin):
    list_display = ('id', 'chat_id', 'name',)
    search_fields = ('id', 'chat_id', 'name',)
    ordering = ['-update_date']


@admin.register(models.Collection)
class CollectionAdmin(admin.ModelAdmin):
    list_display = ('id', 'standard', 'creation_date',)
    ordering = ['-update_date']


@admin.register(models.Image)
class ImageAdmin(admin.ModelAdmin):
    list_display = ('id', 'collection', 'attachment_data', 'creation_date',)
    ordering = ['-update_date']


@admin.register(models.Game)
class GameAdmin(admin.ModelAdmin):
    list_display = ('id', 'collection', 'status')
    ordering = ['-update_date']
