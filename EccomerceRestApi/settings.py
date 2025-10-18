import os
from datetime import timedelta
from pathlib import Path
from decouple import config


# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = config('SECRET_KEY',
                    default='django-insecure--#qd6azas=$(an^)e7w=k42=0e&b9)3)9m4@_s7l+da(0$lh44', cast=str)

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = config('DEBUG', default=False, cast=bool)

ALLOWED_HOSTS = ["*"]


# Application definition

INSTALLED_APPS = [
    'jazzmin',
    'django.contrib.sites',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # Third-party apps
    'allauth',
    'allauth.account',
    'allauth.socialaccount',
    'dj_rest_auth',
    'dj_rest_auth.registration',
    'rest_framework',
    'rest_framework.authtoken',
    'rest_framework_simplejwt',
    'rest_framework_simplejwt.token_blacklist',
    'django_filters',
    'django_countries',
    'drf_spectacular',
    
    # Local apps
    'common.apps.CommonConfig', # Common utils
    'userAuth.apps.UserAuthConfig',
    'users.apps.UsersConfig',
    'cart.apps.CartConfig',
    'products.apps.ProductsConfig',
    'shipping.apps.ShippingConfig',
    'orders.apps.OrdersConfig',
    'category.apps.CategoryConfig',
    'reviews.apps.ReviewsConfig',
    'wishlist.apps.WishlistConfig',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'allauth.account.middleware.AccountMiddleware',
]

ROOT_URLCONF = 'EccomerceRestApi.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates']
        ,
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'EccomerceRestApi.wsgi.application'


# Database
# https://docs.djangoproject.com/en/5.2/ref/settings/#databases

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql_psycopg2',
        'NAME': config('POSTGRES_DB', default='ecommerceDB', cast=str),
        'USER': config('POSTGRES_USER', default='postgres', cast=str),
        'PASSWORD': config('POSTGRES_PASSWORD', default='postgres', cast=str),
        'HOST': config('PG_HOST', default='localhost', cast=str),
        'PORT': config('PG_PORT', default=5432, cast=int),
    }
}


# Password validation
# https://docs.djangoproject.com/en/5.2/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

REST_FRAMEWORK = {
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework.authentication.TokenAuthentication',
        'rest_framework.authentication.SessionAuthentication',
    ],
    'DEFAULT_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer',
        'rest_framework.renderers.BrowsableAPIRenderer',
    ],
    'DEFAULT_PARSER_CLASSES': [
        'rest_framework.parsers.JSONParser',
        'rest_framework.parsers.FormParser',
        'rest_framework.parsers.MultiPartParser',
        'rest_framework.parsers.FileUploadParser',
    ],
    # Permissions
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticatedOrReadOnly',
    ],
    # Filtering
    'DEFAULT_FILTER_BACKENDS': [
        'django_filters.rest_framework.DjangoFilterBackend',
        'rest_framework.filters.SearchFilter',
        'rest_framework.filters.OrderingFilter',
    ],
    # Pagination
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 3,
}

REST_AUTH = {
    'LOGIN_SERIALIZER': 'userAuth.serializers.CustomLoginSerializer',
    'TOKEN_SERIALIZER': 'dj_rest_auth.serializers.TokenSerializer',
    'JWT_SERIALIZER': 'dj_rest_auth.serializers.JWTSerializer',
    'JWT_SERIALIZER_WITH_EXPIRATION': 'dj_rest_auth.serializers.JWTSerializerWithExpiration',
    'JWT_TOKEN_CLAIMS_SERIALIZER': 'rest_framework_simplejwt.serializers.TokenObtainPairSerializer',
    'USER_DETAILS_SERIALIZER': 'userAuth.serializers.ProfileDetailsUpdateSerializer',
    'PASSWORD_RESET_SERIALIZER': 'dj_rest_auth.serializers.PasswordResetSerializer',
    'PASSWORD_RESET_CONFIRM_SERIALIZER': 'userAuth.serializers.CustomPasswordResetConfirmSerializer',
    'PASSWORD_CHANGE_SERIALIZER': 'userAuth.serializers.CustomPasswordChangeSerializer',
    'REGISTER_SERIALIZER': 'userAuth.serializers.CustomRegisterSerializer',
    'REGISTER_PERMISSION_CLASSES': (
        'rest_framework.permissions.AllowAny',
    ),
    'TOKEN_MODEL': 'rest_framework.authtoken.models.Token',
    'TOKEN_CREATOR': 'dj_rest_auth.utils.default_create_token',
    'PASSWORD_RESET_USE_SITES_DOMAIN': False,
    'OLD_PASSWORD_FIELD_ENABLED': False,
    'LOGOUT_ON_PASSWORD_CHANGE': False,
    'SESSION_LOGIN': True,
    'USE_JWT': False,
    'JWT_AUTH_COOKIE': None,
    'JWT_AUTH_REFRESH_COOKIE': None,
    'JWT_AUTH_REFRESH_COOKIE_PATH': '/',
    'JWT_AUTH_SECURE': False,
    'JWT_AUTH_HTTPONLY': True,
    'JWT_AUTH_SAMESITE': 'Lax',
    'JWT_AUTH_RETURN_EXPIRATION': False,
    'JWT_AUTH_COOKIE_USE_CSRF': False,
    'JWT_AUTH_COOKIE_ENFORCE_CSRF_ON_UNAUTHENTICATED': False,
    'SEND_ACTIVATION_EMAIL': True,
    'SEND_CONFIRMATION_EMAIL': True,
}

# Use Token Authentication
REST_USE_JWT = False

# Add Token Authentication to default authentication classes
REST_FRAMEWORK['DEFAULT_AUTHENTICATION_CLASSES'] = [
    'rest_framework.authentication.TokenAuthentication',
    'rest_framework.authentication.SessionAuthentication',
]

# Logging configuration
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
    },
    'loggers': {
        '': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': True,
        },
    },
}

# JWT Auth
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=5),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=1),
    'ROTATE_REFRESH_TOKENS': False,
    'BLACKLIST_AFTER_ROTATION': True,
    'UPDATE_LAST_LOGIN': False,
}

SPECTACULAR_SETTINGS = {
    # Basic settings
    'TITLE': 'Blog API',
    'DESCRIPTION': 'API documentation for the Blog application',
    'VERSION': '1.0.0',
    'SCHEMA_PATH_PREFIX': '/api',
    'SCHEMA_PATH_PREFIX_TRIM': False,
    'SCHEMA_PATH_PREFIX_INCLUDES': ['/api/'],
    'SCHEMA_COERCE_PATH_PK_SUFFIX': True,
    'SCHEMA_COERCE_PATH_PK': True,
    'DEFAULT_GENERATOR_CLASS': 'drf_spectacular.generators.SchemaGenerator',
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',

    # UI Settings
    'SWAGGER_UI_SETTINGS': {
        'deepLinking': True,
        'persistAuthorization': True,
        'displayRequestDuration': True,
        'filter': True,
        'docExpansion': 'none',
        'defaultModelsExpandDepth': -1,
        'layout': 'BaseLayout',
        'syntaxHighlight.theme': 'monokai',
        'operationsSorter': 'method',
        'tagsSorter': 'alpha',
        'tryItOutEnabled': True,
        'displayOperationId': False,
        'showExtensions': True,
        'showCommonExtensions': True,
        'url': '/api/schema/',
        'validatorUrl': None,
        'supportedSubmitMethods': ['get', 'post', 'put', 'delete', 'patch'],
    },

    # UI Distribution (use CDN)
    'SWAGGER_UI_DIST': 'https://cdn.jsdelivr.net/npm/swagger-ui-dist@latest',
    'SWAGGER_UI_FAVICON_HREF': 'https://fastapi.tiangolo.com/img/favicon.png',
    'REDOC_DIST': 'https://cdn.jsdelivr.net/npm/redoc@latest',

    # Template settings
    'SWAGGER_UI_LAYOUT': 'StandaloneLayout',
    'SWAGGER_UI_CONFIG': {
        'deepLinking': True,
        'persistAuthorization': True,
        'displayRequestDuration': True,
        'filter': True,
    },

    # Add the missing script_url and other required template variables
    'TEMPLATE_VARIABLES': {
        'script_url': 'https://cdn.jsdelivr.net/npm/swagger-ui-dist@latest/swagger-ui-bundle.js',
        'swagger_ui_css': 'https://cdn.jsdelivr.net/npm/swagger-ui-dist@latest/swagger-ui.css',
        'swagger_ui_bundle': 'https://cdn.jsdelivr.net/npm/swagger-ui-dist@latest/swagger-ui-bundle.js',
        'swagger_ui_standalone': 'https://cdn.jsdelivr.net/npm/swagger-ui-dist@latest/swagger-ui-standalone-preset.js',
        'favicon_href': 'https://fastapi.tiangolo.com/img/favicon.png',
    },

    # Security
    'SECURITY_DEFINITIONS': {
        'Bearer': {
            'type': 'http',
            'scheme': 'bearer',
            'bearerFormat': 'JWT',
            'name': 'Authorization',
            'in': 'header',
        },
    },

    # Authentication
    'AUTHENTICATION_WHITELIST': [
        'rest_framework_simplejwt.authentication.JWTAuthentication',
        'rest_framework.authentication.SessionAuthentication',
        'rest_framework.authentication.BasicAuthentication',
    ],

    # Hooks
    'PREPROCESSING_HOOKS': [
        'drf_spectacular.hooks.preprocess_exclude_path_format',
    ],

    # Enums
    'ENUM_NAME_OVERRIDES': {
        'StatusEnum': 'posts.choices.STATUS_CHOICES',
    },

    # Other
    'COMPONENT_NO_READ_ONLY_REQUIRED': True,
}


