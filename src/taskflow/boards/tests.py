from unittest import mock
from unittest.mock import patch

from django.urls import reverse
from django.utils.text import slugify
from django.core.cache import cache

from rest_framework.test import APITestCase
from rest_framework import status

from .models import Board
from taskflow.accounts.models import CustomUser

# Create your tests here.

#-------------------------------------------Create Board Test---------------------------------------

class CreateBoardViewTest(APITestCase):

    def setUp(self):
        self.owner = CustomUser.objects.create_user(
            email='owner@gmail.com',
            password='passTest1'
        )
        self.member1 = CustomUser.objects.create_user(
            email='member1@gmail.com',
            password='passTest1'
        )
        self.member2 = CustomUser.objects.create_user(
            email='member2@gmail.com',
            password='passTest1'
        )
        self.url = reverse('board-create')

    def auth_client(self):
        self.client.force_authenticate(user=self.owner)

    def test_unauthenticated_user_returns_401(self):
        payload = {
            'name':'my board',
            'slug':'my-board',
            'members':[self.member1.id, self.member2.id]
        }

        response = self.client.post(self.url, payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_invalid_payload_returns_400(self):
        self.auth_client()

        payload = {
            "name":"",
            "members":[self.member1.id]
        }

        response = self.client.post(self.url, payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('name', response.data)

    def test_create_board_success_with_slug_returns_201_and_slug_same(self):
        self.auth_client()

        payload = {
            'name':'board test',
            'slug':'custom-slug',
            'members':[self.member1.id, self.member2.id]
        }

        response = self.client.post(self.url, payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        board = Board.objects.get(id=response.data["id"])

        self.assertEqual(board.slug, "custom-slug")
        self.assertEqual(board.owner, self.owner)
        self.assertTrue(board.members.filter(id=self.member1.id).exists())
        self.assertTrue(board.members.filter(id=self.member2.id).exists())

    def test_create_board_success_without_slug_slugified_from_name(self):
        self.auth_client()

        payload = {
            "name": "My Board (Test)",
            "members": [self.member1.id, self.member2.id],
        }

        resp = self.client.post(self.url, payload, format="json")
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

        board = Board.objects.get(id=resp.data["id"])
        expected_slug = slugify(payload["name"], allow_unicode=True)

        self.assertEqual(board.slug, expected_slug)
        self.assertEqual(board.owner, self.owner)

        self.assertTrue(board.members.filter(id=self.member1.id).exists())
        self.assertTrue(board.members.filter(id=self.member2.id).exists())

    def test_create_board_success_without_members(self):
        self.auth_client()

        payload = {
            "name": "Board No Members",
            "slug": "no-members",
        }

        resp = self.client.post(self.url, payload, format="json")

        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)

        board = Board.objects.get(id=resp.data["id"])

        self.assertEqual(board.slug, "no-members")
        self.assertEqual(board.owner, self.owner)
        self.assertEqual(board.members.count(), 0)

    def test_create_board_when_exception_returns_500_in_debug(self):
        self.auth_client()

        payload = {
            "name": "Board",
            "slug": "board",
            "members": [self.member1.id],
        }

        # اینجا متد Board.objects.create را mock می‌کنیم تا Exception بدهد.
        with mock.patch(
                "taskflow.boards.models.Board.objects.create",
                side_effect=Exception("DB error"),
        ):
            # settings.DEBUG را هم mock کنیم
            with mock.patch("django.conf.settings.DEBUG", True):
                resp = self.client.post(self.url, payload, format="json")

        self.assertEqual(resp.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)
        self.assertIn("detail", resp.data)
        self.assertIn("DB error", resp.data["detail"])


#-------------------------------------------Owner Board List View Test---------------------------------------


class OwnerBoardListViewTest(APITestCase):

    def setUp(self):
        self.owner1 = CustomUser.objects.create_user(
            email='owner1@test.com',
            password='testPass123'
        )
        self.owner2 = CustomUser.objects.create_user(
            email='owner2@test.com',
            password='testPass123'
        )

        self.board1 = Board.objects.create(
            name='board1',
            slug='board-1',
            owner=self.owner1
        )
        self.board2 = Board.objects.create(
            name='board2',
            slug='board-2',
            owner=self.owner1
        )
        self.board3 = Board.objects.create(
            name='board3',
            slug='board-3',
            owner=self.owner2
        )

        self.url = reverse('board-owned-list')
        cache.clear()

    def auth_owner1(self):
        self.client.force_authenticate(user=self.owner1)

    def auth_owner2(self):
        self.client.force_authenticate(user=self.owner2)

    def test_get_boards_authenticated_success(self):
        """
        Test authenticated user gets their own boards
        """
        self.auth_owner1()

        response = self.client.get(self.url, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 2)

        for board in response.data:
            self.assertEqual(board["owner"]["id"], self.owner1.id)

    def test_get_boards_empty_list(self):
        """
        Test user with no boards gets empty list
        """
        owner3 = CustomUser.objects.create_user(
            email='owner3@test.com',
            password='testPass123'
        )
        self.client.force_authenticate(user=owner3)

        response = self.client.get(self.url, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, [])

    def test_unauthenticated_user(self):
        """
        Test unauthenticated request is rejected
        """
        response = self.client.get(self.url, format='json')

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_cache_is_used_first_time(self):
        """
        Test that data is cached on first request
        """
        self.auth_owner1()

        with patch('taskflow.boards.views.cache.get') as mock_cache_get, \
             patch('taskflow.boards.views.cache.set') as mock_cache_set :

            mock_cache_get.return_value = None

            response = self.client.get(self.url, format='json')

            mock_cache_get.assert_called_once_with(f'user_owner_boards_{self.owner1.id}')
            mock_cache_set.assert_called_once()

            self.assertEqual(
                mock_cache_set.call_args[0][0],
         f"user_owner_boards_{self.owner1.id}"
            )
            self.assertEqual(mock_cache_set.call_args[0][2], 60 * 60 * 24)

            self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_cache_is_used_subsequent_requests(self):
        """
        Test that cached data is returned on subsequent requests
        """
        self.auth_owner1()
        response1 = self.client.get(self.url, format='json')

        Board.objects.filter(owner=self.owner1).delete()

        response2 = self.client.get(self.url, format='json')

        self.assertEqual(response2.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response2.data), 2)
        self.assertIsInstance(response2.data, list)

    def test_cache_key_is_user_specific(self):
        """T
        est cache keys are unique per user
        """
        self.auth_owner1()
        response1 = self.client.get(self.url, format='json')

        self.auth_owner2()
        response2 = self.client.get(self.url, format='json')

        key1 = f"user_owner_boards_{self.owner1.id}"
        key2 = f"user_owner_boards_{self.owner2.id}"

        cached_data1 = cache.get(key1)
        cached_data2 = cache.get(key2)

        self.assertIsNotNone(cached_data1)
        self.assertIsNotNone(cached_data2)

        # User1's cache should contain 2 boards
        self.assertEqual(len(cached_data1), 2)

        # User2's cache should contain 1 board
        self.assertEqual(len(cached_data2), 1)
        self.assertEqual(cached_data2[0]["name"], "board3")

    def test_select_related_optimization(self):
        """
        Test that select_related is used to avoid N+1 queries
        """
        self.auth_owner1()

        with self.assertNumQueries(1):
            response = self.client.get(self.url, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    @patch('taskflow.boards.views.Board.objects.filter')
    def test_database_error_handled(self, mock_filter):
        """
        Test exception during DB query is handled gracefully
        """
        mock_filter.side_effect = Exception("DB connection error")

        self.auth_owner1()

        with self.assertLogs("taskflow.boards.views", level="ERROR") as log:
            response = self.client.get(self.url, format='json')

        self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)
        self.assertIn("detail", response.data)
        self.assertIn("An internal server error occurred.", response.data["detail"])

        # Check error was logged
        self.assertIn("List board failed", log.output[0])
        self.assertIn("DB connection error", log.output[0])

    @patch("taskflow.boards.views.Board.objects.filter")
    def test_debug_mode_returns_detailed_error(self, mock_filter):
        """
        Test when DEBUG=True, detailed error is returned
        """
        mock_filter.side_effect = Exception("Specific error: connection timeout")

        self.auth_owner1()

        with patch("taskflow.boards.views.settings.DEBUG", True):
            response = self.client.get(self.url, format='json')

        self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)
        self.assertIn("detail", response.data)
        self.assertIn("Specific error: connection timeout", response.data["detail"])

    def test_board_ownership_isolated(self):
        """
        Test user cannot see another user's boards via cache or DB
        """
        # User2 fetches their boards
        self.auth_owner2()

        response = self.client.get(self.url, format='json')
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["name"], "board3")

        # Verify user1's data isn't in user2's response
        user1_board_name = ["board1", "board2"]
        for board in response.data:
            self.assertNotIn(board["name"], user1_board_name)


