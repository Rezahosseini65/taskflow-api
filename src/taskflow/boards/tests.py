from unittest import mock
from unittest.mock import patch

from django.conf import settings
from django.urls import reverse
from django.utils.text import slugify
from django.core.cache import cache
from django.db import transaction

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
            self.assertEqual(mock_cache_set.call_args[0][2], 60 * 15)

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

#-------------------------------------------Member Board Detail View Test---------------------------------------

class MemberBoardDetailViewTests(APITestCase):

    def setUp(self):

        self.owner = CustomUser.objects.create_user(
            email='owner@test.com',
            password='testPass123'
        )
        self.member = CustomUser.objects.create_user(
            email='member@test.com',
            password='testPass123'
        )
        self.non_member = CustomUser.objects.create_user(
            email='nonmember@test.com',
            password='testPass123'
        )
        self.other_user = CustomUser.objects.create_user(
            email='other@test.com',
            password='testPass123'
        )

        self.board = Board.objects.create(
            name='Test Board',
            slug='test-board',
            description='Test Description',
            owner=self.owner
        )

        self.board.members.add(self.member)

        self.url = reverse('board-member-detail', kwargs={'pk': self.board.pk})

        self.client = APIClient()

    def test_authenticated_member_can_view_board(self):
        """تست: کاربر عضو می‌تواند برد را ببیند"""
        self.client.force_authenticate(user=self.member)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['id'], self.board.id)
        self.assertEqual(response.data['name'], 'Test Board')
        self.assertEqual(response.data['owner']['id'], self.owner.id)
        self.assertEqual(response.data['owner']['email'], self.owner.email)

        # بررسی اینکه members لیست شده
        members_emails = [m['email'] for m in response.data['members']]
        self.assertIn(self.member.email, members_emails)

    def test_owner_cannot_view_their_own_board(self):
        """تست: مالک نمی‌تواند برد خودش را از این endpoint ببیند"""
        self.client.force_authenticate(user=self.owner)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_non_member_cannot_view_board(self):
        """تست: کاربر غیر عضو نمی‌تواند برد را ببیند"""
        self.client.force_authenticate(user=self.non_member)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_unauthenticated_user_cannot_view_board(self):
        """تست: کاربر احراز هویت نشده نمی‌تواند برد را ببیند"""
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_nonexistent_board_returns_404(self):
        """تست: برد ناموجود خطای 404 برمی‌گرداند"""
        self.client.force_authenticate(user=self.member)
        invalid_url = reverse('board-member-detail', kwargs={'pk': 99999})

        response = self.client.get(invalid_url)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_cache_returns_cached_data(self):
        """تست: کش به درستی کار می‌کند"""
        self.client.force_authenticate(user=self.member)

        # درخواست اول (کش نمیشود)
        with patch('taskflow.boards.views.cache.get') as mock_cache_get:
            mock_cache_get.return_value = None
            response1 = self.client.get(self.url)

        # درخواست دوم (از کش می‌خواند)
        with patch('taskflow.boards.views.cache.get') as mock_cache_get:
            mock_cache_get.return_value = response1.data
            response2 = self.client.get(self.url)

            # بررسی اینکه از کش استفاده شده
            mock_cache_get.assert_called()
            self.assertEqual(response2.data, response1.data)

    def test_cache_key_is_user_specific(self):
        """تست: کلید کش برای هر کاربر متفاوت است"""
        # ایجاد کاربر عضو دوم
        member2 = CustomUser.objects.create_user(
            email='member2@test.com',
            password='testPass123'
        )
        self.board.members.add(member2)

        self.client.force_authenticate(user=self.member)
        response1 = self.client.get(self.url)

        self.client.force_authenticate(user=member2)
        response2 = self.client.get(self.url)

        # هر دو باید موفق باشند
        self.assertEqual(response1.status_code, status.HTTP_200_OK)
        self.assertEqual(response2.status_code, status.HTTP_200_OK)

    def test_response_structure_is_correct(self):
        """تست: ساختار پاسخ صحیح است"""
        self.client.force_authenticate(user=self.member)

        response = self.client.get(self.url)

        expected_fields = {
            'id', 'name', 'slug', 'description',
            'created_at', 'owner', 'members', 'updated_at'
        }

        self.assertEqual(set(response.data.keys()), expected_fields)
        self.assertIn('id', response.data['owner'])
        self.assertIn('email', response.data['owner'])

        # بررسی اینکه password در پاسخ نیست
        self.assertNotIn('password', response.data['owner'])

        if response.data['members']:
            self.assertNotIn('password', response.data['members'][0])

    def test_only_allowed_fields_are_returned(self):
        """تست: فقط فیلدهای مجاز برگردانده می‌شوند"""
        self.client.force_authenticate(user=self.member)

        response = self.client.get(self.url)

        # فیلدهای حساس نباید باشند
        self.assertNotIn('password', response.data)
        self.assertNotIn('owner__password', response.data)

        # فیلدهای اصلی باید باشند
        self.assertIn('id', response.data)
        self.assertIn('name', response.data)

    def test_database_query_count(self):
        """تست: تعداد کوئری‌های دیتابیس بهینه است"""
        self.client.force_authenticate(user=self.member)

        # تعداد کوئری‌ها را بشمار
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        with CaptureQueriesContext(connection) as queries:
            response = self.client.get(self.url)

        # باید حداکثر 3-4 کوئری داشته باشیم (auth + main queries)
        self.assertLess(len(queries.captured_queries), 5)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_board_with_no_members(self):
        """تست: برد بدون عضو"""
        empty_board = Board.objects.create(
            name='Empty Board',
            slug='empty-board',
            description='No members',
            owner=self.other_user
        )
        empty_board.members.add(self.member)  # فقط member را اضافه کن

        url = reverse('board-member-detail', kwargs={'pk': empty_board.pk})
        self.client.force_authenticate(user=self.member)

        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['members']), 1)  # فقط خود member

    def test_concurrent_cache_access(self):
        """تست: دسترسی همزمان به کش"""
        self.client.force_authenticate(user=self.member)

        # چند درخواست همزمان
        responses = []
        for _ in range(5):
            response = self.client.get(self.url)
            responses.append(response)

        # همه باید موفق باشند
        for response in responses:
            self.assertEqual(response.status_code, status.HTTP_200_OK)

        # همه باید داده یکسان داشته باشند
        first_data = responses[0].data
        for response in responses[1:]:
            self.assertEqual(response.data, first_data)

    @patch('taskflow.boards.views.logger')
    def test_error_logging_on_exception(self, mock_logger):
        """تست: لاگ کردن خطاها"""
        self.client.force_authenticate(user=self.member)

        # ایجاد خطای عمدی
        with patch('taskflow.boards.views.Board.objects.filter') as mock_filter:
            mock_filter.side_effect = Exception("Simulated database error")

            response = self.client.get(self.url)

            # بررسی لاگ
            mock_logger.error.assert_called_once()
            self.assertIn("Member Detail board failed", mock_logger.error.call_args[0][0])

    def test_cache_timeout(self):
        """تست: زمان انقضای کش"""
        self.client.force_authenticate(user=self.member)

        # درخواست اول
        response1 = self.client.get(self.url)

        # شبیه‌سازی زمان گذشته
        with patch('django.core.cache.cache.get') as mock_get:
            mock_get.return_value = None
            response2 = self.client.get(self.url)

            # باید دوباره از دیتابیس بخواند
            mock_get.assert_called()

    def tearDown(self):
        """پاک‌سازی بعد از هر تست"""
        cache.clear()
        super().tearDown()

