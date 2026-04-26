# src/taskflow/celery.py
import os
from celery import Celery

# تنظیم ماژول تنظیمات Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'taskflow.settings.development')

app = Celery('taskflow')

# استفاده از تنظیمات Django برای پیکربندی Celery
app.config_from_object('django.conf:settings', namespace='CELERY')

# کشف خودکار تسک‌ها از اپ‌های نصب شده
app.autodiscover_tasks()


@app.task(bind=True, ignore_result=True)
def debug_task(self):
    print(f'Request: {self.request!r}')