#-------------------------------------------Owner Board Detail View Test---------------------------------------


class OwnerBoardDetailViewTest(APITestCase):

    def setUp(self):
        cache.clear()

        self.owner = CustomUser.objects.create_user(
            email='owner@example.com',
            password='ownerPass123'
        )

        self.other_user = CustomUser.objects.create_user(
            email='other@example.com',
            password='otherPass123'
        )

        self.board = Board.objects.create(
            name='Test Board',
            slug='test-board',
            description='Test Description',
            owner=self.owner
        )

        self.board.members.add(self.other_user)

        self.url = reverse('board-owned-detail', kwargs={'pk': self.board.pk})

    def tearDown(self):
        cache.clear()

    def test_get_board_success_by_owner(self):
        """تست موفقیت آمیز دریافت برد توسط مالک"""
        self.client.force_authenticate(user=self.owner)

        response = self.client.get(self.url, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['id'], self.board.id)
        self.assertEqual(response.data['name'], self.board.name)
        self.assertEqual(response.data['owner']['id'], self.owner.id)
        self.assertIn('members', response.data)

    def test_get_board_by_non_owner_returns_404(self):
        """تست دریافت برد توسط کاربر غیر مالک - باید 404 برگردد"""
        self.client.force_authenticate(user=self.other_user)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_get_board_unauthenticated_returns_401(self):
        """تست دریافت برد بدون احراز هویت - باید 401 برگردد"""
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_get_non_existent_board_returns_404(self):
        """تست دریافت برد ناموجود"""
        self.client.force_authenticate(user=self.owner)
        invalid_url = reverse('board-owned-detail', kwargs={'pk': 99999})

        response = self.client.get(invalid_url)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_cache_works_first_request(self):
        """تست اینکه اولین درخواست داده را در کش ذخیره می‌کند"""

        self.client.force_authenticate(user=self.owner)

        cache.clear()

        response1 = self.client.get(self.url)

        # بررسی اینکه داده در کش ذخیره شده
        cache_key = f'owner_board_detail_{self.board.pk}_user_{self.owner.id}'

        cached_data = cache.get(cache_key)

        self.assertIsNotNone(cached_data)
        self.assertEqual(cached_data['id'], self.board.id)
        self.assertEqual(response1.data, cached_data)

    def test_cache_returns_cached_data_on_second_request(self):
        """تست اینکه درخواست دوم داده را از کش برمی دارد"""
        self.client.force_authenticate(user=self.owner)

        _ = self.client.get(self.url)

        Board.objects.get(id=self.board.id).delete()

        response2 = self.client.get(self.url)

        self.assertEqual(response2.status_code, status.HTTP_200_OK)
        self.assertEqual(response2.data["id"], self.board.id)

    def test_different_users_have_different_caches(self):
        other_board = Board.objects.create(
            name='Other Board',
            slug='other-board',
            owner=self.other_user
        )
        other_url = reverse('board-owned-detail', kwargs={'pk': other_board.pk})

        self.client.force_authenticate(user=self.owner)
        self.client.get(self.url)

        self.client.force_authenticate(user=self.other_user)
        self.client.get(other_url)

        cache_key_owner = f'owner_board_detail_{self.board.pk}_user_{self.owner.id}'
        cache_key_other = f'owner_board_detail_{other_board.pk}_user_{self.other_user.id}'

        self.assertIsNotNone(cache.get(cache_key_owner))
        self.assertIsNotNone(cache.get(cache_key_other))
        self.assertNotEqual(cache_key_owner, cache_key_other)

    @patch('taskflow.boards.views.cache.set')
    def test_cache_set_called_with_correct_timeout(self, mock_cache_set):
        self.client.force_authenticate(user=self.owner)

        self.client.get(self.url)

        call_args = mock_cache_set.call_args
        self.assertIsNotNone(call_args)
        self.assertEqual(call_args[0][2], 60 * 15)

    def test_select_related_and_prefetch_related_optimization(self):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        self.client.force_authenticate(user=self.owner)

        with CaptureQueriesContext(connection) as queries:
            self.client.get(self.url)

        self.assertLess(len(queries.captured_queries), 3)

        owner_loaded = any(
            '"owner"' in query['sql'].lower() or 'owner_id' in query['sql'].lower()
            for query in queries.captured_queries
        )
        self.assertTrue(owner_loaded)

    def test_members_only_contains_id_and_email(self):
        self.client.force_authenticate(user=self.owner)

        response = self.client.get(self.url)

        if 'members' in response.data and len(response.data['members']) > 0:
            member = response.data['members'][0]
            self.assertIn('id', member)
            self.assertIn('email', member)
            self.assertNotIn('password', member)

    def test_cache_invalidation_on_board_update(self):
        self.client.force_authenticate(user=self.owner)

        response1 = self.client.get(self.url)

        self.board.name = "Updated Title"
        self.board.save()

        response2 = self.client.get(self.url)

        self.assertEqual(response2.data['name'], 'Test Board')
        self.assertNotEqual(response2.data['name'], 'Updated Title')