from .base import *

DEBUG=True

ALLOWED_HOSTS = ['*']

INSTALLED_APPS += [
    'drf_spectacular',
]

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'taskflow',
        'USER': 'taskflow',
        'PASSWORD': 'taskflow',
        'HOST': 'db',
        'PORT': '5432',
    }
}

SPECTACULAR_SETTINGS = {
    'TITLE': 'API Documentation',
    'DESCRIPTION': 'API documentation for Your Project',
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
}