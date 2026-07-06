from unittest.mock import patch, MagicMock, PropertyMock
from datetime import timedelta

from django.core.cache import cache
from django.test import override_settings, TestCase
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.db import connection, IntegrityError, DatabaseError
from django.test.utils import CaptureQueriesContext
from django.utils.text import slugify
from django.utils import timezone

from rest_framework.test import APITestCase, APIClient
from rest_framework import status

from .models import Company, Membership, Invitation
from .views import CompanyDetailView
from taskflow.notifications.models import Notification
from .tasks import reject_invitation_task, create_member_invitation_task

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
        self.assertEqual(company.name, 'tech innovations inc')
        self.assertEqual(company.slug, 'tech-innovations')
        self.assertEqual(company.email, 'contact@techinnovations.com')
        self.assertEqual(company.owner, self.owner)

        # بررسی membership برای owner
        owner_membership = Membership.objects.get(user=self.owner, company=company)
        self.assertEqual(owner_membership.role, Membership.RoleChoices.OWNER)

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
        self.assertEqual(company.name, 'auto slug company')

        # بررسی اینکه owner به عنوان ADMIN اضافه شده
        self.assertTrue(
            Membership.objects.filter(
                user=self.owner,
                company=company,
                role=Membership.RoleChoices.OWNER
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
        self.assertEqual(owner_membership.role, Membership.RoleChoices.OWNER)

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
        self.assertEqual(company.name, 'custom company')
        self.assertEqual(company.email, 'custom@company.com')

        # بررسی تعداد اعضا (owner + 1 member)
        self.assertEqual(company.members.count(), 2)
        self.assertIn(self.owner, company.members.all())
        self.assertIn(self.member1, company.members.all())

        # بررسی نقش owner
        owner_membership = Membership.objects.get(user=self.owner, company=company)
        self.assertEqual(owner_membership.role, Membership.RoleChoices.OWNER)

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
        self.assertEqual(owner_membership.role, Membership.RoleChoices.OWNER)

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
                role=Membership.RoleChoices.OWNER
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
                    role=Membership.RoleChoices.OWNER
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

        companies = Company.objects.filter(name='same name company')
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
        self.assertEqual(owner_memberships.first().role, Membership.RoleChoices.OWNER)

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


class RequestJoinCompanyViewTest(APITestCase):

    def setUp(self):
        """Setup test data"""
        # Create test user
        self.user = User.objects.create_user(
            email='test@example.com',
            password='passTest123',
            first_name='Test',
            last_name='User'
        )

        # Create company admin
        self.admin_user = User.objects.create_user(
            email='admin@example.com',
            password='passTest123',
            first_name='Admin',
            last_name='User'
        )

        # Create test company
        self.company = Company.objects.create(
            name='test company',
            slug='test-company',
            owner=self.admin_user,
            is_active = True,
            email = 'test@company.com'
        )

        # Add admin as member with admin role
        self.admin_membership = Membership.objects.create(
            user=self.admin_user,
            company=self.company,
            role=Membership.RoleChoices.ADMIN
        )

        # Get the URL for the view
        self.url = reverse('request-join')

    def authenticate(self):
        """Helper method to authenticate user"""
        self.client.force_authenticate(user=self.user)

    @patch('taskflow.companies.views.create_join_request_task.delay')
    def test_successful_join_request(self, mock_delay):
        """Test successful join request"""
        # Arrange
        self.authenticate()
        mock_task = MagicMock()
        mock_task.id = 'test-task-123'
        mock_task.status = 'PENDING'
        mock_delay.return_value = mock_task

        data = {
            'company_name': 'test company',
            'message': 'I would like to join this company'
        }

        # Act
        response = self.client.post(self.url, data, format='json')

        # Assert
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(response.data['task_id'], 'test-task-123')
        self.assertEqual(response.data['status'], 'PENDING')
        self.assertEqual(response.data['message'], 'Join request is being processed asynchronously')

        # Verify task was called with correct arguments
        mock_delay.assert_called_once_with(
            company_name='test company',
            user_id=self.user.id,
            message='I would like to join this company'
        )

    @patch('taskflow.companies.views.create_join_request_task.delay')
    def test_successful_join_request_without_message(self, mock_delay):
        """Test successful join request without providing a message"""
        # Arrange
        self.authenticate()
        mock_task = MagicMock()
        mock_task.id = 'test-task-123'
        mock_task.status = 'PENDING'
        mock_delay.return_value = mock_task

        data = {
            'company_name': 'test company'
        }

        # Act
        response = self.client.post(self.url, data, format='json')

        # Assert
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)

        # Verify task was called with empty message
        mock_delay.assert_called_once_with(
            company_name='test company',
            user_id=self.user.id,
            message=''
        )

    def test_unauthenticated_user(self):
        """Test that unauthenticated users cannot access the endpoint"""
        # Arrange
        data = {
            'company_name': 'test company'
        }

        # Act
        response = self.client.post(self.url, data, format='json')

        # Assert
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_company_does_not_exist(self):
        """Test requesting to join a non-existent company"""
        # Arrange
        self.authenticate()
        data = {
            'company_name': 'nonexistentcompany'
        }

        # Act
        response = self.client.post(self.url, data, format='json')

        # Assert
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.data['error'],
            'Company does not exist or is not active.'
        )

    def test_inactive_company(self):
        """Test requesting to join an inactive company"""
        # Arrange
        self.authenticate()
        inactive_company = Company.objects.create(
            name='inactivecompany',
            owner=self.admin_user,
            is_active=False,
            email='inactive@company.com'
        )
        data = {
            'company_name': 'inactivecompany'
        }

        # Act
        response = self.client.post(self.url, data, format='json')

        # Assert
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.data['error'],
            'Company does not exist or is not active.'
        )

    def test_user_already_member(self):
        """Test user cannot request to join when already a member"""
        # Arrange
        self.authenticate()
        # Make user a member of the company
        Membership.objects.create(
            user=self.user,
            company=self.company,
            role=Membership.RoleChoices.MEMBER,
        )

        data = {
            'company_name': 'test company'
        }

        # Act
        response = self.client.post(self.url, data, format='json')

        # Assert
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.data['error'],
            'You are already a member of this company'
        )

    def test_pending_request_already_exists(self):
        """Test user cannot request to join if they already have a pending request"""
        # Arrange
        self.authenticate()

        # Create a pending request invitation
        Invitation.objects.create(
            email=self.user.email,
            company=self.company,
            invited_by=self.admin_user,
            invited_user=self.user,
            role=Membership.RoleChoices.MEMBER,
            invitation_type=Invitation.InvitationType.REQUEST,
            token='test-token-123',
            status=Invitation.InvitationStatus.PENDING,
            message='I want to join',
            expires_at=timezone.now() + timedelta(days=7)
        )

        data = {
            'company_name': 'test company'
        }

        # Act
        response = self.client.post(self.url, data, format='json')

        # Assert
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.data['error'],
            'You already have a pending join request'
        )

    def test_company_name_case_insensitive(self):
        """Test that company name lookup is case insensitive"""
        # Arrange
        self.authenticate()
        mock_task = MagicMock()
        mock_task.id = 'test-task-123'
        mock_task.status = 'PENDING'

        with patch('taskflow.companies.views.create_join_request_task.delay') as mock_delay:
            mock_delay.return_value = mock_task

            # Act - use uppercase company name
            data = {
                'company_name': 'TEST COMPANY'
            }
            response = self.client.post(self.url, data, format='json')

            # Assert
            self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
            # Verify the task uses the provided name (which is in uppercase)
            mock_delay.assert_called_once_with(
                company_name='TEST COMPANY',
                user_id=self.user.id,
                message=''
            )


