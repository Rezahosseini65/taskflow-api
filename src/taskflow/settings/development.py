from .base import *

DEBUG=True

ALLOWED_HOSTS = ['*']

INSTALLED_APPS += [
    'drf_spectacular',
    'debug_toolbar',
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

INTERNAL_IPS = [
    '127.0.0.1',
    'localhost',
    '0.0.0.0',
]

DEBUG_TOOLBAR_CONFIG = {
    'SHOW_TOOLBAR_CALLBACK': lambda request: True,
}