from django.contrib import admin
from .models import Board


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