class RequestJoinCompanyViewIntegrationTest(APITestCase):
    """
    Integration tests that verify the complete flow with the actual Celery task
    """

    def setUp(self):
        """Setup test data"""
        self.user = User.objects.create_user(
            email='test@example.com',
            password='passTest123',
            first_name='Test',
            last_name='User'
        )

        self.admin_user = User.objects.create_user(
            email='admin_integ@example.com',
            password='passTest123',
            first_name='Admin',
            last_name='User'
        )

        self.company = Company.objects.create(
            name='integtestcompany',
            owner=self.admin_user,
            is_active=True,
            email='integtest@company.com'
        )

        self.admin_membership = Membership.objects.create(
            user=self.admin_user,
            company=self.company,
            role=Membership.RoleChoices.ADMIN,
        )

        self.url = reverse('request-join')

    def authenticate(self):
        self.client.force_authenticate(user=self.user)

    @patch('taskflow.companies.tasks.send_notification_to_admins')
    def test_complete_flow_with_mocked_notifications(self, mock_notify):
        """Test complete flow with mocked notification service"""
        # Arrange
        self.authenticate()
        mock_notify.return_value = 1

        from taskflow.companies.tasks import create_join_request_task

        with patch('taskflow.companies.views.create_join_request_task.delay') as mock_delay:
            def side_effect(*args, **kwargs):

                result = create_join_request_task(*args, **kwargs)

                mock_async_result = MagicMock()
                mock_async_result.id = 'test-task-123'
                mock_async_result.status = 'PENDING'

                mock_async_result.result = result

                return mock_async_result

            mock_delay.side_effect = side_effect

            data = {
                'company_name': 'integtestcompany',
                'message': 'Please accept my request'
            }

            # Act
            response = self.client.post(self.url, data, format='json')

            # Assert
            self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
            self.assertEqual(response.data['task_id'], 'test-task-123')

            # Verify the invitation was created
            invitation_exists = Invitation.objects.filter(
                email=self.user.email,
                company=self.company,
                status=Invitation.InvitationStatus.PENDING,
                invitation_type=Invitation.InvitationType.REQUEST
            ).exists()

            self.assertTrue(invitation_exists)

            # Verify admin notification was called
            mock_notify.assert_called_once()

    def test_duplicate_request_prevention(self):
        """Test that user cannot create duplicate join requests"""
        # Arrange
        self.authenticate()

        # Create first pending request
        Invitation.objects.create(
            email=self.user.email,
            company=self.company,
            invited_by=self.admin_user,
            invited_user=self.user,
            role=Membership.RoleChoices.MEMBER,
            invitation_type=Invitation.InvitationType.REQUEST,
            token='test-token-456',
            status=Invitation.InvitationStatus.PENDING,
            message='First request',
            expires_at=timezone.now() + timedelta(days=7)
        )

        data = {
            'company_name': 'integtestcompany'
        }

        # Act
        response = self.client.post(self.url, data, format='json')

        # Assert
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.data['error'],
            'You already have a pending join request'
        )


