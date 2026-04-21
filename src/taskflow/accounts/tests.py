import time

from django.urls import reverse

from concurrent.futures import ThreadPoolExecutor

from rest_framework.test import APITestCase
from rest_framework import status

from .models import CustomUser


class UserRegisterViewTestCase(APITestCase):

    def setUp(self):
        self.register_url = reverse('user-register')
        self.valid_data = {
            "email": "test@example.com",
            "password": "StrongPassword123",
            "confirm_password": "StrongPassword123"
        }

        self.concurrent_email = "concurrent_test@example.com"
        self.concurrent_data = {
            "email": self.concurrent_email,
            "password": "StrongPassword123",
            "confirm_password": "StrongPassword123"
        }

    def test_registration_success(self):
        start = time.time()
        response = self.client.post(self.register_url, self.valid_data, format='json')
        response_time = time.time() - start

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn("detail", response.json())

        #self.assertLess(response_time, 3.0, f"Response too slow: {response_time:.3f}s")
        print(f"\nRegistration response time: {response_time:.3f}s")

        user = CustomUser.objects.get(email=self.valid_data["email"])

        self.assertTrue(user.password.startswith("pbkdf2_sha256$"))
        self.assertTrue(user.check_password(self.valid_data["password"]))

        self.assertTrue(response.cookies['access_token']['httponly'])
        self.assertTrue(response.cookies['refresh_token']['httponly'])

    def test_concurrency_registration(self):
        num_requests = 10

        with ThreadPoolExecutor(max_workers=num_requests) as executor:
            futures = [executor.submit(self.client.post, self.register_url, self.concurrent_data, format='json') for _
                       in range(num_requests)]

            success_count = 0
            fail_count = 0

            for future in futures:
                response = future.result()
                if response.status_code == status.HTTP_201_CREATED:
                    success_count += 1
                elif response.status_code == status.HTTP_400_BAD_REQUEST:
                    fail_count += 1
                else:
                    fail_count += 1
                    self.fail(f"Unexpected status code: {response.status_code}")

        user_count = CustomUser.objects.filter(email=self.concurrent_email).count()
        self.assertEqual(user_count, 1, "Exactly one user should be created.")
        self.assertEqual(success_count, 1, "Only one registration should succeed.")
        self.assertEqual(fail_count, num_requests - 1, "Other registrations should fail due to duplicate email.")

        user = CustomUser.objects.get(email=self.concurrent_email)
        self.assertTrue(user.password.startswith("pbkdf2_sha256$"))

    def test_duplicate_email(self):
        # This test should run before concurrency test if we don't mock create_user for it.
        CustomUser.objects.create_user(email="test@example.com", password="Password123!")
        response = self.client.post(self.register_url, self.valid_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(CustomUser.objects.filter(email="test@example.com").count(), 1)

    def test_weak_password(self):
        data = self.valid_data.copy()
        data["password"] = "123"
        data["confirm_password"] = "123"
        response = self.client.post(self.register_url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_password_mismatch(self):
        data = self.valid_data.copy()
        data["confirm_password"] = "DifferentPass123!"
        response = self.client.post(self.register_url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_email_trim_and_case_insensitivity(self):
        data = self.valid_data.copy()
        data["email"] = "  TEST@Example.com  "
        response = self.client.post(self.register_url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        # Ensure that after trimming and case insensitivity, the correct email is stored/found
        user_count_stored = CustomUser.objects.filter(email="test@example.com").count()
        self.assertEqual(user_count_stored, 1, "User with normalized email should be found.")
        # Also check if the actual email in the DB is the normalized one
        user_in_db = CustomUser.objects.get(email="test@example.com")
        self.assertEqual(user_in_db.email, "test@example.com")
