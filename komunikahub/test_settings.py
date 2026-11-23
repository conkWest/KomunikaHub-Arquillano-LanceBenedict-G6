"""Local/CI settings: runs the test suite on SQLite so it never touches Supabase.

    python manage.py test --settings=komunikahub.test_settings
"""
from django.contrib.messages import constants as message_constants

from .settings import *  # noqa: F401,F403

SECRET_KEY = SECRET_KEY or 'test-only-key'  # noqa: F405
DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': ':memory:'}}
PASSWORD_HASHERS = ['django.contrib.auth.hashers.MD5PasswordHasher']
MEDIA_ROOT = BASE_DIR / 'media_test'  # noqa: F405

# Safety net in case these are missing from the main settings file.
if 'MIDDLEWARE' not in globals():
    MIDDLEWARE = [
        'django.middleware.security.SecurityMiddleware',
        'django.contrib.sessions.middleware.SessionMiddleware',
        'django.middleware.common.CommonMiddleware',
        'django.middleware.csrf.CsrfViewMiddleware',
        'django.contrib.auth.middleware.AuthenticationMiddleware',
        'django.contrib.messages.middleware.MessageMiddleware',
        'django.middleware.clickjacking.XFrameOptionsMiddleware',
    ]
ROOT_URLCONF = globals().get('ROOT_URLCONF', 'komunikahub.urls')
STATIC_URL = globals().get('STATIC_URL', 'static/')
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
MESSAGE_TAGS = {message_constants.ERROR: 'danger'}
