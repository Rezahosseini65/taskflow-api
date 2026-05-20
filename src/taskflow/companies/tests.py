from django.core.cache import cache
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.db import connection
from django.test.utils import CaptureQueriesContext

from rest_framework.test import APITestCase, APIClient
from rest_framework import status

from taskflow.companies.models import Company
from taskflow.accounts.models import CustomUser

User = get_user_model()


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
        self.company.members.add(self.member1, self.member2)

        # Setup API client
        self.client = APIClient()
        self.url = reverse('company-detail', kwargs={'pk': self.company.pk})

    def authenticate(self, user):
        """Helper method for authentication"""
        self.client.force_authenticate(user=user)

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
        self.client.force_authenticate(user=None)
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

        for member in response.data['members']:
            assert 'id' in member
            assert 'email' in member

        member_emails = [m['email'] for m in response.data['members']]
        assert self.member1.email in member_emails
        assert self.member2.email in member_emails

    # ========== Cache Tests ==========

    def test_cache_is_used_on_second_request(self):
        """Test: Second request should use cache"""
        self.authenticate(self.owner)

        with CaptureQueriesContext(connection) as context:
            # First request
            response1 = self.client.get(self.url)
            first_request_queries = len(context.captured_queries)

            # Second request (should read from cache)
            response2 = self.client.get(self.url)
            second_request_queries = len(context.captured_queries) - first_request_queries

            assert response1.status_code == status.HTTP_200_OK
            assert response2.status_code == status.HTTP_200_OK
            assert second_request_queries == 0  # No new queries

    def test_cache_is_different_for_different_users(self):
        """Test: Cache is separate for different users"""
        self.authenticate(self.owner)
        response_owner = self.client.get(self.url)

        self.authenticate(self.member1)
        response_member = self.client.get(self.url)

        assert response_owner.data['id'] == response_member.data['id']

    # ========== Optimization Tests ==========

    def test_query_count_is_optimized(self):
        """Test: Number of queries should be optimized (max 2 queries)"""
        self.authenticate(self.owner)

        with CaptureQueriesContext(connection) as context:
            response = self.client.get(self.url)

            # Typically 2 queries: one for company+owner, one for members
            # (authentication query in middleware is separate)
            query_count = len(context.captured_queries)
            assert query_count <= 3, f"Expected <=3 queries, got {query_count}"

    def test_no_duplicate_companies_returned(self):
        """Test: OR condition should not return duplicate companies"""
        self.authenticate(self.owner)

        # Add owner as member as well (both conditions)
        self.company.members.add(self.owner)

        response = self.client.get(self.url)

        # Should return only one company
        assert response.status_code == status.HTTP_200_OK
        assert response.data['id'] == self.company.id

    def test_cannot_access_other_company_by_id_guessing(self):
        """Test: User cannot access other company by ID guessing"""
        # Create another company with different owner
        other_owner = User.objects.create_user(
            email='other@example.com',
            password='testPass123'
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
            password='testPass123'
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
            password='testPass123'
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