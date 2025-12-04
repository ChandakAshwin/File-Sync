#!/usr/bin/env python3
import os
import sys
sys.path.insert(0, '/mnt/c/Users/Dell/Desktop/local/WokeloFileSync')

# Set environment variables for WSL
os.environ.update({
    'PYTHONPATH': '/mnt/c/Users/Dell/Desktop/local/WokeloFileSync',
    'BOX_CLIENT_ID': 'd2x3vj5kj7nt5n1awi1v3qkrhtipd7gw',
    'BOX_CLIENT_SECRET': 'iHnSHoNuCfSkgOEFKg8eYdOHihlbHiNI',
    'BOX_DEVELOPER_TOKEN': '8LmqQBEXKa5IrFJ3CuwtQA85Nw8se9uC',
    'REDIS_URL': 'redis://127.0.0.1:6379/0',
    'POSTGRES_USER': 'filesync',
    'POSTGRES_PASSWORD': 'password',
    'POSTGRES_HOST': '127.0.0.1',
    'POSTGRES_PORT': '5432',
    'POSTGRES_DB': 'filesync',
    'LOG_LEVEL': 'INFO'
})

print('Starting WSL Celery Worker...')

from workers.celery_worker_functional import app

if __name__ == '__main__':
    app.worker_main(['worker', '--loglevel=info', '--concurrency=1'])