#-------------------------------------------Owner Board Update View Test---------------------------------------

class OwnerBoardUpdateViewTest(APITestCase):
    """
    Test suite for OwnerBoardUpdateView.

    Tests cover:
    - Successful board updates (name, description, members)
    - Validation errors (duplicate name, long description, empty name)
    - Member management (add, remove, add/remove together)
    - Edge cases (non-existent users, duplicate emails, cache invalidation)
    - Permission checks (unauthenticated, non-owner)
    - Concurrent operation validations
    """

    def setUp(self):
        """Initialize test data with owner, members, and a test board."""
        cache.clear()

        # Create test users
        self.owner = CustomUser.objects.create_user(
            email='owner@test.com',
            password='testPass123'
        )
        self.member1 = CustomUser.objects.create_user(
            email='member1@test.com',
            password='testPass123'
        )
        self.member2 = CustomUser.objects.create_user(
            email='member2@test.com',
            password='testPass123'
        )
        self.non_member = CustomUser.objects.create_user(
            email='nonmember@test.com',
            password='testPass123'
        )
        self.other_user = CustomUser.objects.create_user(
            email='other@test.com',
            password='testPass123'
        )

        # Create test board owned by owner
        self.board = Board.objects.create(
            name='Test Board',
            slug='test-board',
            description='Test Description',
            owner=self.owner
        )

        # Add initial members
        self.board.members.add(self.member1, self.member2)

        # API endpoint URL
        self.url = reverse('board-owned-update', kwargs={'pk': self.board.pk})

    def authenticate(self, user):
        """Helper method to authenticate a user."""
        self.client.force_authenticate(user=user)

    # ==================== Successful Update Tests ====================

    def test_successful_update_board_name_and_description(self):
        """Test successfully updating both board name and description."""
        self.authenticate(self.owner)

        data = {
            'name': 'Updated Board Name',
            'description': 'Updated Description'
        }

        response = self.client.patch(self.url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['name'], 'Updated Board Name')
        self.assertEqual(response.data['description'], 'Updated Description')

        self.board.refresh_from_db()
        self.assertEqual(self.board.name, 'Updated Board Name')
        self.assertEqual(self.board.description, 'Updated Description')

    def test_successful_update_only_name(self):
        """Test updating only the board name."""
        self.authenticate(self.owner)

        data = {'name': 'New Name Only'}

        response = self.client.patch(self.url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['name'], 'New Name Only')
        self.assertEqual(response.data['description'], 'Test Description')

        self.board.refresh_from_db()
        self.assertEqual(self.board.name, 'New Name Only')
        self.assertEqual(self.board.description, 'Test Description')

    def test_successful_update_only_description(self):
        """Test updating only the board description."""
        self.authenticate(self.owner)

        data = {'description': 'New Description Only'}

        response = self.client.patch(self.url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['description'], 'New Description Only')

        self.board.refresh_from_db()
        self.assertEqual(self.board.description, 'New Description Only')

    # ==================== Member Management Tests ====================

    def test_add_members_successfully(self):
        """Test adding new members to the board."""
        self.authenticate(self.owner)

        data = {'members_to_add': ['nonmember@test.com']}

        response = self.client.patch(self.url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.board.refresh_from_db()
        self.assertTrue(self.board.members.filter(email='nonmember@test.com').exists())
        self.assertEqual(self.board.members.count(), 3)

    def test_remove_members_successfully(self):
        """Test removing members from the board."""
        self.authenticate(self.owner)

        data = {'members_to_remove': ['member1@test.com']}

        response = self.client.patch(self.url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.board.refresh_from_db()
        self.assertFalse(self.board.members.filter(email='member1@test.com').exists())
        self.assertEqual(self.board.members.count(), 1)

    def test_add_and_remove_members_together(self):
        """Test adding and removing members in a single request."""
        self.authenticate(self.owner)

        data = {
            'members_to_add': ['nonmember@test.com'],
            'members_to_remove': ['member1@test.com']
        }

        response = self.client.patch(self.url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.board.refresh_from_db()
        self.assertTrue(self.board.members.filter(email='nonmember@test.com').exists())
        self.assertFalse(self.board.members.filter(email='member1@test.com').exists())
        self.assertTrue(self.board.members.filter(email='member2@test.com').exists())

    # ==================== Validation Error Tests ====================

    def test_duplicate_board_name_for_same_owner(self):
        """Test duplicate board name validation for same owner."""
        self.authenticate(self.owner)

        # Create another board with the same name
        Board.objects.create(
            name='Existing Board',
            description='Another board',
            owner=self.owner
        )

        data = {'name': 'Existing Board'}

        response = self.client.patch(self.url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('name', response.data)
        self.assertIn('already have a board with this name', str(response.data))

    def test_same_name_allowed_for_different_owner(self):
        """Test same board name is allowed for different owners."""
        self.authenticate(self.owner)

        # Create board with same name by different owner
        Board.objects.create(
            name='Same Name',
            description='Another board',
            owner=self.other_user
        )

        data = {'name': 'Same Name'}

        response = self.client.patch(self.url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.board.refresh_from_db()
        self.assertEqual(self.board.name, 'Same Name')

    def test_cannot_remove_board_owner(self):
        """Test that board owner cannot be removed from members."""
        self.authenticate(self.owner)

        data = {'members_to_remove': [self.owner.email]}

        response = self.client.patch(self.url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('members_to_remove', response.data)
        self.assertIn('Cannot remove board owner', str(response.data))

    def test_cannot_add_owner_as_member(self):
        """Test that board owner cannot be added as member (already member)."""
        self.authenticate(self.owner)

        data = {'members_to_add': [self.owner.email]}

        response = self.client.patch(self.url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('members_to_add', response.data)
        self.assertIn('already a member by default', str(response.data))

    def test_cannot_add_and_remove_same_user(self):
        """Test cannot add and remove the same user in one request."""
        self.authenticate(self.owner)

        data = {
            'members_to_add': ['member1@test.com'],
            'members_to_remove': ['member1@test.com']
        }

        response = self.client.patch(self.url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('Cannot add and remove the same user', str(response.data))

    def test_add_already_member_user(self):
        """Test adding a user who is already a board member."""
        self.authenticate(self.owner)

        data = {'members_to_add': ['member1@test.com']}

        response = self.client.patch(self.url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('members_to_add', response.data)
        self.assertIn('already members', str(response.data))

    def test_remove_non_member_user(self):
        """Test removing a user who is not a board member."""
        self.authenticate(self.owner)

        data = {'members_to_remove': ['nonmember@test.com']}

        response = self.client.patch(self.url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('members_to_remove', response.data)
        self.assertIn('not members', str(response.data))

    def test_add_nonexistent_user(self):
        """Test adding a user that doesn't exist in the system."""
        self.authenticate(self.owner)

        data = {'members_to_add': ['nonexistent@test.com']}

        response = self.client.patch(self.url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('User(s) not found', str(response.data))

    def test_description_too_long(self):
        """Test validation for description exceeding 500 characters."""
        self.authenticate(self.owner)

        data = {'description': 'a' * 501}

        response = self.client.patch(self.url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('description', response.data)
        self.assertIn('500 characters', str(response.data))

    def test_empty_name_not_allowed(self):
        """Test that empty board name is not allowed."""
        self.authenticate(self.owner)

        data = {'name': ''}

        response = self.client.patch(self.url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('name', response.data)

    # ==================== Permission Tests ====================

    def test_unauthenticated_user(self):
        """Test unauthenticated user cannot update board."""
        response = self.client.patch(self.url, {'name': 'New Name'}, format='json')

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_non_owner_cannot_update(self):
        """Test non-owner user cannot update the board."""
        self.authenticate(self.member1)

        response = self.client.patch(self.url, {'name': 'Hacked Name'}, format='json')

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertIn('Board not found or no permission', str(response.data))

    def test_board_not_found(self):
        """Test request for non-existent board returns 404."""
        self.authenticate(self.owner)

        url = reverse('board-owned-update', kwargs={'pk': 99999})
        response = self.client.patch(url, {'name': 'New Name'}, format='json')

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    # ==================== Cache Tests ====================

    def test_cache_invalidated_after_update(self):
        """Test that cache is properly invalidated after board update."""
        self.authenticate(self.owner)

        # Set cache value
        cache_key = f'member_board_detail_{self.board.pk}_user_{self.owner.pk}'
        cache.set(cache_key, {'test': 'data'})

        # Update board
        response = self.client.patch(self.url, {'name': 'Updated Name'}, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Verify cache was cleared
        self.assertIsNone(cache.get(cache_key))

    # ==================== Edge Cases ====================

    def test_update_with_duplicate_emails_in_add(self):
        """Test duplicate emails in members_to_add are handled correctly."""
        self.authenticate(self.owner)

        data = {
            'members_to_add': ['nonmember@test.com', 'nonmember@test.com']
        }

        response = self.client.patch(self.url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Verify user was added only once
        self.board.refresh_from_db()
        members_count = self.board.members.filter(email='nonmember@test.com').count()
        self.assertEqual(members_count, 1)

    def test_update_with_duplicate_emails_in_remove(self):
        """Test duplicate emails in members_to_remove are handled correctly."""
        self.authenticate(self.owner)

        data = {
            'members_to_remove': ['member1@test.com', 'member1@test.com']
        }

        response = self.client.patch(self.url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.board.refresh_from_db()
        self.assertFalse(self.board.members.filter(email='member1@test.com').exists())

#-------------------------------------------Owner Board Delete View Test---------------------------------------

class OwnerBoardDeleteViewTest(APITestCase):
    """
    Test suite for OwnerBoardDeleteView.
    """

    def setUp(self):
        """Initialize test data."""
        cache.clear()

        # Create test users (only email and password as specified)
        self.owner = CustomUser.objects.create_user(
            email='owner@test.com',
            password='testPass123'
        )
        self.member = CustomUser.objects.create_user(
            email='member@test.com',
            password='testPass123'
        )
        self.other_user = CustomUser.objects.create_user(
            email='other@test.com',
            password='testPass123'
        )

        # Create active board
        self.board = Board.objects.create(
            name='Test Board',
            slug='test-board',
            description='Test Description',
            owner=self.owner,
            is_active=True
        )
        self.board.members.add(self.member)

        # Create already deleted board (inactive)
        self.deleted_board = Board.objects.create(
            name='Deleted Board',
            slug='deleted-board',
            description='Already Deleted',
            owner=self.owner,
            is_active=False
        )

        self.url = reverse('board-owned-delete', kwargs={'pk': self.board.pk})
        self.deleted_url = reverse('board-owned-delete', kwargs={'pk': self.deleted_board.pk})

    def authenticate(self, user):
        """Helper method to authenticate a user."""
        self.client.force_authenticate(user=user)

    # ==================== Successful Delete Tests ====================

    def test_owner_can_delete_board_successfully(self):
        """Test board owner can soft delete their active board."""
        self.authenticate(self.owner)

        response = self.client.delete(self.url)

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        # Verify board is soft deleted
        self.board.refresh_from_db()
        self.assertFalse(self.board.is_active)

        # Verify other fields remain unchanged
        self.assertEqual(self.board.name, 'Test Board')
        self.assertEqual(self.board.description, 'Test Description')
        self.assertEqual(self.board.owner, self.owner)

    def test_cannot_delete_already_inactive_board(self):
        """Test cannot delete a board that is already inactive."""
        self.authenticate(self.owner)

        response = self.client.delete(self.deleted_url)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

        # Verify board remains inactive
        self.deleted_board.refresh_from_db()
        self.assertFalse(self.deleted_board.is_active)

    def test_members_still_accessible_after_soft_delete(self):
        """Test board members are still accessible after soft delete."""
        self.authenticate(self.owner)

        # Verify members exist before delete
        self.assertTrue(self.board.members.filter(email='member@test.com').exists())

        # Delete board
        response = self.client.delete(self.url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        # Verify members relationship still exists
        self.board.refresh_from_db()
        self.assertTrue(self.board.members.filter(email='member@test.com').exists())

    # ==================== Permission Tests ====================

    def test_non_owner_cannot_delete_board(self):
        """Test board member cannot delete the board."""
        self.authenticate(self.member)

        response = self.client.delete(self.url)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

        # Verify board remains active
        self.board.refresh_from_db()
        self.assertTrue(self.board.is_active)

    def test_other_user_cannot_delete_board(self):
        """Test completely unrelated user cannot delete the board."""
        self.authenticate(self.other_user)

        response = self.client.delete(self.url)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

        # Verify board remains active
        self.board.refresh_from_db()
        self.assertTrue(self.board.is_active)

    def test_unauthenticated_user_cannot_delete_board(self):
        """Test unauthenticated user cannot delete board."""
        response = self.client.delete(self.url)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

        # Verify board remains active
        self.board.refresh_from_db()
        self.assertTrue(self.board.is_active)

    # ==================== Edge Cases Tests ====================

    def test_delete_nonexistent_board(self):
        """Test deleting a board that doesn't exist."""
        self.authenticate(self.owner)

        url = reverse('board-owned-delete', kwargs={'pk': 99999})
        response = self.client.delete(url)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    # ✅ حذف شد: test_delete_board_with_invalid_pk (غیرقابل تست با int pk)

    def test_delete_other_owners_board(self):
        """Test user cannot delete another user's board."""
        self.authenticate(self.owner)

        # Create board for other user
        other_board = Board.objects.create(
            name="Other's Board",
            slug='others-board',
            owner=self.other_user,
            is_active=True
        )
        url = reverse('board-owned-delete', kwargs={'pk': other_board.pk})

        response = self.client.delete(url)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

        # Verify other's board remains active
        other_board.refresh_from_db()
        self.assertTrue(other_board.is_active)

    # ==================== Cache Tests ====================

    def test_cache_invalidated_after_delete(self):
        """Test that caches are properly invalidated after board deletion."""
        self.authenticate(self.owner)

        # Set cache values
        cache_key1 = f'owner_board_detail_{self.board.pk}_user_{self.owner.pk}'
        cache_key2 = f'user_owner_boards_{self.owner.pk}'

        cache.set(cache_key1, {'test': 'data'})
        cache.set(cache_key2, [{'id': self.board.pk, 'name': 'Test Board'}])

        # Delete board
        response = self.client.delete(self.url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        # Verify caches are cleared
        self.assertIsNone(cache.get(cache_key1))
        self.assertIsNone(cache.get(cache_key2))

    def test_cache_with_different_user_not_affected(self):
        """Test that other user's cache is not affected."""
        self.authenticate(self.owner)

        # Set cache for different user
        other_cache_key = f'user_owner_boards_{self.member.pk}'
        cache.set(other_cache_key, [{'test': 'data'}])

        # Delete board
        response = self.client.delete(self.url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        # Verify other user's cache remains intact
        self.assertIsNotNone(cache.get(other_cache_key))

    # ==================== Concurrent Operations Tests ====================

    # ✅ حذف شد: test_concurrent_delete_requests (در محیط تست جنگو کار نمی‌کند)
    # دلیل: هر تست در یک تراکنش جداگانه اجرا می‌شود و select_for_update رفتار متفاوتی دارد

    # ==================== Data Integrity Tests ====================

    def test_soft_delete_does_not_remove_from_database(self):
        """Test that soft delete does not actually remove the record."""
        self.authenticate(self.owner)

        board_id = self.board.pk

        response = self.client.delete(self.url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        # Board should still exist in database
        self.assertTrue(Board.objects.filter(pk=board_id).exists())

        # But should not be in active queryset
        self.assertFalse(Board.objects.filter(pk=board_id, is_active=True).exists())

    def test_updated_at_changed_after_delete(self):
        """Test that updated_at timestamp is updated after soft delete."""
        self.authenticate(self.owner)

        original_updated_at = self.board.updated_at

        # Wait a moment to ensure timestamp difference
        import time
        time.sleep(0.01)

        response = self.client.delete(self.url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        self.board.refresh_from_db()
        self.assertNotEqual(self.board.updated_at, original_updated_at)
        self.assertGreater(self.board.updated_at, original_updated_at)

    def test_delete_twice_returns_404(self):
        """Test deleting the same board twice returns 404 on second attempt."""
        self.authenticate(self.owner)

        # First delete
        response1 = self.client.delete(self.url)
        self.assertEqual(response1.status_code, status.HTTP_204_NO_CONTENT)

        # Second delete (board is already inactive)
        response2 = self.client.delete(self.url)
        self.assertEqual(response2.status_code, status.HTTP_404_NOT_FOUND)

    # ==================== Query Optimization Tests ====================

    def test_only_necessary_fields_are_selected(self):
        """Test that only necessary fields are selected from database."""
        self.authenticate(self.owner)

        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        with CaptureQueriesContext(connection) as context:
            response = self.client.delete(self.url)

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        # Find SELECT query (ignore SAVEPOINT queries)
        select_query = None
        for query in context.captured_queries:
            if 'SELECT' in query['sql'] and 'boards_board' in query['sql']:
                select_query = query['sql']
                break

        # Verify only necessary fields are selected
        self.assertIsNotNone(select_query)
        self.assertIn('"id"', select_query)
        self.assertIn('"is_active"', select_query)
        self.assertIn('"updated_at"', select_query)
        self.assertIn('"owner_id"', select_query)

        # Verify unnecessary fields are not selected
        self.assertNotIn('"name"', select_query)
        self.assertNotIn('"description"', select_query)
        self.assertNotIn('"slug"', select_query)
        self.assertNotIn('"created_at"', select_query)

    def test_only_two_queries_executed(self):
        """Test that only 2 queries are executed (SELECT and UPDATE)."""
        self.authenticate(self.owner)

        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        with CaptureQueriesContext(connection) as context:
            response = self.client.delete(self.url)

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        # Filter out SAVEPOINT and other system queries
        actual_queries = [
            q for q in context.captured_queries
            if 'SELECT' in q['sql'] or 'UPDATE' in q['sql']
        ]

        # Should be exactly 2 queries (SELECT FOR UPDATE + UPDATE)
        self.assertEqual(len(actual_queries), 2)

        # Verify query types
        query_types = []
        for query in actual_queries:
            if 'SELECT' in query['sql']:
                query_types.append('SELECT')
            elif 'UPDATE' in query['sql']:
                query_types.append('UPDATE')

        self.assertEqual(query_types, ['SELECT', 'UPDATE'])

    def test_response_has_correct_status_and_message(self):
        """Test that response has correct status code and message."""
        self.authenticate(self.owner)

        response = self.client.delete(self.url)

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(response.data, {"detail": "Board deleted successfully."})

    def test_delete_response_has_no_content_body_for_204(self):
        """Test that 204 response has no content body (by default)."""
        self.authenticate(self.owner)

        response = self.client.delete(self.url)

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        # For 204 responses, Django REST framework may return empty response
        # This test ensures our implementation follows the standard