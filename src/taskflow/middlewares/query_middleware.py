# middleware.py
import time
from django.db import connection


class QueryCountMiddleware:
    """Middleware برای نمایش تعداد کوئری‌های هر درخواست"""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # پاک کردن کوئری‌های قبلی
        connection.queries_log.clear()

        # اجرای درخواست
        start_time = time.time()
        response = self.get_response(request)
        end_time = time.time()

        # محاسبه آمار
        query_count = len(connection.queries)
        exec_time = (end_time - start_time) * 1000

        # فقط برای API درخواست‌ها نمایش بده
        if request.path.startswith('/api/'):
            print(f"\n{'=' * 60}")
            print(f"📊 API Request: {request.method} {request.path}")
            print(f"✅ Status Code: {response.status_code}")
            print(f"📈 Query Count: {query_count}")
            print(f"⏱️  Total Time: {exec_time:.2f} ms")
            print(f"{'=' * 60}\n")

        return response