@override_settings(CELERY_ALWAYS_EAGER=True, CELERY_EAGER_PROPAGATES_EXCEPTIONS=True)
class AcceptJoinRequestTests(APITestCase):

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

        # اصلاح: استفاده از پیام واقعی ویو
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(response.data['message'], 'Join request is being processed')  # اصلاح شده
        self.assertIn('task_id', response.data)

        # اجرای همگام تسک برای تست
        from taskflow.companies.tasks import accept_invitation_task
        result = accept_invitation_task(
            token=self.invitation.token,
            admin_id=self.admin_user.id
        )

        # بررسی نتیجه تسک
        self.assertEqual(result['status'], 'success')
        self.assertEqual(result['user_id'], self.user.id)
        self.assertEqual(result['company_id'], self.company.id)

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

        # ویو همیشه 202 برمی‌گرداند، پس باید تسک را بررسی کنیم
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(response.data['message'], 'Join request is being processed')
        self.assertIn('task_id', response.data)

        # اجرای همگام تسک و بررسی خطای دسترسی
        from taskflow.companies.tasks import accept_invitation_task

        with self.assertRaises(PermissionError) as context:
            accept_invitation_task(
                token=self.invitation.token,
                admin_id=self.non_admin_user.id
            )

        self.assertIn('Only admins can approve', str(context.exception))

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

        # ویو همیشه 202 برمی‌گرداند
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(response.data['message'], 'Join request is being processed')
        self.assertIn('task_id', response.data)

        # اجرای همگام تسک و بررسی خطا
        from taskflow.companies.tasks import accept_invitation_task
        result = accept_invitation_task(
            token='non-existent-token',  # توکن ناموجود
            admin_id=self.admin_user.id
        )

        # تسک باید خطا برگرداند
        self.assertEqual(result['status'], 'error')
        self.assertIn('Invitation not found or already processed', result['error'])

    def test_approve_already_approved_request(self):
        """Test that approving an already approved request fails"""
        self.invitation.status = Invitation.InvitationStatus.ACCEPTED
        self.invitation.save()

        self.authenticate(self.admin_user)

        response = self.client.post(self.url, format='json')

        # اصلاح: استفاده از پیام واقعی ویو
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(response.data['message'], 'Join request is being processed')  # اصلاح شده

        # اجرای تسک و بررسی خطا
        from taskflow.companies.tasks import accept_invitation_task
        result = accept_invitation_task(
            token=self.invitation.token,
            admin_id=self.admin_user.id
        )

        # تسک باید خطا برگرداند چون درخواست قبلاً تایید شده
        self.assertEqual(result['status'], 'error')
        self.assertIn('Invitation not found or already processed', result['error'])

    def test_approve_request_with_cache_invalidation(self):
        """Test that cache is invalidated after approval"""
        self.authenticate(self.admin_user)

        # Set some cache
        cache.set(f"notification_list_user_{self.user.id}_page1", "test_data")
        cache.set(f"notification_list_user_{self.admin_user.id}_page1", "test_data")

        response = self.client.post(self.url, format='json')
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)

        # Execute task synchronously
        from taskflow.companies.tasks import accept_invitation_task
        result = accept_invitation_task(
            token=self.invitation.token,
            admin_id=self.admin_user.id
        )

        self.assertEqual(result['status'], 'success')

        # Verify cache was invalidated
        self.assertIsNone(cache.get(f"notification_list_user_{self.user.id}_page1"))
        self.assertIsNone(cache.get(f"notification_list_user_{self.admin_user.id}_page1"))

    def test_approve_request_notification_created(self):
        """Test that notification is created after approval"""
        self.authenticate(self.admin_user)

        response = self.client.post(self.url, format='json')
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)

        # Execute task synchronously
        from taskflow.companies.tasks import accept_invitation_task
        result = accept_invitation_task(
            token=self.invitation.token,
            admin_id=self.admin_user.id
        )

        self.assertEqual(result['status'], 'success')

        # Verify notification was created - اصلاح: استفاده از مدل صحیح
        notification_exists = Notification.objects.filter(
            recipient=self.user,
            notification_type=Notification.NotificationType.JOIN_APPROVED,
            company=self.company
        ).exists()
        self.assertTrue(notification_exists)

        # Verify admin's notification was marked as read
        admin_notification = Notification.objects.filter(
            recipient=self.admin_user,
            invitation=self.invitation,
            notification_type=Notification.NotificationType.JOIN_REQUEST
        ).first()

        if admin_notification:
            self.assertEqual(admin_notification.status, Notification.NotificationStatus.READ)
            self.assertIsNotNone(admin_notification.read_at)


