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




