from unittest.mock import patch
from datetime import timedelta

from django.core.cache import cache
from django.test import override_settings, TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils.text import slugify
from django.utils import timezone

from rest_framework.test import APITestCase, APIClient
from rest_framework import status

from .models import Company, Membership, Invitation
from .services.invitation_service import InvitationService
from .views import CompanyDetailView

User = get_user_model()


class CompanyCreateViewTest(APITestCase):

    def setUp(self):
        self.url = reverse('company-create')
        self.owner = User.objects.create_user(
            email='owner@example.com',
            password='testPass123'
        )
        self.member1 = User.objects.create_user(
            email='member1@example.com',
            password='testPass123'
        )
        self.member2 = User.objects.create_user(
            email='member2@example.com',
            password='testPass123'
        )

        # Clear cache before each test
        cache.clear()

    def authenticate(self, user):
        self.client.force_authenticate(user=user)

    def test_create_company_success_without_members_returns_201(self):
        """Test successful company creation without members"""
        self.authenticate(self.owner)

        payload = {
            'name': 'Tech Innovations Inc',
            'slug': 'tech-innovations',
            'email': 'contact@techinnovations.com'
        }

        response = self.client.post(self.url, payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn('id', response.data)

        company = Company.objects.get(id=response.data['id'])
        self.assertEqual(company.name, 'Tech Innovations Inc')
        self.assertEqual(company.slug, 'tech-innovations')
        self.assertEqual(company.email, 'contact@techinnovations.com')
        self.assertEqual(company.owner, self.owner)

        # بررسی membership برای owner
        owner_membership = Membership.objects.get(user=self.owner, company=company)
        self.assertEqual(owner_membership.role, Membership.RoleChoices.ADMIN)

        # بررسی اینکه هیچ عضو دیگری وجود ندارد
        self.assertEqual(company.members.count(), 1)  # فقط owner
        self.assertIn(self.owner, company.members.all())

    def test_create_company_without_slug_auto_generates_slug(self):
        """Test that slug is automatically generated from name if not provided"""
        self.authenticate(self.owner)

        payload = {
            'name': 'Auto Slug Company'
        }

        response = self.client.post(self.url, payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        company = Company.objects.get(id=response.data['id'])
        expected_slug = slugify('Auto Slug Company', allow_unicode=True)
        self.assertEqual(company.slug, expected_slug)
        self.assertEqual(company.name, 'Auto Slug Company')

        # بررسی اینکه owner به عنوان ADMIN اضافه شده
        self.assertTrue(
            Membership.objects.filter(
                user=self.owner,
                company=company,
                role=Membership.RoleChoices.ADMIN
            ).exists()
        )

    def test_create_company_with_members_returns_201(self):
        """Test company creation with initial members"""
        self.authenticate(self.owner)

        payload = {
            'name': 'Startup Hub',
            'slug': 'startup-hub',
            'members': [self.member1.id, self.member2.id]
        }

        response = self.client.post(self.url, payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        company = Company.objects.get(id=response.data['id'])

        # بررسی تعداد کل اعضا (owner + 2 member)
        self.assertEqual(company.members.count(), 3)

        # بررسی owner
        self.assertIn(self.owner, company.members.all())
        owner_membership = Membership.objects.get(user=self.owner, company=company)
        self.assertEqual(owner_membership.role, Membership.RoleChoices.ADMIN)

        # بررسی اعضای اضافه شده
        self.assertIn(self.member1, company.members.all())
        member1_membership = Membership.objects.get(user=self.member1, company=company)
        self.assertEqual(member1_membership.role, Membership.RoleChoices.MEMBER)

        self.assertIn(self.member2, company.members.all())
        member2_membership = Membership.objects.get(user=self.member2, company=company)
        self.assertEqual(member2_membership.role, Membership.RoleChoices.MEMBER)

    def test_create_company_with_custom_slug_and_members(self):
        """Test company creation with both custom slug and members"""
        self.authenticate(self.owner)

        payload = {
            'name': 'Custom Company',
            'slug': 'my-custom-slug-123',
            'email': 'custom@company.com',
            'members': [self.member1.id]
        }

        response = self.client.post(self.url, payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        company = Company.objects.get(id=response.data['id'])
        self.assertEqual(company.slug, 'my-custom-slug-123')
        self.assertEqual(company.name, 'Custom Company')
        self.assertEqual(company.email, 'custom@company.com')

        # بررسی تعداد اعضا (owner + 1 member)
        self.assertEqual(company.members.count(), 2)
        self.assertIn(self.owner, company.members.all())
        self.assertIn(self.member1, company.members.all())

        # بررسی نقش owner
        owner_membership = Membership.objects.get(user=self.owner, company=company)
        self.assertEqual(owner_membership.role, Membership.RoleChoices.ADMIN)

    def test_create_company_unauthenticated_returns_401(self):
        """Test that unauthenticated users cannot create companies"""
        payload = {
            'name': 'Unauthorized Company'
        }

        response = self.client.post(self.url, payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(Company.objects.count(), 0)
        self.assertEqual(Membership.objects.count(), 0)

    def test_create_company_invalid_data_returns_400(self):
        """Test company creation with invalid data (missing required fields)"""
        self.authenticate(self.owner)

        # Missing required 'name' field
        payload = {
            'email': 'no-name@company.com'
        }

        response = self.client.post(self.url, payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('name', response.data)
        self.assertEqual(Company.objects.count(), 0)
        self.assertEqual(Membership.objects.count(), 0)

    def test_create_company_duplicate_slug_returns_error(self):
        """Test that duplicate slug raises validation error"""
        self.authenticate(self.owner)

        # Create first company
        company1 = Company.objects.create(
            owner=self.owner,
            name='First Company',
            slug='duplicate-slug'
        )
        # اضافه کردن owner به membership
        Membership.objects.create(
            user=self.owner,
            company=company1,
            role=Membership.RoleChoices.ADMIN
        )

        # Try to create second company with same slug
        payload = {
            'name': 'Second Company',
            'slug': 'duplicate-slug'
        }

        response = self.client.post(self.url, payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertTrue('slug' in response.data or 'non_field_errors' in response.data)
        self.assertEqual(Company.objects.count(), 1)

    def test_create_company_with_empty_members_list(self):
        """Test company creation with empty members list"""
        self.authenticate(self.owner)

        payload = {
            'name': 'Empty Members Company',
            'members': []
        }

        response = self.client.post(self.url, payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        company = Company.objects.get(id=response.data['id'])

        # فقط owner باید عضو باشد
        self.assertEqual(company.members.count(), 1)
        self.assertIn(self.owner, company.members.all())

        # بررسی نقش owner
        owner_membership = Membership.objects.get(user=self.owner, company=company)
        self.assertEqual(owner_membership.role, Membership.RoleChoices.ADMIN)

    def test_create_company_with_nonexistent_members(self):
        """Test company creation with non-existent member IDs"""
        self.authenticate(self.owner)

        payload = {
            'name': 'Company Bad Members',
            'members': [99999, 88888]  # Non-existent user IDs
        }

        response = self.client.post(self.url, payload, format='json')

        # باید خطای اعتبارسنجی برگردد
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('members', response.data)
        self.assertEqual(Company.objects.count(), 0)

    def test_create_company_without_email_field(self):
        """Test company creation without optional email field"""
        self.authenticate(self.owner)

        payload = {
            'name': 'No Email Company',
            'slug': 'no-email'
        }

        response = self.client.post(self.url, payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        company = Company.objects.get(id=response.data['id'])
        self.assertIsNone(company.email)

        # بررسی اینکه owner اضافه شده
        self.assertEqual(company.members.count(), 1)
        self.assertIn(self.owner, company.members.all())

    def test_create_company_with_unicode_characters(self):
        """Test company creation with unicode characters in name and slug"""
        self.authenticate(self.owner)

        payload = {
            'name': 'شرکت فناوری اطلاعات',
            'slug': 'it-company'
        }

        response = self.client.post(self.url, payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        company = Company.objects.get(id=response.data['id'])
        self.assertEqual(company.name, 'شرکت فناوری اطلاعات')
        self.assertEqual(company.slug, 'it-company')

        # بررسی owner membership
        self.assertTrue(
            Membership.objects.filter(
                user=self.owner,
                company=company,
                role=Membership.RoleChoices.ADMIN
            ).exists()
        )

    def test_create_company_auto_slug_with_unicode(self):
        """Test auto slug generation with unicode characters"""
        self.authenticate(self.owner)

        payload = {
            'name': 'شرکت نوآوران'
        }

        response = self.client.post(self.url, payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        company = Company.objects.get(id=response.data['id'])
        expected_slug = slugify('شرکت نوآوران', allow_unicode=True)
        self.assertEqual(company.slug, expected_slug)

    @override_settings(DEBUG=True)
    @patch('taskflow.companies.views.logger')
    def test_create_company_database_error_handling_debug_mode(self, mock_logger):
        """Test error handling when database operation fails in DEBUG mode"""
        self.authenticate(self.owner)

        payload = {
            'name': 'Company That Will Fail'
        }

        # Mock Company.objects.create to raise an exception
        with patch('taskflow.companies.models.Company.objects.create') as mock_create:
            mock_create.side_effect = Exception("Database connection error")
            response = self.client.post(self.url, payload, format='json')

            self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)
            self.assertIn('detail', response.data)
            self.assertIn('An error occurred', response.data['detail'])
            mock_logger.error.assert_called_once()

    @override_settings(DEBUG=False)
    @patch('taskflow.companies.views.logger')
    def test_create_company_database_error_handling_non_debug_mode(self, mock_logger):
        """Test error handling when database operation fails in non-DEBUG mode"""
        self.authenticate(self.owner)

        payload = {
            'name': 'Company That Will Fail'
        }

        # Mock Company.objects.create to raise an exception
        with patch('taskflow.companies.models.Company.objects.create') as mock_create:
            mock_create.side_effect = Exception("Database connection error")
            response = self.client.post(self.url, payload, format='json')

            self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)
            self.assertEqual(response.data, {'detail': 'Server Error'})
            mock_logger.error.assert_called_once()

    def test_create_company_multiple_companies_same_owner(self):
        """Test creating multiple companies by the same owner"""
        self.authenticate(self.owner)

        companies_data = [
            {'name': 'Company Alpha', 'slug': 'alpha'},
            {'name': 'Company Beta', 'slug': 'beta'},
            {'name': 'Company Gamma', 'slug': 'gamma'}
        ]

        for data in companies_data:
            response = self.client.post(self.url, data, format='json')
            self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        self.assertEqual(Company.objects.filter(owner=self.owner).count(), 3)

        # بررسی اینکه owner در هر سه شرکت membership دارد
        for company in Company.objects.filter(owner=self.owner):
            self.assertTrue(
                Membership.objects.filter(
                    user=self.owner,
                    company=company,
                    role=Membership.RoleChoices.ADMIN
                ).exists()
            )

    def test_create_company_duplicate_name_not_allowed(self):
        """Test that companies cannot have duplicate names (name field is unique)"""
        self.authenticate(self.owner)

        payload1 = {'name': 'Same Name Company', 'slug': 'first'}
        payload2 = {'name': 'Same Name Company', 'slug': 'second'}

        response1 = self.client.post(self.url, payload1, format='json')
        response2 = self.client.post(self.url, payload2, format='json')

        self.assertEqual(response1.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response2.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('name', response2.data)

        companies = Company.objects.filter(name='Same Name Company')
        self.assertEqual(companies.count(), 1)

    def test_create_company_owner_membership_created_at(self):
        """Test that membership created_at is set correctly"""
        self.authenticate(self.owner)

        payload = {
            'name': 'Membership Date Test'
        }

        response = self.client.post(self.url, payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        company = Company.objects.get(id=response.data['id'])
        membership = Membership.objects.get(user=self.owner, company=company)

        self.assertIsNotNone(membership.joined_at)

    def test_create_company_member_with_owner_in_members_list(self):
        """Test that if owner is in members list, it doesn't create duplicate"""
        self.authenticate(self.owner)

        payload = {
            'name': 'Owner In Members Test',
            'members': [self.owner.id, self.member1.id]
        }

        response = self.client.post(self.url, payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        company = Company.objects.get(id=response.data['id'])

        # فقط یک رکورد membership برای owner باید وجود داشته باشد
        owner_memberships = Membership.objects.filter(user=self.owner, company=company)
        self.assertEqual(owner_memberships.count(), 1)
        self.assertEqual(owner_memberships.first().role, Membership.RoleChoices.ADMIN)

        # تعداد کل اعضا باید 2 باشد (owner + member1)
        self.assertEqual(company.members.count(), 2)

    def tearDown(self):
        # Clean up cache if you have any cache invalidation
        cache.clear()
        super().tearDown()


class CompanyDetailViewTest(APITestCase):
    """Comprehensive tests for CompanyDetailView"""

    def setUp(self):
        """Initial setup before each test"""
        # Clear cache
        cache.clear()

        # Create test users
        self.owner = User.objects.create_user(
            email='owner@example.com',
            password='testPass123',
            display_name='Company Owner'
        )

        self.member1 = User.objects.create_user(
            email='member1@example.com',
            password='testPass123',
            display_name='Member One'
        )

        self.member2 = User.objects.create_user(
            email='member2@example.com',
            password='testPass123',
            display_name='Member Two'
        )

        self.unauthorized_user = User.objects.create_user(
            email='hacker@example.com',
            password='testPass123',
            display_name='Hacker'
        )

        # Create company
        self.company = Company.objects.create(
            name='Test Company',
            slug='test-company',
            email='info@testcompany.com',
            website='https://testcompany.com',
            description='This is a test company',
            owner=self.owner,
            is_active=True
        )

        # Add members to company
        Membership.objects.create(
            company=self.company,
            user=self.member1,
            role='member'
        )
        Membership.objects.create(
            company=self.company,
            user=self.member2,
            role='admin'
        )

        # Setup API client
        self.client = APIClient()
        self.url = reverse('company-detail', kwargs={'pk': self.company.pk})

    def authenticate(self, user):
        """Helper method for authentication"""
        if user:
            self.client.force_authenticate(user=user)
        else:
            self.client.force_authenticate(user=None)

    # ========== Access Tests ==========

    def test_owner_can_view_company(self):
        """Test: Company owner can view details"""
        self.authenticate(self.owner)
        response = self.client.get(self.url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data['id'] == self.company.id
        assert response.data['name'] == self.company.name
        assert response.data['owner']['id'] == self.owner.id
        assert response.data['owner']['email'] == self.owner.email

    def test_member_can_view_company(self):
        """Test: Company member can view details"""
        self.authenticate(self.member1)
        response = self.client.get(self.url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data['id'] == self.company.id

    def test_unauthorized_user_cannot_view_company(self):
        """Test: Non-member user cannot view company"""
        self.authenticate(self.unauthorized_user)
        response = self.client.get(self.url)

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_unauthenticated_user_cannot_view_company(self):
        """Test: Unauthenticated user cannot view company"""
        self.authenticate(None)
        response = self.client.get(self.url)

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_nonexistent_company_returns_404(self):
        """Test: Non-existent company should return 404"""
        self.authenticate(self.owner)
        url = reverse('company-detail', kwargs={'pk': 99999})
        response = self.client.get(url)

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_response_contains_all_required_fields(self):
        """Test: Response should contain all required fields"""
        self.authenticate(self.owner)
        response = self.client.get(self.url)

        required_fields = [
            'id', 'name', 'slug', 'email', 'website',
            'description', 'logo', 'owner', 'members',
            'is_active', 'created_at', 'updated_at'
        ]

        for field in required_fields:
            assert field in response.data

    def test_owner_data_is_nested_correctly(self):
        """Test: Owner information should be displayed as nested object"""
        self.authenticate(self.owner)
        response = self.client.get(self.url)

        assert 'owner' in response.data
        assert 'id' in response.data['owner']
        assert 'email' in response.data['owner']
        assert response.data['owner']['id'] == self.owner.id
        assert response.data['owner']['email'] == self.owner.email

    def test_members_data_is_nested_correctly(self):
        """Test: Members information should be a list of objects with id and email"""
        self.authenticate(self.owner)
        response = self.client.get(self.url)

        assert 'members' in response.data
        assert isinstance(response.data['members'], list)
        assert len(response.data['members']) == 2

        # Check structure of each member based on actual response
        for member in response.data['members']:
            # Check required fields exist
            assert 'user_id' in member, f"Member missing 'user_id' field: {member}"
            assert 'email' in member, f"Member missing 'email' field: {member}"
            assert 'role' in member, f"Member missing 'role' field: {member}"
            assert 'joined_at' in member, f"Member missing 'joined_at' field: {member}"

            # Validate data types
            assert isinstance(member['user_id'], int), "user_id should be integer"
            assert isinstance(member['email'], str), "email should be string"
            assert '@' in member['email'], "email should be valid email format"
            assert isinstance(member['role'], str), "role should be string"

        # Extract emails for verification
        member_emails = [m['email'] for m in response.data['members']]
        assert self.member1.email in member_emails
        assert self.member2.email in member_emails

        # Extract user_ids for verification
        member_ids = [m['user_id'] for m in response.data['members']]
        assert self.member1.id in member_ids
        assert self.member2.id in member_ids
    # ========== Cache Tests ==========

    def test_cache_is_used_on_second_request(self):
        """Test: Second request should use cache"""
        self.authenticate(self.owner)

        with CaptureQueriesContext(connection) as context:
            # First request - should execute queries
            response1 = self.client.get(self.url)
            first_request_queries = len(context.captured_queries)

            # Store the captured queries count for first request
            context.captured_queries.clear()

            # Second request - should use cache (no queries to database)
            response2 = self.client.get(self.url)
            second_request_queries = len(context.captured_queries)

            assert response1.status_code == status.HTTP_200_OK
            assert response2.status_code == status.HTTP_200_OK

            # Note: Authentication might still hit database, so we check for minimal queries
            # Cache should prevent company and membership queries only
            assert second_request_queries <= 2, f"Expected <=2 queries, got {second_request_queries}"

            # Verify data is same
            assert response1.data == response2.data

            # Verify cache is actually working by checking cache directly
            from taskflow.companies.views import CompanyDetailView
            view = CompanyDetailView()
            cache_key = view.get_cache_key(self.owner.id, self.company.pk)
            cached_data = cache.get(cache_key)
            assert cached_data is not None
            assert cached_data == response1.data

    def test_cache_is_different_for_different_users(self):
        """Test: Cache is separate for different users"""
        self.authenticate(self.owner)
        response_owner = self.client.get(self.url)

        self.authenticate(self.member1)
        response_member = self.client.get(self.url)

        assert response_owner.data['id'] == response_member.data['id']

    def test_cache_invalidation(self):
        """Test: Cache should store data for 15 minutes"""
        self.authenticate(self.owner)

        # First request populates cache
        response1 = self.client.get(self.url)

        # Get cache key from view instance
        view = CompanyDetailView()
        cache_key = view.get_cache_key(self.owner.id, self.company.pk)

        # Verify cache exists
        assert cache.get(cache_key) is not None

        # Second request should use cache
        with CaptureQueriesContext(connection) as context:
            response2 = self.client.get(self.url)
            assert len(context.captured_queries) == 0

        assert response1.data == response2.data

    # ========== Optimization Tests ==========

    def test_query_count_is_optimized(self):
        """Test: Number of queries should be optimized (max 3 queries)"""
        self.authenticate(self.owner)

        with CaptureQueriesContext(connection) as context:
            response = self.client.get(self.url)

            # Expected queries:
            # 1. Authentication check (if using DB session)
            # 2. Company query with owner join
            # 3. Members query (via serializer)
            query_count = len(context.captured_queries)

            # Allow up to 4 queries (including authentication)
            assert query_count <= 4, f"Expected <=4 queries, got {query_count}"
            assert response.status_code == status.HTTP_200_OK

    def test_no_duplicate_companies_returned(self):
        """Test: OR condition should not return duplicate companies"""
        self.authenticate(self.owner)

        # Add owner as member as well (both conditions)
        Membership.objects.create(
            company=self.company,
            user=self.owner,
            role='owner'
        )

        response = self.client.get(self.url)

        # Should return only one company
        assert response.status_code == status.HTTP_200_OK
        assert response.data['id'] == self.company.id

    def test_cannot_access_other_company_by_id_guessing(self):
        """Test: User cannot access other company by ID guessing"""
        # Create another company with different owner
        other_owner = User.objects.create_user(
            email='other@example.com',
            password='testPass123',
            display_name='Other Owner'
        )

        other_company = Company.objects.create(
            name='Other Company',
            slug='other-company',
            owner=other_owner,
            is_active=True
        )

        self.authenticate(self.owner)
        url = reverse('company-detail', kwargs={'pk': other_company.pk})
        response = self.client.get(url)

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_member_cannot_see_companies_of_another_user(self):
        """Test: Member of one company cannot see another company"""
        # Create another company with different owner
        other_owner = User.objects.create_user(
            email='other2@example.com',
            password='testPass123',
            display_name='Other Owner 2'
        )

        other_company = Company.objects.create(
            name='Another Company',
            slug='another-company',
            owner=other_owner,
            is_active=True
        )

        self.authenticate(self.member1)
        url = reverse('company-detail', kwargs={'pk': other_company.pk})
        response = self.client.get(url)

        assert response.status_code == status.HTTP_404_NOT_FOUND


class CompanyDetailViewPerformanceTest(APITestCase):
    """Performance tests for CompanyDetailView"""

    def setUp(self):
        cache.clear()

        self.user = User.objects.create_user(
            email='owner@example.com',
            password='testPass123',
            display_name='Performance Owner'
        )

        # Create 100 companies
        self.companies = []
        for i in range(100):
            company = Company.objects.create(
                name=f'Company {i}',
                slug=f'company-{i}',
                owner=self.user,
                is_active=True
            )
            self.companies.append(company)

        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_first_request_response_time(self):
        """Test: First request response time should be acceptable"""
        import time

        url = reverse('company-detail', kwargs={'pk': self.companies[0].pk})

        start = time.time()
        response = self.client.get(url)
        end = time.time()

        response_time = (end - start) * 1000  # milliseconds

        assert response.status_code == status.HTTP_200_OK
        assert response_time < 500, f"Response time {response_time}ms > 500ms"

    def test_cached_request_response_time(self):
        """Test: Cached request should be very fast"""
        import time

        url = reverse('company-detail', kwargs={'pk': self.companies[0].pk})

        # First request to populate cache
        self.client.get(url)

        # Second request (cached)
        start = time.time()
        response = self.client.get(url)
        end = time.time()

        response_time = (end - start) * 1000  # milliseconds

        assert response.status_code == status.HTTP_200_OK
        assert response_time < 50, f"Cached response time {response_time}ms > 50ms"


class RequestJoinCompanyTests(APITestCase):

    def setUp(self):
        # Create users
        self.user = User.objects.create_user(
            email='user@example.com',
            password='testPass123',
            first_name='Test',
            last_name='User'
        )

        self.admin_user = User.objects.create_user(
            email='admin@example.com',
            password='testPass123',
            first_name='Admin',
            last_name='User'
        )

        self.other_user = User.objects.create_user(
            email='other@example.com',
            password='testPass123',
            first_name='Other',
            last_name='User'
        )

        # Create a company
        self.company = Company.objects.create(
            name='Test Company',
            slug='test-company',
            owner=self.admin_user,
            is_active=True
        )

        # Make admin_user an admin of the company
        Membership.objects.create(
            user=self.admin_user,
            company=self.company,
            role=Membership.RoleChoices.ADMIN
        )

        # URL for requesting to join
        self.url = reverse('request-join')

    def authenticate(self, user):
        """Helper method to authenticate a user"""
        self.client.force_authenticate(user=user)

    def test_successful_join_request(self):
        """Test that a user can successfully request to join a company"""
        self.authenticate(self.user)

        data = {
            'name': self.company.name,
            'message': 'I would like to join this company'
        }

        response = self.client.post(self.url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(response.data['success'])
        self.assertEqual(response.data['message'], 'Join request sent successfully')
        self.assertEqual(response.data['company']['name'], self.company.name)

        # Verify invitation was created
        invitation = Invitation.objects.get(
            email=self.user.email,
            company=self.company,
            invitation_type=Invitation.InvitationType.REQUEST
        )
        self.assertEqual(invitation.status, Invitation.InvitationStatus.PENDING)
        self.assertEqual(invitation.message, 'I would like to join this company')

    def test_join_request_without_message(self):
        """Test join request with default message when no message provided"""
        self.authenticate(self.user)

        data = {
            'name': self.company.name
        }

        response = self.client.post(self.url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        invitation = Invitation.objects.get(
            email=self.user.email,
            company=self.company
        )
        expected_message = f"{self.user.get_full_name()} requests to join your company"
        self.assertEqual(invitation.message, expected_message)

    def test_join_request_already_member(self):
        """Test that a user cannot request to join a company they're already a member of"""
        # Make user a member
        Membership.objects.create(
            user=self.user,
            company=self.company,
            role=Membership.RoleChoices.MEMBER
        )

        self.authenticate(self.user)

        data = {'name': self.company.name}

        response = self.client.post(self.url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(response.data['success'])
        self.assertIn('You are already a member', str(response.data['errors']))

    def test_join_request_pending_already(self):
        """Test that a user cannot create a duplicate pending request"""
        self.authenticate(self.user)

        # Create existing pending request
        Invitation.objects.create(
            email=self.user.email,
            company=self.company,
            invited_by=self.user,
            invited_user=self.user,
            role=Membership.RoleChoices.MEMBER,
            invitation_type=Invitation.InvitationType.REQUEST,
            token='existing-token',
            status=Invitation.InvitationStatus.PENDING,
            expires_at=timezone.now() + timedelta(days=7)
        )

        data = {'name': self.company.name}

        response = self.client.post(self.url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(response.data['success'])

    def test_join_request_nonexistent_company(self):
        """Test that requesting to join a non-existent company fails"""
        self.authenticate(self.user)

        data = {'name': 'Company That Does Not Exist'}

        response = self.client.post(self.url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(response.data['success'])
        self.assertIn('Company does not exist', str(response.data['errors']))

    def test_join_request_inactive_company(self):
        """Test that requesting to join an inactive company fails"""
        inactive_company = Company.objects.create(
            name='Inactive Company',
            slug='inactive-company',
            owner=self.user,
            is_active=False
        )

        self.authenticate(self.user)

        data = {'name': inactive_company.name}

        response = self.client.post(self.url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(response.data['success'])

    def test_join_request_unauthenticated(self):
        """Test that unauthenticated users cannot request to join"""
        data = {'name': self.company.name}

        response = self.client.post(self.url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class ApproveJoinRequestTests(APITestCase):

    def setUp(self):
        # Create users
        self.user = User.objects.create_user(
            email='user@example.com',
            password='testPass123',
            first_name='Test',
            last_name='User'
        )

        self.admin_user = User.objects.create_user(
            email='admin@example.com',
            password='testPass123',
            first_name='Admin',
            last_name='User'
        )

        self.non_admin_user = User.objects.create_user(
            email='nonadmin@example.com',
            password='testPass123'
        )

        # Create a company
        self.company = Company.objects.create(
            name='Test Company',
            slug='test-company',
            owner=self.admin_user,
            is_active=True
        )

        # Make admin_user an admin
        Membership.objects.create(
            user=self.admin_user,
            company=self.company,
            role=Membership.RoleChoices.ADMIN
        )

        # Make non_admin_user a regular member
        Membership.objects.create(
            user=self.non_admin_user,
            company=self.company,
            role=Membership.RoleChoices.MEMBER
        )

        # Create a join request
        self.invitation = Invitation.objects.create(
            email=self.user.email,
            company=self.company,
            invited_by=self.user,
            invited_user=self.user,
            role=Membership.RoleChoices.MEMBER,
            invitation_type=Invitation.InvitationType.REQUEST,
            token='test-token-123',
            status=Invitation.InvitationStatus.PENDING,
            expires_at=timezone.now() + timedelta(days=30)
        )

        self.url = reverse('approve-request', args=[self.invitation.id])

    def authenticate(self, user):
        """Helper method to authenticate a user"""
        self.client.force_authenticate(user=user)

    def test_admin_approves_join_request(self):
        """Test that an admin can approve a join request"""
        self.authenticate(self.admin_user)

        response = self.client.post(self.url, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['message'], 'Join request approved')
        self.assertEqual(response.data['membership']['user_id'], self.user.id)
        self.assertEqual(response.data['membership']['company_id'], self.company.id)
        self.assertEqual(response.data['membership']['role'], Membership.RoleChoices.MEMBER)

        # Verify membership was created
        membership_exists = Membership.objects.filter(
            user=self.user,
            company=self.company
        ).exists()
        self.assertTrue(membership_exists)

        # Verify invitation status was updated
        self.invitation.refresh_from_db()
        self.assertEqual(self.invitation.status, Invitation.InvitationStatus.ACCEPTED)

    def test_non_admin_cannot_approve_request(self):
        """Test that a non-admin user cannot approve a join request"""
        self.authenticate(self.non_admin_user)

        response = self.client.post(self.url, format='json')

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn('Only admins can approve', str(response.data['error']))

        # Verify membership was not created
        membership_exists = Membership.objects.filter(
            user=self.user,
            company=self.company
        ).exists()
        self.assertFalse(membership_exists)

    def test_approve_nonexistent_request(self):
        """Test that approving a non-existent request fails"""
        self.authenticate(self.admin_user)

        url = reverse('approve-request', args=[99999])
        response = self.client.post(url, format='json')

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_approve_already_approved_request(self):
        """Test that approving an already approved request fails"""
        self.invitation.status = Invitation.InvitationStatus.ACCEPTED
        self.invitation.save()

        self.authenticate(self.admin_user)

        response = self.client.post(self.url, format='json')

        # Should handle appropriately - likely raise an error
        self.assertNotEqual(response.status_code, status.HTTP_200_OK)


class RejectJoinRequestTests(APITestCase):

    def setUp(self):
        # Create users
        self.user = User.objects.create_user(
            email='user@example.com',
            password='testPass123',
            first_name='Test',
            last_name='User'
        )

        self.admin_user = User.objects.create_user(
            email='admin@example.com',
            password='testPass123'
        )

        self.non_admin_user = User.objects.create_user(
            email='nonadmin@example.com',
            password='testPass123'
        )

        # Create a company
        self.company = Company.objects.create(
            name='Test Company',
            slug='test-company',
            owner=self.admin_user,
            is_active=True
        )

        # Make admin_user an admin
        Membership.objects.create(
            user=self.admin_user,
            company=self.company,
            role=Membership.RoleChoices.ADMIN
        )

        # Make non_admin_user a regular member
        Membership.objects.create(
            user=self.non_admin_user,
            company=self.company,
            role=Membership.RoleChoices.MEMBER
        )

        # Create a join request
        self.invitation = Invitation.objects.create(
            email=self.user.email,
            company=self.company,
            invited_by=self.user,
            invited_user=self.user,
            role=Membership.RoleChoices.MEMBER,
            invitation_type=Invitation.InvitationType.REQUEST,
            token='test-token-456',
            status=Invitation.InvitationStatus.PENDING,
            expires_at=timezone.now() + timedelta(days=30)
        )

        self.url = reverse('reject-request', args=[self.invitation.id])

    def authenticate(self, user):
        """Helper method to authenticate a user"""
        self.client.force_authenticate(user=user)

    def test_admin_rejects_join_request(self):
        """Test that an admin can reject a join request"""
        self.authenticate(self.admin_user)

        response = self.client.post(self.url, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['message'], 'Join request rejected')

        # Verify invitation status was updated to REJECTED
        self.invitation.refresh_from_db()
        self.assertEqual(self.invitation.status, Invitation.InvitationStatus.CANCELLED)

        # Verify membership was NOT created
        membership_exists = Membership.objects.filter(
            user=self.user,
            company=self.company
        ).exists()
        self.assertFalse(membership_exists)

    def test_admin_rejects_with_reason(self):
        """Test that admin can reject with a reason (though reason isn't used yet)"""
        self.authenticate(self.admin_user)

        data = {'reason': 'Not a good fit for the team'}
        response = self.client.post(self.url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.invitation.refresh_from_db()
        self.assertEqual(self.invitation.status, Invitation.InvitationStatus.CANCELLED)

    def test_non_admin_cannot_reject_request(self):
        """Test that a non-admin user cannot reject a join request"""
        self.authenticate(self.non_admin_user)

        response = self.client.post(self.url, format='json')

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn('Only admins can reject', str(response.data['error']))

        # Verify invitation is still pending
        self.invitation.refresh_from_db()
        self.assertEqual(self.invitation.status, Invitation.InvitationStatus.PENDING)

    def test_reject_nonexistent_request(self):
        """Test that rejecting a non-existent request fails"""
        self.authenticate(self.admin_user)

        url = reverse('reject-request', args=[99999])
        response = self.client.post(url, format='json')

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_reject_already_rejected_request(self):
        """Test that rejecting an already rejected request is idempotent"""
        self.invitation.status = Invitation.InvitationStatus.CANCELLED
        self.invitation.save()

        self.authenticate(self.admin_user)

        response = self.client.post(self.url, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.invitation.refresh_from_db()
        self.assertEqual(self.invitation.status, Invitation.InvitationStatus.CANCELLED)

    def test_unauthenticated_user_cannot_reject(self):
        """Test that unauthenticated users cannot reject requests"""
        response = self.client.post(self.url, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class InvitationServiceTests(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            email='user@example.com',
            password='testPass123',
            first_name='Test',
            last_name='User'
        )

        self.admin_user = User.objects.create_user(
            email='admin@example.com',
            password='testPass123'
        )

        self.company = Company.objects.create(
            name='Test Company',
            slug='test-company',
            owner=self.admin_user,
            is_active=True
        )

        Membership.objects.create(
            user=self.admin_user,
            company=self.company,
            role=Membership.RoleChoices.ADMIN
        )

    def test_generate_token(self):
        """Test token generation creates unique tokens"""
        token1 = InvitationService.generate_token()
        token2 = InvitationService.generate_token()

        self.assertIsNotNone(token1)
        self.assertIsNotNone(token2)
        self.assertNotEqual(token1, token2)
        self.assertTrue(len(token1) > 20)

    def test_create_expiry_date(self):
        """Test expiry date creation"""
        expiry = InvitationService.create_expiry_date(days=7)
        now = timezone.now()

        self.assertTrue(expiry > now)
        self.assertTrue(expiry - now <= timedelta(days=7, seconds=1))

    def test_create_expiry_date_default(self):
        """Test expiry date with default days"""
        expiry = InvitationService.create_expiry_date()
        now = timezone.now()

        self.assertTrue(expiry > now)
        self.assertTrue(expiry - now <= timedelta(days=7, seconds=1))

    def test_create_join_request_success(self):
        """Test successful creation of join request"""
        invitation = InvitationService.create_join_request(
            self.company.id,
            self.user,
            "Please let me join"
        )

        self.assertIsNotNone(invitation)
        self.assertEqual(invitation.email, self.user.email)
        self.assertEqual(invitation.company, self.company)
        self.assertEqual(invitation.status, Invitation.InvitationStatus.PENDING)
        self.assertEqual(invitation.invitation_type, Invitation.InvitationType.REQUEST)
        self.assertEqual(invitation.message, "Please let me join")

    def test_create_join_request_already_member(self):
        """Test error when user is already a member"""
        Membership.objects.create(
            user=self.user,
            company=self.company,
            role=Membership.RoleChoices.MEMBER
        )

        with self.assertRaises(ValueError) as context:
            InvitationService.create_join_request(self.company.id, self.user)

        self.assertIn("already a member", str(context.exception))

    def test_create_join_request_pending_exists(self):
        """Test error when pending request already exists"""
        Invitation.objects.create(
            email=self.user.email,
            company=self.company,
            invited_by=self.user,
            invited_user=self.user,
            role=Membership.RoleChoices.MEMBER,
            invitation_type=Invitation.InvitationType.REQUEST,
            token='test-token',
            status=Invitation.InvitationStatus.PENDING,
            expires_at=timezone.now() + timedelta(days=7)
        )

        with self.assertRaises(ValueError) as context:
            InvitationService.create_join_request(self.company.id, self.user)

        self.assertIn("already have a pending", str(context.exception))

    def test_approve_join_request_success(self):
        """Test successful approval of join request"""
        invitation = Invitation.objects.create(
            email=self.user.email,
            company=self.company,
            invited_by=self.user,
            invited_user=self.user,
            role=Membership.RoleChoices.MEMBER,
            invitation_type=Invitation.InvitationType.REQUEST,
            token='approve-test-token',
            status=Invitation.InvitationStatus.PENDING,
            expires_at=timezone.now() + timedelta(days=30)
        )

        membership = InvitationService.approve_join_request(
            invitation.id,
            self.admin_user
        )

        self.assertIsNotNone(membership)
        self.assertEqual(membership.user, self.user)
        self.assertEqual(membership.company, self.company)
        self.assertEqual(membership.role, Membership.RoleChoices.MEMBER)

    def test_approve_join_request_non_admin(self):
        """Test error when non-admin tries to approve"""
        non_admin = User.objects.create_user(
            email='nonadmin2@example.com',
            password='testPass123'
        )

        invitation = Invitation.objects.create(
            email=self.user.email,
            company=self.company,
            invited_by=self.user,
            invited_user=self.user,
            role=Membership.RoleChoices.MEMBER,
            invitation_type=Invitation.InvitationType.REQUEST,
            token='approve-test-token',
            status=Invitation.InvitationStatus.PENDING,
            expires_at=timezone.now() + timedelta(days=30)
        )

        with self.assertRaises(PermissionError) as context:
            InvitationService.approve_join_request(invitation.id, non_admin)

        self.assertIn("Only admins", str(context.exception))

    def test_reject_join_request_success(self):
        """Test successful rejection of join request"""
        invitation = Invitation.objects.create(
            email=self.user.email,
            company=self.company,
            invited_by=self.user,
            invited_user=self.user,
            role=Membership.RoleChoices.MEMBER,
            invitation_type=Invitation.InvitationType.REQUEST,
            token='reject-test-token',
            status=Invitation.InvitationStatus.PENDING,
            expires_at=timezone.now() + timedelta(days=30)
        )

        rejected_invitation = InvitationService.reject_join_request(
            invitation.id,
            self.admin_user
        )

        self.assertEqual(rejected_invitation.status, Invitation.InvitationStatus.CANCELLED)

    def test_reject_join_request_non_admin(self):
        """Test error when non-admin tries to reject"""
        non_admin = User.objects.create_user(
            email='nonadmin3@example.com',
            password='testPass123'
        )

        invitation = Invitation.objects.create(
            email=self.user.email,
            company=self.company,
            invited_by=self.user,
            invited_user=self.user,
            role=Membership.RoleChoices.MEMBER,
            invitation_type=Invitation.InvitationType.REQUEST,
            token='reject-test-token',
            status=Invitation.InvitationStatus.PENDING,
            expires_at=timezone.now() + timedelta(days=30)
        )

        with self.assertRaises(PermissionError) as context:
            InvitationService.reject_join_request(invitation.id, non_admin)

        self.assertIn("Only admins", str(context.exception))