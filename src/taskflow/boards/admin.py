from django.contrib import admin
from .models import Board, List


@admin.register(Board)
class BoardAdmin(admin.ModelAdmin):
    list_display = ('name', 'owner', 'created_at', 'updated_at')

    list_filter = ('created_at', 'owner')

    search_fields = ('name', 'description', 'owner__email')

    prepopulated_fields = {'slug': ('name',)}

    readonly_fields = ('created_at', 'updated_at')

    filter_horizontal = ('members',)

    fieldsets = (
        (None, {
            'fields': ('name', 'slug', 'description')
        }),
        ('Ownership & Membership', {
            'fields': ('owner', 'members'),
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(List)
class ListAdmin(admin.ModelAdmin):

    list_display = ('name', 'board', 'position', 'created_at', 'updated_at')

    list_filter = ('board', 'created_at')

    search_fields = ('name', 'board__name')

    readonly_fields = ('created_at', 'updated_at')

    fieldsets = (
        (None, {
            'fields': ('name', 'board', 'position')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )