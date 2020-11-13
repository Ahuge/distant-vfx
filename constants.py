# Filesystem path constants
CONFIG_PATH = './config.yml'

# Template constants
TC_PATTERN = r'\d{2}:\d{2}:\d{2}:\d{2}'

# Media-related constants
FPS = 24

# Logging configuration.
LOG_SETTINGS = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'detailed': {
            'format': '%(asctime)s :: %(levelname)s :: %(name)s :: %(filename)s, line %(lineno)s :: %(funcName)s :: '
                      '%(message)s'
        },
    },
    'handlers': {
        'default': {
            'class': 'logging.handlers.TimedRotatingFileHandler',
            'level': 'DEBUG',
            'formatter': 'detailed',
            'filename': 'log/debug.log',
            'encoding': 'utf-8',
            'interval': 1,
            'when': 'midnight',
            'backupCount': 5
        },
        'info': {
            'class': 'logging.handlers.TimedRotatingFileHandler',
            'level': 'INFO',
            'formatter': 'detailed',
            'filename': 'log/info.log',
            'encoding': 'utf-8',
            'interval': 1,
            'when': 'midnight',
            'backupCount': 5
        },
        'session': {
            'class': 'logging.FileHandler',
            'level': 'DEBUG',
            'formatter': 'detailed',
            'filename': 'log/session.log',
            'mode': 'w',
            'encoding': 'utf-8',
        }
    },
    'loggers': {
        '': {
            'handlers': ['default', 'info', 'session'],
            'level': 'DEBUG',
            'propagate': True
        }
    }
}