# All auth
LOGIN_URL = '/api/auth/dj_rest_auth/login/'
LOGOUT_REDIRECT_URL = '/api/auth/dj_rest_auth/login/'
ACCOUNT_EMAIL_VERIFICATION = "mandatory"
ACCOUNT_CONFIRM_EMAIL_ON_GET = True
ACCOUNT_EMAIL_CONFIRMATION_EXPIRE_DAYS = 1
ACCOUNT_SIGNUP_FIELDS = {
    'email*': {
        'required': True,
        'label': 'Email',
        'placeholder': 'Enter your email address',
    },
    'email_confirm': {
        'required': True,
        'label': 'Confirm Email',
        'placeholder': 'Confirm your email address',
    },
}
ACCOUNT_LOGIN_METHODS = ["email"]
ACCOUNT_USER_MODEL_USERNAME_FIELD = None
ACCOUNT_EMAIL_CONFIRMATION_AUTHENTICATED_REDIRECT_URL = '/api/auth/dj_rest_auth/login/'
ACCOUNT_EMAIL_CONFIRMATION_ANONYMOUS_REDIRECT_URL = '/api/auth/dj_rest_auth/login/'
ACCOUNT_DEFAULT_HTTP_PROTOCOL = 'http'
# Allauth settings
ACCOUNT_UNIQUE_EMAIL = True
ACCOUNT_EMAIL_SUBJECT_PREFIX = 'Ecommerce Rest API - '
ACCOUNT_LOGOUT_ON_PASSWORD_CHANGE = True

# Phone number
PHONENUMBER_DEFAULT_REGION = 'PL'

# Internationalization
# https://docs.djangoproject.com/en/5.2/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_TZ = True


STATIC_URL = 'static/'
MEDIA_URL = 'media/'

STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')

# Default primary key field type
# https://docs.djangoproject.com/en/5.2/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# User model
AUTH_USER_MODEL = "users.User"

# Email backend for development
if DEBUG:
    print("\n=== DEBUG: Using console email backend ===")
    EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

    SITE_DOMAIN = 'localhost:8000'
    SITE_NAME = 'Localhost'

    # Ensure the logs directory exists
    log_dir = BASE_DIR / "logs"
    log_dir.mkdir(exist_ok=True)

    # LOGGING = {
    #     "version": 1,
    #     "disable_existing_loggers": False,
    #     "formatters": {
    #         "verbose": {
    #             "format": "{levelname} {asctime} {module} {process:d} {thread:d} {message}",
    #             "style": "{",
    #         },
    #         "simple": {
    #             "format": "{levelname} {message}",
    #             "style": "{",
    #         },
    #         "console": {
    #             "format": "%(asctime)s %(name)-12s %(levelname)-8s %(message)s",
    #         },
    #         "file": {
    #             "format": "%(asctime)s %(name)-15s %(levelname)-8s %(message)s",
    #         },
    #     },
    #     "filters": {
    #         "require_debug_true": {
    #             "()": "django.utils.log.RequireDebugTrue",
    #         },
    #     },
    #     "handlers": {
    #         "console": {
    #             "level": "DEBUG",
    #             "class": "logging.StreamHandler",
    #             "formatter": "console",
    #         },
    #         "file": {
    #             "level": "INFO",
    #             "class": "logging.handlers.RotatingFileHandler",
    #             "formatter": "file",
    #             "filename": BASE_DIR / "logs/django.log",
    #             "maxBytes": 1024 * 1024 * 5,  # 5 MB
    #             "backupCount": 5,
    #         },
    #         "mail_admins": {
    #             "level": "ERROR",
    #             "class": "django.utils.log.AdminEmailHandler",
    #         },
    #     },
    #     "loggers": {
    #         # Root logger - captures everything
    #         "": {
    #             "handlers": ["console", "file"],
    #             "level": "INFO",
    #             "propagate": True,
    #         },
    #         # Django framework loggers
    #         "django": {
    #             "handlers": ["console", "file"],
    #             "level": "INFO",
    #             "propagate": False,
    #         },
    #         # Database queries (set to DEBUG to see SQL queries)
    #         "django.db.backends": {
    #             "handlers": ["console"],
    #             "level": "INFO",
    #             "propagate": False,
    #         },
    #         # Allauth logging
    #         "allauth": {
    #             "handlers": ["console", "file"],
    #             "level": "DEBUG",
    #             "propagate": False,
    #         },
    #         # Email logging
    #         "django.core.mail": {
    #             "handlers": ["console", "file"],
    #             "level": "DEBUG",
    #             "propagate": False,
    #         },
    #         # Your apps logging
    #         "users": {
    #             "handlers": ["console", "file"],
    #             "level": "DEBUG",
    #             "propagate": False,
    #         },
    #         "posts": {
    #             "handlers": ["console", "file"],
    #             "level": "DEBUG",
    #             "propagate": False,
    #         },
    #         # Add other apps as needed
    #     },
    # }
else:
    SITE_DOMAIN = config('SITE_DOMAIN', default='localhost:8000')
    SITE_NAME = config('SITE_NAME', default='Localhost')

    EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
    EMAIL_HOST = config('EMAIL_HOST', default='smtp.gmail.com')
    EMAIL_PORT = config('EMAIL_PORT', default=587)
    EMAIL_USE_TLS = True
    EMAIL_HOST_USER = config('EMAIL_HOST_USER', default='')
    EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD', default='')
    DEFAULT_FROM_EMAIL = config('DEFAULT_FROM_EMAIL', default='noreply@yourdomain.com')

