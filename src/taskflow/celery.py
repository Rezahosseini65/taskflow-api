import os
from celery import Celery

environment = os.environ.get('DJANGO_SETTINGS_MODULE', 'taskflow.settings.development')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', environment)

app = Celery('taskflow')


app.config_from_object('django.conf:settings', namespace='CELERY')

app.autodiscover_tasks()

@app.task(bind=True)
def debug_task(self):
    print(f'Request: {self.request!r}')