@override_settings(CELERY_ALWAYS_EAGER=True, CELERY_EAGER_PROPAGATES_EXCEPTIONS=True)
class RejectJoinRequestTests(APITestCase):

    def setUp(self):
        """Set up test data"""
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
            password='testPass123',
            first_name='Non',
            last_name='Admin'
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

        self.url = reverse('reject-request', args=[self.invitation.token])

    def authenticate(self, user):
        """Helper method to authenticate a user"""
        self.client.force_authenticate(user=user)

    def test_admin_rejects_join_request(self):
        """Test that an admin can reject a join request"""
        self.authenticate(self.admin_user)

        reason = "Position has been filled"
        response = self.client.post(self.url, {'reason': reason}, format='json')

        # Check response
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(response.data['status'], 'processing')
        self.assertEqual(response.data['message'], 'Join request is being processed')
        self.assertEqual(response.data['token'], self.invitation.token)
        self.assertIn('task_id', response.data)

        # Execute task synchronously
        result = reject_invitation_task(
            token=self.invitation.token,
            admin_id=self.admin_user.id,
            reason=reason
        )

        # Verify task result
        self.assertEqual(result['status'], 'success')
        self.assertEqual(result['user_id'], self.user.id)
        self.assertEqual(result['company_id'], self.company.id)
        self.assertEqual(result['reason'], reason)
        self.assertEqual(result['admin_email'], self.admin_user.email)

        # Verify invitation status was updated
        self.invitation.refresh_from_db()
        self.assertEqual(self.invitation.status, Invitation.InvitationStatus.CANCELLED)

        # Verify notification was created
        notification_exists = Notification.objects.filter(
            recipient=self.user,
            notification_type=Notification.NotificationType.JOIN_REJECTED,
            company=self.company
        ).exists()
        self.assertTrue(notification_exists)

        # Verify admin's notification was marked as read
        admin_notification = Notification.objects.filter(
            recipient=self.admin_user,
            invitation=self.invitation,
            notification_type=Notification.NotificationType.JOIN_REQUEST
        ).first()

        if admin_notification:
            self.assertEqual(admin_notification.status, Notification.NotificationStatus.READ)
            self.assertIsNotNone(admin_notification.read_at)

        # Verify membership was NOT created
        membership_exists = Membership.objects.filter(
            user=self.user,
            company=self.company
        ).exists()
        self.assertFalse(membership_exists)

    def test_admin_rejects_join_request_without_reason(self):
        """Test that an admin can reject a join request without providing a reason"""
        self.authenticate(self.admin_user)

        response = self.client.post(self.url, format='json')

        # Check response
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(response.data['status'], 'processing')

        # Execute task synchronously
        result = reject_invitation_task(
            token=self.invitation.token,
            admin_id=self.admin_user.id,
            reason=None
        )

        # Verify task result
        self.assertEqual(result['status'], 'success')
        self.assertEqual(result['reason'], None)

        # Verify invitation status was updated
        self.invitation.refresh_from_db()
        self.assertEqual(self.invitation.status, Invitation.InvitationStatus.CANCELLED)

        # Verify notification was created with default message
        notification = Notification.objects.filter(
            recipient=self.user,
            notification_type=Notification.NotificationType.JOIN_REJECTED,
            company=self.company
        ).first()

        self.assertIsNotNone(notification)
        self.assertIn(f"درخواست شما برای عضویت در {self.company.name}", notification.message)
        self.assertNotIn("دلیل:", notification.message)

    def test_reject_already_rejected_request(self):
        """Test that rejecting an already rejected request fails"""
        # First, reject the invitation
        self.invitation.status = Invitation.InvitationStatus.CANCELLED
        self.invitation.save()

        self.authenticate(self.admin_user)

        response = self.client.post(self.url, format='json')

        # View should return 202 Accepted (sends to task)
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)

        # Execute task and check error
        result = reject_invitation_task(
            token=self.invitation.token,
            admin_id=self.admin_user.id,
            reason=None
        )

        # Task should return error because invitation is already processed
        self.assertEqual(result['status'], 'error')
        self.assertEqual(result['error'], 'Invitation not found or already processed')

    def test_reject_request_cache_invalidation(self):
        """Test that cache is invalidated after rejection"""
        self.authenticate(self.admin_user)

        # Set some cache
        cache.set(f"notification_list_user_{self.user.id}_page1", "test_data")
        cache.set(f"notification_list_user_{self.admin_user.id}_page1", "test_data")

        response = self.client.post(self.url, format='json')
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)

        # Execute task synchronously
        result = reject_invitation_task(
            token=self.invitation.token,
            admin_id=self.admin_user.id,
            reason="Test reason"
        )

        self.assertEqual(result['status'], 'success')

        # Verify cache was invalidated
        self.assertIsNone(cache.get(f"notification_list_user_{self.user.id}_page1"))
        self.assertIsNone(cache.get(f"notification_list_user_{self.admin_user.id}_page1"))

    def test_reject_request_notification_created(self):
        """Test that notification is created after rejection"""
        self.authenticate(self.admin_user)

        reason = "Position no longer available"
        response = self.client.post(self.url, {'reason': reason}, format='json')
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)

        # Execute task synchronously
        result = reject_invitation_task(
            token=self.invitation.token,
            admin_id=self.admin_user.id,
            reason=reason
        )

        self.assertEqual(result['status'], 'success')

        # Verify notification was created for the user
        user_notification = Notification.objects.filter(
            recipient=self.user,
            notification_type=Notification.NotificationType.JOIN_REJECTED,
            company=self.company
        ).first()

        self.assertIsNotNone(user_notification)
        self.assertEqual(user_notification.sender, self.admin_user)
        self.assertEqual(user_notification.invitation, self.invitation)
        self.assertIn(reason, user_notification.message)

        # Verify notification was marked as read for admin
        admin_notification = Notification.objects.filter(
            recipient=self.admin_user,
            invitation=self.invitation,
            notification_type=Notification.NotificationType.JOIN_REQUEST
        ).first()

        if admin_notification:
            self.assertEqual(admin_notification.status, Notification.NotificationStatus.READ)
            self.assertIsNotNone(admin_notification.read_at)
            self.assertEqual(admin_notification.metadata['reason'], 'request_rejected')

    def test_reject_request_unauthorized(self):
        """Test that unauthenticated users cannot reject requests"""
        response = self.client.post(self.url, format='json')

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_reject_request_with_special_characters_in_reason(self):
        """Test that reject request handles special characters in reason"""
        self.authenticate(self.admin_user)

        reason = "Position filled - New candidate already hired! 🎉"
        response = self.client.post(self.url, {'reason': reason}, format='json')

        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)

        # Execute task synchronously
        result = reject_invitation_task(
            token=self.invitation.token,
            admin_id=self.admin_user.id,
            reason=reason
        )

        self.assertEqual(result['status'], 'success')

        # Verify notification contains the reason with special characters
        notification = Notification.objects.filter(
            recipient=self.user,
            notification_type=Notification.NotificationType.JOIN_REJECTED
        ).first()

        self.assertIsNotNone(notification)
        self.assertIn(reason, notification.message)

    def test_reject_request_task_atomic_transaction(self):
        """Test that the task uses atomic transaction for consistency"""
        self.authenticate(self.admin_user)

        response = self.client.post(self.url, format='json')
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)

        # Execute task
        result = reject_invitation_task(
            token=self.invitation.token,
            admin_id=self.admin_user.id,
            reason="Test"
        )

        self.assertEqual(result['status'], 'success')

        # Verify all changes were applied atomically
        self.invitation.refresh_from_db()
        self.assertEqual(self.invitation.status, Invitation.InvitationStatus.CANCELLED)

        # Both notifications should exist
        user_notification = Notification.objects.filter(
            recipient=self.user,
            notification_type=Notification.NotificationType.JOIN_REJECTED
        ).exists()
        self.assertTrue(user_notification)

        # Admin notification should be marked as read
        admin_notification = Notification.objects.filter(
            recipient=self.admin_user,
            invitation=self.invitation,
            notification_type=Notification.NotificationType.JOIN_REQUEST
        ).first()

        if admin_notification:
            self.assertEqual(admin_notification.status, Notification.NotificationStatus.READ)

    def test_reject_request_view_handles_exceptions(self):
        """Test that the view handles exceptions properly"""
        self.authenticate(self.admin_user)

        # Mock the task to raise an exception
        from unittest.mock import patch

        with patch('taskflow.companies.tasks.reject_invitation_task.delay') as mock_delay:
            mock_delay.side_effect = PermissionError("Permission denied")

            response = self.client.post(self.url, format='json')

            # Should handle PermissionError
            self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
            self.assertEqual(response.data['error'], 'permission_denied')

        with patch('taskflow.companies.tasks.reject_invitation_task.delay') as mock_delay:
            mock_delay.side_effect = ValueError("Invitation has expired")

            response = self.client.post(self.url, format='json')

            # Should handle ValueError
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertEqual(response.data['error'], 'invitation_expired')

        with patch('taskflow.companies.tasks.reject_invitation_task.delay') as mock_delay:
            mock_delay.side_effect = Invitation.DoesNotExist()

            response = self.client.post(self.url, format='json')

            # Should handle DoesNotExist
            self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
            self.assertEqual(response.data['error'], 'invitation_not_found')

        with patch('taskflow.companies.tasks.reject_invitation_task.delay') as mock_delay:
            mock_delay.side_effect = Exception("Unexpected error")

            response = self.client.post(self.url, format='json')

            # Should handle unexpected errors
            self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)
            self.assertEqual(response.data['error'], 'internal_server_error')


