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

    invited_by = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='invited_users',
        verbose_name=_('invited by')
    )
    invitation_accepted_at = models.DateTimeField(
        _('invitation accepted at'),
        null=True,
        blank=True
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

    def clean(self):
        super().clean()
        self.email = self.__class__.objects.normalize_email(self.email)