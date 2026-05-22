from django.db import models
from django.utils.translation import gettext_lazy as _

# Create your models here.


class Board(models.Model):
    """
    Represents a project board, similar to Trello boards, where tasks are organized.
    Each board has a name, an optional description, an owner, and can have multiple members.
    Boards are identified by a unique slug for URL purposes.
    """
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

    owner = models.ForeignKey(
        'accounts.CustomUser',
        on_delete=models.PROTECT,
        related_name='owned_boards',
        verbose_name=_('owner'),
        help_text=_('The user who created and owns this board. Cannot be deleted while the board exists.')
    )
    members = models.ManyToManyField(
        'accounts.CustomUser',
        related_name='boards',
        blank=True,
        verbose_name=_('member board'),
        help_text=_('Users who have access to this board besides the owner.')
    )

    is_active = models.BooleanField(
        _('active board'),
        default=True
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'{self.name}--{self.owner.email}'

    class Meta:
        verbose_name = _('Board')
        verbose_name_plural = _('Boards')

        ordering = ['-created_at']

        indexes = [
            models.Index(fields=['name', 'slug']),
            models.Index(fields=['owner']),
        ]


