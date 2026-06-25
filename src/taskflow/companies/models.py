from django.db import models
from django.utils import timezone
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
            models.Index(fields=['created_at']),
            models.Index(fields=['owner', 'is_active']),
            models.Index(fields=['id', 'owner']),
        ]
        ordering = ['-created_at']

    def members_count(self):
        return self.members.count()

    def get_admin_members(self):
        return self.user_memberships.filter(role=Membership.RoleChoices.ADMIN)

    def get_member_roles(self, user):
        membership = self.user_memberships.filter(user=user).first()
        return membership.role if membership else None

    def get_members_with_roles(self):
        return self.user_memberships.select_related('user').all()

    def __str__(self):
        return f'{self.name}--{self.owner.email}'


class Membership(models.Model):
    class RoleChoices(models.TextChoices):
        ADMIN = 'Admin', _('admin')
        MEMBER = 'Member', _('member')
        OWNER = 'Owner', _('owner')

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
            models.Index(fields=['company_id', 'user_id']),  # این مهم‌ترینه
            models.Index(fields=['user_id']),
        ]

    def __str__(self):
        return f'{self.user.email}-{self.role}'


class Invitation(models.Model):
    class InvitationStatus(models.TextChoices):
        PENDING = 'pending', _('Pending')
        ACCEPTED = 'accepted', _('Accepted')
        EXPIRED = 'expired', _('Expired')
        CANCELLED = 'cancelled', _('Cancelled')

    class InvitationType(models.TextChoices):
        EMAIL = 'email', _('Email Invitation')
        DIRECT = 'direct', _('Direct Invitation')
        REQUEST = 'request', _('Join Request')
        MEMBER_INVITE = 'member_invite', _('Member Invite')

    email = models.EmailField(_('email'))
    company = models.ForeignKey(
        Company,
        on_delete=models.CASCADE,
        related_name='invitations',
        verbose_name=_('company')
    )
    invited_by = models.ForeignKey(
        'accounts.CustomUser',
        on_delete=models.CASCADE,
        related_name='sent_invitations',
        verbose_name=_('invited by')
    )
    invited_user = models.ForeignKey(
        'accounts.CustomUser',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='received_invitations',
        verbose_name=_('invited user')
    )
    role = models.CharField(
        _('role'),
        max_length=7,
        choices=Membership.RoleChoices.choices,
        default=Membership.RoleChoices.MEMBER
    )
    invitation_type = models.CharField(
        _('invitation type'),
        max_length=14,
        choices=InvitationType.choices,
        default=InvitationType.EMAIL
    )
    token = models.CharField(
        _('token'),
        max_length=100,
        unique=True
    )
    status = models.CharField(
        _('status'),
        max_length=20,
        choices=InvitationStatus.choices,
        default=InvitationStatus.PENDING
    )
    message = models.TextField(_('message'), blank=True)
    expires_at = models.DateTimeField(_('expires at'))
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _('invitation')
        verbose_name_plural = _('invitations')
        indexes = [
            models.Index(fields=['token']),
            models.Index(fields=['email', 'status']),
            models.Index(fields=['company', 'status']),
            models.Index(fields=['expires_at']),
            models.Index(fields=['invitation_type']),
        ]
        unique_together = ['email', 'company', 'status']

    def __str__(self):
        return f"{self.get_invitation_type_display()} - {self.email} to {self.company.name}"

    def is_expired(self)->bool:
        return timezone.now() > self.expires_at

    def accept(self, user):
        """Accept invitation and add user to company"""
        if self.is_expired():
            self.status = self.InvitationStatus.EXPIRED
            self.save()
            raise ValueError("Invitation has expired")

        membership, created = Membership.objects.get_or_create(
            user=user,
            company=self.company,
            defaults={'role': self.role}
        )

        self.status = self.InvitationStatus.ACCEPTED
        self.invited_user = user
        self.save()

        return membership

    def cancel(self):
        """Cancel invitation"""
        self.status = self.InvitationStatus.CANCELLED
        self.save()

