from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from .models import Board, BoardMembership


class BoardMembershipInline(admin.TabularInline):
    model = BoardMembership
    extra = 1
    autocomplete_fields = ("membership",)


@admin.register(Board)
class BoardAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "company",
        "owner",
        "visibility",
        "is_active",
        "is_archived",
        "created_at",
    )

    list_filter = (
        "visibility",
        "is_active",
        "is_archived",
        "company",
    )

    search_fields = (
        "name",
        "slug",
        "company__name",
        "owner__user__email",
    )

    readonly_fields = (
        "created_at",
        "updated_at",
        "archived_at",
    )

    autocomplete_fields = (
        "company",
        "owner",
    )

    fieldsets = (
        (_("Basic Information"), {
            "fields": (
                "name",
                "slug",
                "description",
                "cover",
            )
        }),
        (_("Access"), {
            "fields": (
                "company",
                "owner",
                "visibility",
            )
        }),
        (_("Status"), {
            "fields": (
                "is_active",
                "is_archived",
                "archived_at",
            )
        }),
        (_("Timestamps"), {
            "fields": (
                "created_at",
                "updated_at",
            )
        }),
    )

    inlines = [BoardMembershipInline]


@admin.register(BoardMembership)
class BoardMembershipAdmin(admin.ModelAdmin):
    list_display = (
        "board",
        "membership",
        "role",
        "is_active",
        "joined_at",
    )

    list_filter = (
        "role",
        "is_active",
    )

    search_fields = (
        "board__name",
        "membership__user__email",
    )

    autocomplete_fields = (
        "board",
        "membership",
    )