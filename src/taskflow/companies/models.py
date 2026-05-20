from django.db import models
from django.utils.translation import gettext_lazy as _

# Create your models here.


class Company(models.Model):
    name = models.CharField(
        _('name'),
        max_length=128,
        unique=True
    )
    slug = models.SlugField(
        _('slug'),
        unique=True,
        allow_unicode=True
    )
    email = models.EmailField(
        _('email'),
        null=True,
        blank=True
    )
    website = models.URLField(
        _('website'),
        blank=True,
        null=True
    )
    description = models.TextField(
        _('description'),
        blank=True,
        null=True
    )
    logo = models.ImageField(
        _('image'),
        upload_to='company/logo/',
        null=True,
        blank=True
    )

    owner = models.ForeignKey(
        'accounts.CustomUser',
        on_delete=models.PROTECT,
        related_name='owned_companies',
        verbose_name=_('owner')
    )
    members=models.ManyToManyField(
        'accounts.CustomUser',
        blank=True,
        related_name='companies'
    )

    is_active = models.BooleanField(
        _('active'),
        default=True
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _('Company')
        verbose_name_plural = _('Companies')

        indexes = [
            models.Index(fields=['name']),
            models.Index(fields=['slug']),
            models.Index(fields=['owner']),
            models.Index(fields=['is_active']),
            models.Index(fields=['created_at'])
        ]
        ordering = ['-created_at']

    def members_count(self):
        return self.members.count()

    def __str__(self):
        return f'{self.name}--{self.owner.email}'