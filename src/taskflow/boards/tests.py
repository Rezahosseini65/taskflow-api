from unittest import mock
from unittest.mock import patch

from django.conf import settings
from django.urls import reverse
from django.utils.text import slugify
from django.core.cache import cache

from rest_framework.test import APITestCase, APIClient
from rest_framework import status

from .models import Board
from .views import MemberBoardListView
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


#-------------------------------------------Member Board List View Test---------------------------------------

class MemberBoardListViewTests(APITestCase):

    def setUp(self):
        """Setup run before each test"""
        # Clear cache before each test
        cache.clear()

        # Create users
        self.user1 = CustomUser.objects.create_user(
            email='test1@example.com',
            password='testPass123'
        )

        self.user2 = CustomUser.objects.create_user(
            email='test2@example.com',
            password='testPass123'
        )

        self.user3 = CustomUser.objects.create_user(
            email='test3@example.com',
            password='testPass123'
        )

        # URL for the view
        self.url = reverse('board-member-list')

        # Authenticate client
        self.client = APIClient()
        self.client.force_authenticate(user=self.user1)

    def tearDown(self):
        """Cleanup after each test"""
        cache.clear()

    # ========== Authentication Tests ==========

    def test_unauthenticated_access_returns_401(self):
        """Test that unauthenticated users receive 401 Unauthorized"""
        client = APIClient()  # Unauthenticated client
        response = client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_authenticated_access_returns_200(self):
        """Test that authenticated users can access the endpoint"""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # ========== Member Boards Retrieval Tests ==========

    def test_get_member_boards_success(self):
        """Test successfully retrieving boards where user is a member"""
        # Create boards where user1 is member (not owner)
        board1 = Board.objects.create(
            name="Member Board 1",
            slug="member-board-1",
            owner=self.user2
        )
        board1.members.add(self.user1)

        board2 = Board.objects.create(
            name="Member Board 2",
            slug="member-board-2",
            owner=self.user3
        )
        board2.members.add(self.user1)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 2)

        # Verify board data
        board_ids = [board['id'] for board in response.data]
        self.assertIn(board1.id, board_ids)
        self.assertIn(board2.id, board_ids)

    def test_excludes_boards_owned_by_user(self):
        """Test that boards owned by the user are not included"""
        # Board owned by user1 (should be excluded)
        owned_board = Board.objects.create(
            name="My Own Board",
            slug="my-own-board",
            owner=self.user1
        )
        owned_board.members.add(self.user2)

        # Board where user1 is member (should be included)
        member_board = Board.objects.create(
            name="Member Board",
            slug="member-board",
            owner=self.user2
        )
        member_board.members.add(self.user1)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['id'], member_board.id)
        self.assertNotEqual(response.data[0]['id'], owned_board.id)

    def test_excludes_boards_where_user_is_both_owner_and_member(self):
        """Test that boards where user is owner are excluded even if also member"""
        board = Board.objects.create(
            name="Owner Board",
            slug="owner-board",
            owner=self.user1
        )
        board.members.add(self.user1)  # Add as member too
        board.members.add(self.user2)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 0)

    def test_empty_member_boards_list(self):
        """Test response when user has no member boards"""
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, [])

    def test_member_boards_for_different_users(self):
        """Test that different users see different member boards"""
        # Create boards for user1
        board1 = Board.objects.create(
            name="User1 Member Board",
            slug="user1-member",
            owner=self.user2
        )
        board1.members.add(self.user1)

        # Create boards for user2
        board2 = Board.objects.create(
            name="User2 Member Board",
            slug="user2-member",
            owner=self.user1
        )
        board2.members.add(self.user2)

        # User1 sees only board1
        response1 = self.client.get(self.url)
        self.assertEqual(len(response1.data), 1)
        self.assertEqual(response1.data[0]['id'], board1.id)

        # User2 sees only board2
        self.client.force_authenticate(user=self.user2)
        response2 = self.client.get(self.url)
        self.assertEqual(len(response2.data), 1)
        self.assertEqual(response2.data[0]['id'], board2.id)

    # ========== Serializer Data Format Tests ==========

    def test_response_contains_expected_fields(self):
        """Test that response contains all expected fields from serializer"""
        board = Board.objects.create(
            name="Test Board",
            slug="test-board",
            owner=self.user2
        )
        board.members.add(self.user1)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        board_data = response.data[0]

        # Check main fields
        expected_fields = {'id', 'name', 'slug', 'created_at', 'owner'}
        self.assertTrue(expected_fields.issubset(board_data.keys()))

        # Check owner nested fields
        self.assertIn('id', board_data['owner'])
        self.assertIn('email', board_data['owner'])

    def test_owner_data_is_nested_correctly(self):
        """Test that owner data is properly nested in response"""
        board = Board.objects.create(
            name="Test Board",
            slug="test-board",
            owner=self.user2
        )
        board.members.add(self.user1)

        response = self.client.get(self.url)

        owner_data = response.data[0]['owner']
        self.assertEqual(owner_data['id'], self.user2.id)
        self.assertEqual(owner_data['email'], self.user2.email)

    # ========== Cache Tests ==========

    def test_cache_is_used_on_subsequent_requests(self):
        """Test that cached data is used on second request"""
        board = Board.objects.create(
            name="Cached Board",
            slug="cached-board",
            owner=self.user2
        )
        board.members.add(self.user1)

        # First request - should hit database
        with self.assertNumQueries(1):  # Only one query expected
            response1 = self.client.get(self.url)

        # Second request - should use cache (no database query)
        with self.assertNumQueries(0):  # No database queries
            response2 = self.client.get(self.url)

        self.assertEqual(response1.data, response2.data)
        self.assertEqual(response1.status_code, status.HTTP_200_OK)

    def test_cache_is_cleared_correctly_for_different_users(self):
        """Test that different users have different cache entries"""
        board1 = Board.objects.create(
            name="User1 Board",
            slug="user1-board",
            owner=self.user2
        )
        board1.members.add(self.user1)

        # First user request
        response1 = self.client.get(self.url)

        # Switch to second user
        self.client.force_authenticate(user=self.user2)
        board2 = Board.objects.create(
            name="User2 Board",
            slug="user2-board",
            owner=self.user1
        )
        board2.members.add(self.user2)

        response2 = self.client.get(self.url)

        # Different users should get different data
        self.assertNotEqual(response1.data, response2.data)

    def test_cache_expiry_time(self):
        """Test that cache is set with correct expiry time"""
        board = Board.objects.create(
            name="Cache Expiry Test",
            slug="cache-expiry",
            owner=self.user2
        )
        board.members.add(self.user1)

        with patch('django.core.cache.cache.set') as mock_cache_set:
            response = self.client.get(self.url)

            # Check that cache.set was called with correct timeout
            mock_cache_set.assert_called_once()
            call_args = mock_cache_set.call_args
            timeout = call_args[0][2]  # Third argument is timeout
            self.assertEqual(timeout, 60 * 15)  # 15 minutes

    # ========== Query Optimization Tests ==========

    def test_select_related_is_used(self):
        """Test that select_related is used to prevent N+1 queries"""
        # Create multiple boards
        for i in range(5):
            board = Board.objects.create(
                name=f"Board {i}",
                slug=f"board-{i}",
                owner=self.user2
            )
            board.members.add(self.user1)

        # Should only make 1 query (with select_related)
        with self.assertNumQueries(1):
            response = self.client.get(self.url)

        self.assertEqual(len(response.data), 5)

    def test_only_fields_are_selected(self):
        """Test that only necessary fields are selected from database"""
        board = Board.objects.create(
            name="Optimized Board",
            slug="optimized-board",
            owner=self.user2,
            description="This should not be selected",  # Not in only() fields
        )
        board.members.add(self.user1)

        response = self.client.get(self.url)

        # Response should only have the fields from only()
        board_data = response.data[0]
        self.assertIn('id', board_data)
        self.assertIn('name', board_data)
        self.assertIn('slug', board_data)
        self.assertIn('created_at', board_data)
        self.assertIn('owner', board_data)

        # Fields not in only() should not be in response
        self.assertNotIn('description', board_data)

    # ========== Error Handling Tests ==========

    @patch('taskflow.boards.views.Board.objects.filter')
    def test_database_error_returns_500(self, mock_filter):
        """Test that database errors return 500 status code"""
        mock_filter.side_effect = Exception("Database connection error")

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)
        self.assertIn('detail', response.data)

    @patch('taskflow.boards.views.Board.objects.filter')
    def test_database_error_hides_details_in_production(self, mock_filter, ):
        """Test that detailed error is hidden when DEBUG=False"""
        settings.DEBUG = False
        mock_filter.side_effect = Exception("Sensitive database error")

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)
        self.assertEqual(
            response.data['detail'],
            "An internal server error occurred."
        )

    # ========== Permission Classes Tests ==========

    def test_permission_classes_are_set(self):
        """Test that IsAuthenticated permission class is set"""
        from rest_framework.permissions import IsAuthenticated

        view = MemberBoardListView()
        self.assertTrue(any(
            issubclass(perm, IsAuthenticated)
            for perm in view.permission_classes
        ))

    # ========== Edge Cases Tests ==========

    def test_many_member_boards_performance(self):
        """Test performance with many boards (should use select_related)"""
        # Create 20 boards
        for i in range(20):
            board = Board.objects.create(
                name=f"Board {i}",
                slug=f"board-{i}",
                owner=self.user2
            )
            board.members.add(self.user1)

        with self.assertNumQueries(1):  # Should still be only 1 query
            response = self.client.get(self.url)

        self.assertEqual(len(response.data), 20)

    def test_user_is_member_of_boards_with_same_owner(self):
        """Test multiple boards with same owner"""
        # Create 3 boards all owned by user2
        boards = []
        for i in range(3):
            board = Board.objects.create(
                name=f"Board {i}",
                slug=f"board-{i}",
                owner=self.user2
            )
            board.members.add(self.user1)
            boards.append(board)

        response = self.client.get(self.url)

        self.assertEqual(len(response.data), 3)
        response_ids = [b['id'] for b in response.data]
        for board in boards:
            self.assertIn(board.id, response_ids)

    def test_cache_key_format(self):
        """Test the cache key format"""
        view_instance = MemberBoardListView()
        cache_key = view_instance.get_cache_key(self.user1.id)
        self.assertEqual(cache_key, f'member_board_list_user_{self.user1.id}')

        # Different user should have different key
        cache_key_user2 = view_instance.get_cache_key(self.user2.id)
        self.assertNotEqual(cache_key, cache_key_user2)

    def test_response_content_type(self):
        """Test that response has correct content type"""
        response = self.client.get(self.url)
        self.assertEqual(response['Content-Type'], 'application/json')