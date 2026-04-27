from unittest import mock

from django.urls import reverse
from django.utils.text import slugify

from rest_framework.test import APITestCase
from rest_framework import status

from .models import Board
from taskflow.accounts.models import CustomUser

# Create your tests here.


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
