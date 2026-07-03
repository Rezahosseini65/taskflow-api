import time
from unittest.mock import patch

from django.db import connection, connections
from django.test import TransactionTestCase
from django.urls import reverse

from concurrent.futures import ThreadPoolExecutor, as_completed

from rest_framework.test import APITestCase, APIClient
from rest_framework import status

from .models import CustomUser


class UserRegisterViewTestCase(TransactionTestCase):

    def setUp(self):
        from .views import UserRegisterView
        UserRegisterView.throttle_classes = []

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

    @classmethod
    def tearDownClass(cls):
        connections.close_all()
        super().tearDownClass()

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

        def register():
            client = APIClient()
            try:
                return client.post(
                    self.register_url,
                    self.concurrent_data,
                    format="json"
                )
            finally:
                # بستن connection مربوط به همین Thread
                connections.close_all()

        with ThreadPoolExecutor(max_workers=num_requests) as executor:
            futures = [executor.submit(register) for _ in range(num_requests)]

            success_count = 0
            fail_count = 0

            for future in futures:
                response = future.result()

                if response.status_code == status.HTTP_201_CREATED:
                    success_count += 1
                elif response.status_code == status.HTTP_400_BAD_REQUEST:
                    fail_count += 1
                else:
                    self.fail(f"Unexpected status code: {response.status_code}")

        # بستن connection مربوط به Thread اصلی
        connections.close_all()

        user_count = CustomUser.objects.filter(
            email=self.concurrent_email
        ).count()

        self.assertEqual(user_count, 1)
        self.assertEqual(success_count, 1)
        self.assertEqual(fail_count, num_requests - 1)

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


