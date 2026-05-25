from django.contrib.auth.hashers import make_password
from django.db import models
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from django.contrib.auth.models import (
    AbstractBaseUser,
    PermissionsMixin,
    UserManager
)

from .validators import phone_number_validator

# Create your models here.


class CustomUserManager(UserManager):

    def create_user(
        self, email, password =None, **extra_fields
    ):
        """
        Create and save a user with the given email, and password.
        """
        if not email:
            raise ValueError("The given email must be set")

        email = email.strip()

        if 'display_name' not in extra_fields or not extra_fields['display_name']:
            extra_fields.setdefault('display_name', email.split('@')[0])

        email = self.normalize_email(email).lower()
        user = self.model(email=email, **extra_fields)
        user.password = make_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(
        self, email, password =None, **extra_fields
    ):
        """
        Create and save a new superuser with the given email and password.
        """
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")

        return self.create_user(email, password, **extra_fields)


class CustomUser(AbstractBaseUser, PermissionsMixin):
    email = models.EmailField(
        _('email'),
        unique=True
    )
    first_name = models.CharField(
        _('first name'),
        max_length=64,
        null=True,
        blank=True
    )
    last_name = models.CharField(
        _('last name'),
        max_length=64,
        null=True,
        blank=True
    )
    display_name = models.CharField(
        _('display name'),
        max_length=150,
        null=True,
        blank=True,
        help_text=_('Name shown to other team members')
    )
    phone_number = models.CharField(
        _('phone number'),
        max_length=13,
        validators=[phone_number_validator],
        null=True,
        blank=True
    )
    avatar = models.ImageField(
        _('avatar'),
        upload_to='avatars/',
        blank=True,
        null=True
    )
    email_notifications_enabled = models.BooleanField(
        _('email notifications'),
        default=True
    )

    is_staff = models.BooleanField(
        _('staff status'),
        default=True,
        help_text=_("Designates whether the user can log into this admin site."),
    )
    is_active = models.BooleanField(
        _('active'),
        default=True,
        help_text=_(
            "Designates whether this user should be treated as active. "
            "Unselect this instead of deleting accounts."
        ),
    )

    date_joined = models.DateTimeField(_("date joined"), default=timezone.now)
    last_activity = models.DateTimeField(_('last activity'), default=timezone.now)
    is_online = models.BooleanField(_('online status'), default=False)

    objects = CustomUserManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    class Meta:
        verbose_name = _('user')
        verbose_name_plural = _('users')
        indexes = [
            models.Index(fields=['email']),
            models.Index(fields=['display_name']),
            models.Index(fields=['last_activity']),
        ]

    def clean(self):
        super().clean()
        self.email = self.__class__.objects.normalize_email(self.email)

    def get_full_name(self):
        """Return the full_name or fallback to email"""
        if self.first_name and self.last_name:
            return f"{self.first_name} {self.last_name}"
        return self.email

    def update_last_activity(self):
        """Update user's last activity timestamp"""
        self.last_activity = timezone.now()
        self.save(update_fields=['last_activity'])

    def mark_online(self):
        """Mark user as online"""
        self.is_online = True
        self.update_last_activity()
        self.save(update_fields=['is_online', 'last_activity'])

    def mark_offline(self):
        """Mark user as offline"""
        self.is_online = False
        self.save(update_fields=['is_online'])

    def __str__(self):
        return self.get_full_name()