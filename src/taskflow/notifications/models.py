from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class Notification(models.Model):
    class NotificationType(models.TextChoices):
        JOIN_REQUEST = 'join_request', _('Join Request')
        JOIN_APPROVED = 'join_approved', _('Join Approved')
        JOIN_REJECTED = 'join_rejected', _('Join Rejected')
        INVITATION = 'invitation', _('Invitation')
        SYSTEM = 'system', _('System')

    class NotificationStatus(models.TextChoices):
        UNREAD = 'unread', _('Unread')
        READ = 'read', _('Read')
        ARCHIVED = 'archived', _('Archived')

    recipient = models.ForeignKey(
        'accounts.CustomUser',
        on_delete=models.CASCADE,
        related_name='notifications',
        verbose_name=_('recipient')
    )
    sender = models.ForeignKey(
        'accounts.CustomUser',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='sent_notifications',
        verbose_name=_('sender')
    )
    notification_type = models.CharField(
        _('notification type'),
        max_length=20,
        choices=NotificationType.choices,
        default=NotificationType.SYSTEM
    )
    title = models.CharField(
        _('title'),
        max_length=128
    )
    message = models.TextField(
        _('message'),
        blank=True
    )
    action_url = models.CharField(
        _('action url'),
        max_length=500,
        blank=True,
        null=True
    )
    metadata = models.JSONField(
        _('metadata'),
        default=dict,
        blank=True
    )
    invitation = models.ForeignKey(
        'companies.Invitation',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='invitation_notifications',
        verbose_name=_('invitation')
    )
    company = models.ForeignKey(
        'companies.Company',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='company_notifications',
        verbose_name=_('company')
    )
    status = models.CharField(
        _('status'),
        max_length=20,
        choices=NotificationStatus.choices,
        default=NotificationStatus.UNREAD
    )

    created_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = _('notification')
        verbose_name_plural = _('notifications')
        indexes = [
            models.Index(fields=['recipient', 'status']),
            models.Index(fields=['recipient', '-created_at']),
            models.Index(fields=['-created_at']),
            models.Index(fields=['notification_type']),
        ]
        ordering = ['-created_at']

    def mark_as_read(self):
        if self.status == self.NotificationStatus.UNREAD:
            self.status = self.NotificationStatus.READ
            self.read_at = timezone.now()
            self.save()

    def mark_as_archived(self):
        self.status = self.NotificationStatus.ARCHIVED
        self.save()

    @classmethod
    def mark_all_as_read(cls, user):
        return cls.objects.filter(
            recipient=user,
            status=cls.NotificationStatus.UNREAD
        ).update(
            status=cls.NotificationStatus.READ,
            read_at=timezone.now()
        )

    @property
    def is_read(self):
        return self.status == self.NotificationStatus.READ

    @property
    def time_ago(self):
        from django.utils.timesince import timesince
        return timesince(self.created_at)

    def __str__(self):
        return f'{self.recipient.email} - {self.title}'