class UserLoginViewTestCase(APITestCase):

    def setUp(self):
        self.login_url = reverse('user-login')
        self.valid_user_data = {
            "email": "test@example.com",
            "password": "StrongPassword123!"
        }

        # Create a valid user for login tests
        self.user = CustomUser.objects.create_user(
            email=self.valid_user_data["email"],
            password=self.valid_user_data["password"]
        )

        self.inactive_user = CustomUser.objects.create_user(
            email="inactive@example.com",
            password="StrongPassword123!",
            is_active=False
        )

    def test_login_success(self):
        """
        Test successful login with valid credentials
        """
        response = self.client.post(self.login_url, self.valid_user_data, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()["detail"], "Login successful")

        # Verify httponly cookies exist
        self.assertIn('access_token', response.cookies)
        self.assertIn('refresh_token', response.cookies)
        self.assertTrue(response.cookies['access_token']['httponly'])
        self.assertTrue(response.cookies['refresh_token']['httponly'])
        self.assertTrue(response.cookies['access_token']['samesite'])

        # Verify cookies are not empty
        self.assertNotEqual(response.cookies['access_token'].value, '')
        self.assertNotEqual(response.cookies['refresh_token'].value, '')

    def test_login_with_wrong_password(self):
        """
        Test login with incorrect password
        """
        data = {
            "email": self.valid_user_data["email"],
            "password": "WrongPassword123!"
        }
        response = self.client.post(self.login_url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("non_field_errors", response.json())
        # Ensure cookies are not set
        self.assertNotIn('access_token', response.cookies)

    def test_login_with_nonexistent_email(self):
        """
        Test login with non-existent email
        """
        data = {
            "email": "nonexistent@example.com",
            "password": "SomePassword123!"
        }
        response = self.client.post(self.login_url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("non_field_errors", response.json())

    def test_login_with_inactive_user(self):
        """
        Test login with inactive user
        """
        data = {
            "email": "inactive@example.com",
            "password": "StrongPassword123!"
        }
        response = self.client.post(self.login_url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("non_field_errors", response.json())

    def test_login_with_missing_email(self):
        """
        Test login without email
        """
        data = {
            "password": "StrongPassword123!"
        }
        response = self.client.post(self.login_url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("email", response.json())

    def test_login_with_missing_password(self):
        """
        Test login without password
        """
        data = {
            "email": "test@example.com"
        }
        response = self.client.post(self.login_url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("password", response.json())

    def test_login_with_empty_fields(self):
        """
        Test login with empty fields
        """
        data = {
            "email": "",
            "password": ""
        }
        response = self.client.post(self.login_url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("email", response.json())
        self.assertIn("password", response.json())

    def test_login_with_email_case_insensitivity(self):
        """
        Test login with email in different case
        """
        data = {
            "email": "TEST@Example.com",
            "password": "StrongPassword123!"
        }
        response = self.client.post(self.login_url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_login_with_email_whitespace(self):
        """
        Test login with email containing leading/trailing whitespace
        """
        data = {
            "email": "  test@example.com  ",
            "password": "StrongPassword123!"
        }
        response = self.client.post(self.login_url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()["detail"], "Login successful")

    @patch('taskflow.accounts.views.logger')
    def test_login_exception_handling_in_debug_mode(self, mock_logger):
        """
        Test error handling in DEBUG mode
        """
        from django.conf import settings
        settings.DEBUG = True

        # Simulate server error by patching generate_access_refresh_tokens
        with patch('taskflow.accounts.views.generate_access_refresh_tokens',
                   side_effect=Exception("Database connection error")):
            response = self.client.post(self.login_url, self.valid_user_data, format='json')

            self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)
            self.assertIn("An error occurred", response.json()["detail"])
            mock_logger.error.assert_called_once()

    def test_login_returns_correct_token_format(self):
        """
        Test returned token format
        """
        response = self.client.post(self.login_url, self.valid_user_data, format='json')

        access_token = response.cookies['access_token'].value
        refresh_token = response.cookies['refresh_token'].value

        # Tokens should be at least 20 characters long
        self.assertGreater(len(access_token), 20)
        self.assertGreater(len(refresh_token), 20)

        # Verify tokens are JWT (3 dot-separated parts)
        self.assertEqual(len(access_token.split('.')), 3)
        self.assertEqual(len(refresh_token.split('.')), 3)

    def test_login_does_not_modify_user_state(self):
        """
        Test that login does not modify user state
        """
        last_login_before = self.user.last_login

        response = self.client.post(self.login_url, self.valid_user_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.user.refresh_from_db()
        # last_login should not change as we don't update it in the view
        self.assertEqual(self.user.last_login, last_login_before)

    def test_login_with_special_characters_in_password(self):
        """
        Test login with password containing special characters
        """
        special_password = "P@ssw0rd!@#$%^&*()_+"
        user = CustomUser.objects.create_user(
            email="special@example.com",
            password=special_password
        )

        data = {
            "email": "special@example.com",
            "password": special_password
        }
        response = self.client.post(self.login_url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()["detail"], "Login successful")

    def test_login_with_long_email(self):
        """
        Test login with very long email
        """
        long_email = "a" * 50 + "@" + "b" * 50 + ".com"
        user = CustomUser.objects.create_user(
            email=long_email,
            password="StrongPassword123!"
        )

        data = {
            "email": long_email,
            "password": "StrongPassword123!"
        }
        response = self.client.post(self.login_url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_login_cookie_attributes(self):
        """
        Test cookie security attributes
        """
        response = self.client.post(self.login_url, self.valid_user_data, format='json')

        access_cookie = response.cookies['access_token']
        refresh_cookie = response.cookies['refresh_token']

        # Verify security attributes
        self.assertTrue(access_cookie.get('httponly', False))
        self.assertTrue(refresh_cookie.get('httponly', False))

        # Verify path
        self.assertEqual(access_cookie.get('path', '/'), '/')
        self.assertEqual(refresh_cookie.get('path', '/'), '/')

        # Verify samesite
        self.assertIn('samesite', access_cookie.keys())
        self.assertIn('samesite', refresh_cookie.keys())


class UserLoginViewTransactionTestCase(TransactionTestCase):

    def test_concurrent_logins(self):
        login_url = '/api/users/login/'

        def login(user_index):
            """Each thread operates independently"""
            try:
                connection.close()

                email = f"concurrent_test_{user_index}_{time.time()}@example.com"
                password = "StrongPass123!"

                user = CustomUser.objects.create_user(
                    email=email,
                    password=password
                )

                client = self.client_class()
                response = client.post(
                    login_url,
                    {'email': email, 'password': password},
                    format='json'
                )

                user.delete()

                return response.status_code, response.data if response.status_code != 200 else None

            except Exception as e:
                return 500, str(e)

            finally:
                connections.close_all()

        results = []
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(login, i) for i in range(5)]

            for future in as_completed(futures):
                status_code, data = future.result()
                results.append((status_code, data))

        for status_code, data in results:
            self.assertEqual(status_code, 200, f"Failed with data: {data}")

        connections.close_all()