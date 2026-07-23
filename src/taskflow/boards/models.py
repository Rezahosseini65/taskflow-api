from django.db import models
from django.utils.translation import gettext_lazy as _

# Create your models here.


class Board(models.Model):
    """
    Represents a project board, similar to Trello boards, where tasks are organized.
    Each board has a name, an optional description, an owner, and can have multiple members.
    Boards are identified by a unique slug for URL purposes.
    """

    class Visibility(models.TextChoices):
        PRIVATE = 'private', _('Private')
        WORKSPACE = 'workspace', _('Workspace')
        PUBLIC = 'public', _('Public')

    name = models.CharField(
        _('name'),
        max_length=64,
        help_text=_('The visible name of the board. For example: "Project Alpha" or "Marketing Plan".')
    )
    slug = models.SlugField(
        _('slug'),
        max_length=64,
        unique=True,
        allow_unicode=True,
        help_text=_('A unique URL-friendly identifier for the board. Can contain Persian characters.')
    )
    description = models.TextField(
        _('description'),
        null=True,
        blank=True,
        help_text=_('Optional. A short description about the purpose or content of the board.')
    )
    cover = models.ImageField(
        _('cover'),
        upload_to='boards/cover/',
        null=True,
        blank=True
    )
    visibility = models.CharField(
        max_length=20,
        choices=Visibility.choices,
        default=Visibility.PRIVATE
    )

    owner = models.ForeignKey(
        'companies.Membership',
        on_delete=models.PROTECT,
        related_name='owned_boards',
        verbose_name=_('owner'),
        help_text=_('The user who created and owns this board. Cannot be deleted while the board exists.')
    )
    members = models.ManyToManyField(
        'companies.Membership',
        related_name='member_boards',
        blank=True,
        through='BoardMembership',
        verbose_name=_('member board'),
        help_text=_('Users who have access to this board besides the owner.')
    )
    company = models.ForeignKey(
        'companies.Company',
        on_delete=models.CASCADE,
        blank=True,
        null=True,
        related_name='company_boards',
        verbose_name=_('company board'),
    )
    is_active = models.BooleanField(
        _('active board'),
        default=True
    )
    is_archived = models.BooleanField(
        _('archived'),
        default=False
    )
    archived_at = models.DateTimeField(
        _('archived at'),
        null=True,
        blank=True
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = _('Board')
        verbose_name_plural = _('Boards')

        ordering = ['-created_at']

        models.UniqueConstraint(
            fields=['company', 'name'],
            name='unique_board_name_per_company'
        )

        indexes = [
            models.Index(fields=['company']),
            models.Index(fields=['name']),
            models.Index(fields=['owner']),
        ]


class BoardMembership(models.Model):
    class RoleChoices(models.TextChoices):
        ADMIN = 'Admin', _('admin')
        MEMBER = 'Membership', _('membership')
        VIEWER = 'Viewer', _('viewer')

    board = models.ForeignKey(
        Board,
        on_delete=models.CASCADE,
        related_name='board_memberships',
        verbose_name=_('board')
    )
    membership = models.ForeignKey(
        'companies.Membership',
        on_delete=models.CASCADE,
        related_name='board_memberships',
        verbose_name=_('membership')
    )

    role = models.CharField(
        _('role'),
        max_length=11,
        choices=RoleChoices.choices,
        default=RoleChoices.MEMBER
    )

    joined_at = models.DateTimeField(
        _('joined at'),
        auto_now_add=True
    )
    is_active = models.BooleanField(
        _('active'),
        default=True
    )

    class Meta:
        verbose_name = _('Board Membership')
        verbose_name_plural = _('Board Memberships')

        constraints = [
            models.UniqueConstraint(
                fields=['board', 'membership'],
                name='unique_membership_per_board'
            )
        ]

        indexes = [
            models.Index(fields=['board']),
            models.Index(fields=['membership']),
        ]

    def __str__(self):
        return f'{self.membership} - {self.board}'