class SendMemberInvitationViewTest(TestCase):
    """Test cases for SendMemberInvitationView"""

    def setUp(self):
        """Set up test data"""
        cache.clear()

        # Create users
        self.owner_user = User.objects.create_user(
            email='owner@example.com',
            password='testPass123',
            first_name='Owner',
            last_name='User'
        )

        self.admin_user = User.objects.create_user(
            email='admin@example.com',
            password='testPass123',
            first_name='Admin',
            last_name='User'
        )

        self.member_user = User.objects.create_user(
            email='member@example.com',
            password='testPass123',
            first_name='Member',
            last_name='User'
        )

        self.invited_user = User.objects.create_user(
            email='invited@example.com',
            password='testPass123',
            first_name='Invited',
            last_name='User'
        )

        self.non_member_user = User.objects.create_user(
            email='nonmember@example.com',
            password='testPass123',
            first_name='Non',
            last_name='Member'
        )

        # Create a company
        self.company = Company.objects.create(
            name='Test Company',
            slug='test-company',
            owner=self.owner_user,
            is_active=True
        )

        # Create inactive company
        self.inactive_company = Company.objects.create(
            name='Inactive Company',
            slug='inactive-company',
            owner=self.owner_user,
            is_active=False
        )

        # Create memberships
        Membership.objects.create(
            user=self.owner_user,
            company=self.company,
            role=Membership.RoleChoices.OWNER
        )

        Membership.objects.create(
            user=self.admin_user,
            company=self.company,
            role=Membership.RoleChoices.ADMIN
        )

        Membership.objects.create(
            user=self.member_user,
            company=self.company,
            role=Membership.RoleChoices.MEMBER
        )

        # URL for inviting member
        self.url = reverse('invite-member', args=[self.company.id])

        # API client
        self.client = APIClient()

    def authenticate(self, user):
        """Helper method to authenticate a user"""
        self.client.force_authenticate(user=user)

    def test_successful_invitation_by_owner(self):
        """Test successful invitation by company owner"""
        self.authenticate(self.owner_user)

        data = {
            'user_email': self.invited_user.email,
            'role': Membership.RoleChoices.MEMBER
        }

        with patch('taskflow.companies.tasks.create_member_invitation_task.delay') as mock_task:
            mock_task.return_value.id = 'test-task-123'

            response = self.client.post(self.url, data, format='json')

            self.assertEqual(response.status_code, status.HTTP_201_CREATED)
            self.assertEqual(response.data['status'], 'processing')
            self.assertEqual(response.data['task_id'], 'test-task-123')
            self.assertIn('message', response.data)

            # Verify task was called with correct parameters
            mock_task.assert_called_once_with(
                company_id=self.company.id,
                invited_user_id=self.invited_user.id,
                inviter_id=self.owner_user.id,
                role=Membership.RoleChoices.MEMBER
            )

    def test_successful_invitation_by_admin(self):
        """Test successful invitation by company admin"""
        self.authenticate(self.admin_user)

        data = {
            'user_email': self.invited_user.email
        }

        with patch('taskflow.companies.tasks.create_member_invitation_task.delay') as mock_task:
            mock_task.return_value.id = 'test-task-123'

            response = self.client.post(self.url, data, format='json')

            self.assertEqual(response.status_code, status.HTTP_201_CREATED)
            mock_task.assert_called_once_with(
                company_id=self.company.id,
                invited_user_id=self.invited_user.id,
                inviter_id=self.admin_user.id,
                role=Membership.RoleChoices.MEMBER  # Default role
            )

    def test_invitation_by_non_admin_member(self):
        """Test that regular members cannot invite others"""
        self.authenticate(self.member_user)

        data = {
            'user_email': self.invited_user.email
        }

        response = self.client.post(self.url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(
            response.data['error'],
            'You do not have permission to invite members'
        )

    def test_invitation_to_inactive_company(self):
        """Test invitation to inactive company"""
        self.authenticate(self.owner_user)

        url = reverse('invite-member', args=[self.inactive_company.id])
        data = {
            'user_email': self.invited_user.email
        }

        response = self.client.post(url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.data['error'], 'Company not found or inactive')

    def test_invitation_to_nonexistent_company(self):
        """Test invitation to non-existent company"""
        self.authenticate(self.owner_user)

        url = reverse('invite-member', args=[99999])
        data = {
            'user_email': self.invited_user.email
        }

        response = self.client.post(url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_invitation_to_existing_member(self):
        """Test invitation to user who is already a member"""
        self.authenticate(self.owner_user)

        data = {
            'user_email': self.member_user.email
        }

        response = self.client.post(self.url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('non_field_errors', response.data)
        self.assertEqual(
            response.data['non_field_errors'][0],
            f"{self.member_user.email} is already a member"
        )

    def test_invitation_with_pending_invitation(self):
        """Test invitation to user with pending invitation"""
        # Create pending invitation
        Invitation.objects.create(
            email=self.invited_user.email,
            company=self.company,
            invited_by=self.admin_user,
            invited_user=self.invited_user,
            role=Membership.RoleChoices.MEMBER,
            invitation_type=Invitation.InvitationType.MEMBER_INVITE,
            token='pending-token-123',
            status=Invitation.InvitationStatus.PENDING,
            expires_at=timezone.now() + timedelta(days=7)
        )

        self.authenticate(self.owner_user)

        data = {
            'user_email': self.invited_user.email
        }

        response = self.client.post(self.url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.data['non_field_errors'][0],
            f"An invitation already exists for {self.invited_user.email}"
        )

    def test_invitation_to_self(self):
        """Test that user cannot invite themselves"""
        self.authenticate(self.owner_user)

        data = {
            'user_email': self.owner_user.email
        }

        response = self.client.post(self.url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.data['non_field_errors'][0],
            "owner@example.com is already a member"
        )

    def test_invitation_to_nonexistent_user(self):
        """Test invitation to non-existent user email"""
        self.authenticate(self.owner_user)

        data = {
            'user_email': 'nonexistent@example.com'
        }

        response = self.client.post(self.url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.data['non_field_errors'][0],
            'No user found with email: nonexistent@example.com'
        )

    def test_invitation_without_authentication(self):
        """Test invitation without authentication"""
        data = {
            'user_email': self.invited_user.email
        }

        response = self.client.post(self.url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_invitation_with_invalid_email_format(self):
        """Test invitation with invalid email format"""
        self.authenticate(self.owner_user)

        data = {
            'user_email': 'invalid-email'
        }

        response = self.client.post(self.url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('user_email', response.data)

    def test_invitation_with_empty_email(self):
        """Test invitation with empty email"""
        self.authenticate(self.owner_user)

        data = {
            'user_email': ''
        }

        response = self.client.post(self.url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('user_email', response.data)

    def test_invitation_with_invalid_role(self):
        """Test invitation with invalid role"""
        self.authenticate(self.owner_user)

        data = {
            'user_email': self.invited_user.email,
            'role': 'INVALID_ROLE'
        }

        response = self.client.post(self.url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('role', response.data)

    @patch('taskflow.companies.views.create_member_invitation_task.delay')
    def test_invitation_handles_integrity_error(self, mock_task):
        """Test handling of IntegrityError when creating invitation"""
        self.authenticate(self.owner_user)

        mock_task.side_effect = IntegrityError("Duplicate entry")

        data = {
            'user_email': self.invited_user.email
        }

        response = self.client.post(self.url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)
        self.assertEqual(response.data['error'], 'Database integrity error')
        self.assertEqual(response.data['code'], 'INTEGRITY_ERROR')

    @patch('taskflow.companies.views.create_member_invitation_task.delay')
    def test_invitation_handles_database_error(self, mock_task):
        """Test handling of DatabaseError when creating invitation"""
        self.authenticate(self.owner_user)

        mock_task.side_effect = DatabaseError("Connection error")

        data = {
            'user_email': self.invited_user.email
        }

        response = self.client.post(self.url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)
        self.assertEqual(response.data['error'], 'Database error occurred')
        self.assertEqual(response.data['code'], 'DATABASE_ERROR')

    @patch('taskflow.companies.views.create_member_invitation_task.delay')
    def test_invitation_handles_general_exception(self, mock_task):
        """Test handling of general exception when creating invitation"""
        self.authenticate(self.owner_user)

        mock_task.side_effect = Exception("Unexpected error")

        data = {
            'user_email': self.invited_user.email
        }

        response = self.client.post(self.url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)
        self.assertEqual(response.data['error'], 'Failed to send invitation')
        self.assertEqual(response.data['code'], 'TASK_FAILED')


class CreateMemberInvitationTaskTest(TestCase):
    """Test cases for create_member_invitation_task"""

    def setUp(self):
        """Set up test data"""
        cache.clear()

        # Create users
        self.inviter = User.objects.create_user(
            email='inviter@example.com',
            password='testPass123',
            first_name='Inviter',
            last_name='User'
        )

        self.invited_user = User.objects.create_user(
            email='invited@example.com',
            password='testPass123',
            first_name='Invited',
            last_name='User'
        )

        # Create a company
        self.company = Company.objects.create(
            name='Test Company',
            slug='test-company',
            owner=self.inviter,
            is_active=True
        )

        # Create inactive company
        self.inactive_company = Company.objects.create(
            name='Inactive Company',
            slug='inactive-company',
            owner=self.inviter,
            is_active=False
        )

    def test_successful_invitation_creation(self):
        """Test successful creation of invitation"""
        result = create_member_invitation_task(
            company_id=self.company.id,
            invited_user_id=self.invited_user.id,
            inviter_id=self.inviter.id,
            role=Membership.RoleChoices.MEMBER
        )

        self.assertEqual(result['status'], 'success')
        self.assertEqual(result['company_id'], self.company.id)
        self.assertEqual(result['company_name'], self.company.name)
        self.assertEqual(result['invited_user_id'], self.invited_user.id)
        self.assertEqual(result['invited_user_email'], self.invited_user.email)
        self.assertEqual(result['inviter_id'], self.inviter.id)
        self.assertEqual(result['inviter_email'], self.inviter.email)
        self.assertEqual(result['role'], Membership.RoleChoices.MEMBER)

        # Check invitation was created
        invitation = Invitation.objects.get(id=result['invitation_id'])
        self.assertEqual(invitation.email, self.invited_user.email)
        self.assertEqual(invitation.company, self.company)
        self.assertEqual(invitation.invited_by, self.inviter)
        self.assertEqual(invitation.invited_user, self.invited_user)
        self.assertEqual(invitation.role, Membership.RoleChoices.MEMBER)
        self.assertEqual(invitation.invitation_type, Invitation.InvitationType.MEMBER_INVITE)
        self.assertEqual(invitation.status, Invitation.InvitationStatus.PENDING)
        self.assertIsNotNone(invitation.token)
        # secrets.token_urlsafe(32) returns a string of length 43 (32 bytes base64 encoded)
        self.assertEqual(len(invitation.token), 43)
        self.assertIn(self.inviter.email, invitation.message)
        self.assertIn(self.company.name, invitation.message)

        # Check notification was created
        notification = Notification.objects.get(id=result['notification_id'])
        self.assertEqual(notification.recipient, self.invited_user)
        self.assertEqual(notification.sender, self.inviter)
        self.assertEqual(notification.notification_type, Notification.NotificationType.INVITATION)
        self.assertIn(self.company.name, notification.title)
        self.assertIn(self.inviter.email, notification.message)
        self.assertIn(self.company.name, notification.message)
        self.assertEqual(notification.invitation, invitation)
        self.assertEqual(notification.company, self.company)
        self.assertEqual(notification.status, Notification.NotificationStatus.UNREAD)
        self.assertEqual(notification.metadata['invitation_type'], 'member_invite')
        self.assertEqual(notification.metadata['invited_by'], self.inviter.id)
        self.assertEqual(notification.metadata['invited_by_email'], self.inviter.email)
        self.assertEqual(notification.metadata['role'], Membership.RoleChoices.MEMBER)

    def test_successful_invitation_with_admin_role(self):
        """Test successful invitation creation with admin role"""
        result = create_member_invitation_task(
            company_id=self.company.id,
            invited_user_id=self.invited_user.id,
            inviter_id=self.inviter.id,
            role=Membership.RoleChoices.ADMIN
        )

        self.assertEqual(result['status'], 'success')
        self.assertEqual(result['role'], Membership.RoleChoices.ADMIN)

        invitation = Invitation.objects.get(id=result['invitation_id'])
        self.assertEqual(invitation.role, Membership.RoleChoices.ADMIN)

    def test_company_not_found(self):
        """Test invitation with non-existent company"""
        result = create_member_invitation_task(
            company_id=99999,
            invited_user_id=self.invited_user.id,
            inviter_id=self.inviter.id
        )

        self.assertEqual(result['status'], 'error')
        # Remove trailing space from expected error message
        self.assertEqual(result['error'].strip(), 'Company not found or not active')

    def test_inactive_company(self):
        """Test invitation with inactive company"""
        result = create_member_invitation_task(
            company_id=self.inactive_company.id,
            invited_user_id=self.invited_user.id,
            inviter_id=self.inviter.id
        )

        self.assertEqual(result['status'], 'error')
        # Remove trailing space from expected error message
        self.assertEqual(result['error'].strip(), 'Company not found or not active')

    def test_invited_user_not_found(self):
        """Test invitation with non-existent invited user"""
        # Mock get_user to return None for invited user
        with patch('taskflow.companies.tasks.get_user', return_value=None):
            result = create_member_invitation_task(
                company_id=self.company.id,
                invited_user_id=99999,
                inviter_id=self.inviter.id
            )

        self.assertEqual(result['status'], 'error')
        self.assertEqual(result['error'], 'User not found')

    def test_inviter_not_found(self):
        """Test invitation with non-existent inviter"""

        # Mock get_user to return None for inviter
        def mock_get_user(user_id):
            if user_id == self.invited_user.id:
                return self.invited_user
            return None

        with patch('taskflow.companies.tasks.get_user', side_effect=mock_get_user):
            result = create_member_invitation_task(
                company_id=self.company.id,
                invited_user_id=self.invited_user.id,
                inviter_id=99999
            )

        self.assertEqual(result['status'], 'error')
        self.assertEqual(result['error'], 'User not found')

    def test_cache_cleared_after_invitation(self):
        """Test that cache is cleared after creating invitation"""
        # Set some cache key
        cache_key = f'notification_list_user_{self.invited_user.id}'
        cache.set(cache_key, 'test_value')

        # Create invitation
        result = create_member_invitation_task(
            company_id=self.company.id,
            invited_user_id=self.invited_user.id,
            inviter_id=self.inviter.id
        )

        # Check cache was cleared
        self.assertIsNone(cache.get(cache_key))

    def test_invitation_expires_in_7_days(self):
        """Test that invitation expires in 7 days"""
        result = create_member_invitation_task(
            company_id=self.company.id,
            invited_user_id=self.invited_user.id,
            inviter_id=self.inviter.id
        )

        invitation = Invitation.objects.get(id=result['invitation_id'])
        expected_expiry = timezone.now() + timedelta(days=7)

        # Check expiry is within 5 seconds of expected (to account for test execution time)
        time_diff = abs((invitation.expires_at - expected_expiry).total_seconds())
        self.assertLess(time_diff, 5)

    def test_unique_token_generation(self):
        """Test that each invitation gets a unique token"""
        result1 = create_member_invitation_task(
            company_id=self.company.id,
            invited_user_id=self.invited_user.id,
            inviter_id=self.inviter.id
        )

        # Create another user
        another_user = User.objects.create_user(
            email='another@example.com',
            password='testPass123',
            first_name='Another',
            last_name='User'
        )

        result2 = create_member_invitation_task(
            company_id=self.company.id,
            invited_user_id=another_user.id,
            inviter_id=self.inviter.id
        )

        invitation1 = Invitation.objects.get(id=result1['invitation_id'])
        invitation2 = Invitation.objects.get(id=result2['invitation_id'])

        self.assertNotEqual(invitation1.token, invitation2.token)

    @patch('taskflow.companies.tasks.transaction.atomic')
    def test_transaction_rollback_on_error(self, mock_atomic):
        """Test that transaction is rolled back on error"""
        # Force an error during invitation creation
        mock_atomic.side_effect = Exception("Database error")

        # The task will raise an exception, which will trigger retry
        with self.assertRaises(Exception):
            create_member_invitation_task(
                company_id=self.company.id,
                invited_user_id=self.invited_user.id,
                inviter_id=self.inviter.id
            )

        # Verify no invitation was created
        self.assertFalse(Invitation.objects.filter(
            company=self.company,
            invited_user=self.invited_user
        ).exists())

    def test_invitation_message_format(self):
        """Test that invitation message is formatted correctly"""
        result = create_member_invitation_task(
            company_id=self.company.id,
            invited_user_id=self.invited_user.id,
            inviter_id=self.inviter.id
        )

        invitation = Invitation.objects.get(id=result['invitation_id'])
        expected_message = f"{self.inviter.email} invites you to join {self.company.name}"
        self.assertEqual(invitation.message, expected_message)

    def test_notification_content_format(self):
        """Test that notification content is formatted correctly"""
        result = create_member_invitation_task(
            company_id=self.company.id,
            invited_user_id=self.invited_user.id,
            inviter_id=self.inviter.id
        )

        notification = Notification.objects.get(id=result['notification_id'])

        expected_title = f"دعوت به عضویت در {self.company.name}"
        expected_message = f"{self.inviter.email} شما را به عضویت در {self.company.name} دعوت کرده است."
        expected_action_url = f"/invitations/accept/{Invitation.objects.get(id=result['invitation_id']).token}/"

        self.assertEqual(notification.title, expected_title)
        self.assertEqual(notification.message, expected_message)
        self.assertEqual(notification.action_url, expected_action_url)

    def test_task_without_role_uses_default(self):
        """Test that task uses default role when not provided"""
        result = create_member_invitation_task(
            company_id=self.company.id,
            invited_user_id=self.invited_user.id,
            inviter_id=self.inviter.id
            # role not provided
        )

        self.assertEqual(result['status'], 'success')
        self.assertEqual(result['role'], Membership.RoleChoices.MEMBER)

        invitation = Invitation.objects.get(id=result['invitation_id'])
        self.assertEqual(invitation.role, Membership.RoleChoices.MEMBER)

    def test_company_query_uses_is_active_filter(self):
        """Test that company query correctly filters by is_active"""
        # First create an active company
        result = create_member_invitation_task(
            company_id=self.company.id,
            invited_user_id=self.invited_user.id,
            inviter_id=self.inviter.id
        )

        self.assertEqual(result['status'], 'success')

        # Then try inactive company
        result = create_member_invitation_task(
            company_id=self.inactive_company.id,
            invited_user_id=self.invited_user.id,
            inviter_id=self.inviter.id
        )

        self.assertEqual(result['status'], 'error')
        self.assertEqual(result['error'].strip(), 'Company not found or not active')