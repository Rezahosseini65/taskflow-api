# admin.py
from django.contrib import admin
from django.db import models
from django.utils.html import format_html
from django.db.models import Count
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from .models import Company
from ..accounts.models import CustomUser


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    # لیست فیلدهای نمایش داده شده
    list_display = (
        'name',
        'owner_display',
        'members_count',
        'is_active_display',
        'created_at_display',
        'logo_preview'
    )

    # فیلدهای قابل جستجو
    search_fields = (
        'name',
        'slug',
        'email',
        'owner__email',
        'owner__phone_number'
    )

    # فیلترهای سمت راست صفحه
    list_filter = (
        'is_active',
        'created_at',
        ('owner', admin.RelatedOnlyFieldListFilter),
    )

    # فیلدهای فقط خواندنی
    readonly_fields = (
        'created_at',
        'updated_at',
        'slug_readonly',
        'logo_preview_large',
        'members_list'
    )

    # فیلدهایی که خودکار پر می‌شوند
    prepopulated_fields = {'slug': ('name',)}

    # مرتب‌سازی پیش‌فرض
    ordering = ('-created_at',)

    # تعداد آیتم در هر صفحه
    list_per_page = 25

    # اکشن‌های سفارشی
    actions = ['activate_companies', 'deactivate_companies', 'export_companies']

    # گروه‌بندی فیلدها در صفحه ویرایش
    fieldsets = (
        (_('Basic Information'), {
            'fields': (
                'name',
                'slug',
                'email',
                'website'
            )
        }),
        (_('Content'), {
            'fields': ('description', 'logo', 'logo_preview_large'),
            'classes': ('wide',),
        }),
        (_('Members & Ownership'), {
            'fields': ('owner', 'members', 'members_list'),
            'classes': ('collapse',),
        }),
        (_('Status'), {
            'fields': ('is_active',),
        }),
        (_('Timestamps'), {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )

    def get_queryset(self, request):
        """بهینه‌سازی کوئری با count اعضا"""
        return super().get_queryset(request).annotate(
            total_members=Count('members')
        )

    # روش‌های نمایش فیلدهای سفارشی
    @admin.display(description=_('Owner'), ordering='owner__email')
    def owner_display(self, obj):
        """نمایش مالک با لینک"""
        url = reverse(
            'admin:accounts_customuser_change',
            args=[obj.owner.id]
        )
        return format_html(
            '<a href="{}" style="font-weight: bold;">{}</a>',
            url,
            obj.owner.email
        )

    owner_display.short_description = _('Owner')

    @admin.display(description=_('Members Count'), ordering='total_members')
    def members_count(self, obj):
        """تعداد اعضا"""
        count = getattr(obj, 'total_members', obj.members.count())
        return format_html(
            '<span style="background: #4CAF50; color: white; '
            'padding: 2px 8px; border-radius: 12px;">{} {}</span>',
            count,
            _('members')
        )

    @admin.display(description=_('Status'), boolean=True)
    def is_active_display(self, obj):
        """نمایش وضعیت فعال/غیرفعال"""
        return obj.is_active

    @admin.display(description=_('Created At'), ordering='created_at')
    def created_at_display(self, obj):
        """نمایش تاریخ با فرمت فارسی"""
        return obj.created_at.strftime('%Y/%m/%d - %H:%M')

    @admin.display(description=_('Logo'))
    def logo_preview(self, obj):
        """پیش‌نمایش لوگو در لیست"""
        if obj.logo:
            return format_html(
                '<img src="{}" width="40" height="40" style="'
                'border-radius: 8px; object-fit: cover;" />',
                obj.logo.url
            )
        return format_html(
            '<span style="color: gray;">📷 {}</span>',
            _('No logo')
        )

    @admin.display(description=_('Logo Preview'))
    def logo_preview_large(self, obj):
        """پیش‌نمایش بزرگ لوگو در صفحه ویرایش"""
        if obj.logo:
            return format_html(
                '<div style="margin: 10px 0;">'
                '<img src="{}" width="200" style="border-radius: 12px; '
                'border: 2px solid #ddd; padding: 5px;" />'
                '<p><strong>{}</strong> {} x {}</p>'
                '</div>',
                obj.logo.url,
                _('Dimensions:'),
                obj.logo.width if hasattr(obj.logo, 'width') else '?',
                obj.logo.height if hasattr(obj.logo, 'height') else '?'
            )
        return format_html(
            '<div style="padding: 20px; background: #f0f0f0; '
            'border-radius: 8px; text-align: center;">'
            '📷 {}'
            '</div>',
            _('No logo uploaded')
        )

    @admin.display(description=_('Members List'))
    def members_list(self, obj):
        """نمایش لیست اعضا با لینک"""
        members = obj.members.all()[:10]
        if not members:
            return format_html(
                '<span style="color: gray;">⚠️ {}</span>',
                _('No members')
            )

        members_html = '<div style="max-height: 200px; overflow-y: auto;">'
        for member in members:
            url = reverse('admin:accounts_customuser_change', args=[member.id])
            members_html += format_html(
                '<div style="padding: 5px; border-bottom: 1px solid #eee;">'
                '<a href="{}">📧 {}</a>'
                '</div>',
                url, member.email
            )

        total_members = obj.members.count()
        if total_members > 10:
            members_html += format_html(
                '<div style="padding: 5px; color: blue; font-weight: bold;">'
                '... +{} {}'
                '</div>',
                total_members - 10,
                _('more members')
            )

        members_html += '</div>'
        return format_html(members_html)

    @admin.display(description=_('Slug'))
    def slug_readonly(self, obj):
        """نمایش اسلاگ فقط خواندنی"""
        return format_html(
            '<code style="background: #f4f4f4; padding: 5px;">{}</code>',
            obj.slug
        )

    # اکشن‌های سفارشی
    @admin.action(description=_('Activate selected companies'))
    def activate_companies(self, request, queryset):
        """فعال کردن شرکت‌های انتخاب شده"""
        updated = queryset.update(is_active=True)
        self.message_user(
            request,
            _('{} companies were successfully activated.').format(updated)
        )

    @admin.action(description=_('Deactivate selected companies'))
    def deactivate_companies(self, request, queryset):
        """غیرفعال کردن شرکت‌های انتخاب شده"""
        updated = queryset.update(is_active=False)
        self.message_user(
            request,
            _('{} companies were successfully deactivated.').format(updated)
        )

    @admin.action(description=_('Export selected companies to CSV'))
    def export_companies(self, request, queryset):
        """خروجی CSV از شرکت‌های انتخاب شده"""
        import csv
        from django.http import HttpResponse

        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename="companies.csv"'

        writer = csv.writer(response)
        writer.writerow([
            _('Name'), _('Slug'), _('Email'), _('Website'),
            _('Owner'), _('Members Count'), _('Active'), _('Created At')
        ])

        for company in queryset:
            writer.writerow([
                company.name,
                company.slug,
                company.email or '',
                company.website or '',
                company.owner.email,
                company.members.count(),
                _('Yes') if company.is_active else _('No'),
                company.created_at.strftime('%Y-%m-%d %H:%M:%S')
            ])

        self.message_user(request, _('Export completed successfully.'))
        return response

    # اعتبارسنجی سفارشی
    def save_model(self, request, obj, form, change):
        """ذخیره با ثبت خودکار creator"""
        if not change:  # اگر شرکت جدید است
            if not obj.owner:
                obj.owner = request.user
        super().save_model(request, obj, form, change)

    # فیلتر کردن لیست بر اساس دسترسی کاربر
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if not request.user.is_superuser:
            # ادمین‌های معمولی فقط شرکت‌هایی که مالک یا عضو هستند را ببینند
            return qs.filter(
                models.Q(owner=request.user) |
                models.Q(members=request.user)
            ).distinct()
        return qs

    # محدود کردن انتخاب مالک
    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == 'owner':
            kwargs['queryset'] = CustomUser.objects.filter(is_staff=True)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)