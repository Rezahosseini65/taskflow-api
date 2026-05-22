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
        related_name='companies',
        through='Membership',
        through_fields=('company', 'user'),
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

    def get_admin_members(self):
        return self.user_memberships.filter(role=Membership.RoleChoices.ADMIN)

    def get_member_roles(self, user):
        membership = self.user_memberships.filter(user=user).first()
        return membership.role if membership else None

    def __str__(self):
        return f'{self.name}--{self.owner.email}'


class Membership(models.Model):
    class RoleChoices(models.TextChoices):
        ADMIN = 'Admin', _('admin')
        MEMBER = 'Member', _('member')
    user = models.ForeignKey(
        'accounts.CustomUser',
        on_delete=models.CASCADE,
        related_name='company_memberships',
        verbose_name=_('user')
    )
    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name='user_memberships',
        verbose_name=_('company')
    )
    role = models.CharField(
        _('role'),
        max_length=7,
        choices=RoleChoices.choices,
        default=RoleChoices.MEMBER
    )
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _('membership')
        verbose_name_plural = _('memberships')
        unique_together = ['user', 'company']
        indexes = [
            models.Index(fields=['user', 'company']),
            models.Index(fields=['role']),
        ]

    def __str__(self):
        return f'{self.user.email}-{self.company.name}-{self.role}'

