import logging
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase, APIClient
from django.contrib.auth import get_user_model

from PIL import Image
from io import BytesIO
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.authtoken.models import Token


User = get_user_model()

logger = logging.getLogger(__name__)


def create_test_image():
    """Helper function to create a test image"""
    image = Image.new('RGB', (100, 100), color='red')
    image_file = BytesIO()
    image.save(image_file, 'JPEG')
    image_file.seek(0)
    return SimpleUploadedFile(
        'test_image.jpg',
        image_file.getvalue(),
        content_type='image/jpeg'
    )


class UserViewSetTestCase(APITestCase):
    def setUp(self):
        # Create admin user
        self.admin = User.objects.create_superuser(
            email='admin@example.com',
            password='adminpass123',
            first_name='Admin',
            last_name='User'
        )

        # Create regular user
        self.user = User.objects.create_user(
            email='user@example.com',
            password='testpass123',
            first_name='Regular',
            last_name='User'
        )

        # Create another user for testing
        self.other_user = User.objects.create_user(
            email='other@example.com',
            password='otherpass123',
            first_name='Other',
            last_name='User'
        )

        # Get or create tokens
        self.admin_token, _ = Token.objects.get_or_create(user=self.admin)
        self.user_token, _ = Token.objects.get_or_create(user=self.user)

        logger.info(f"Admin token: {self.admin_token.key}")
        logger.info(f"User token: {self.user_token.key}")

        # API client setup
        self.client = APIClient()

        # URLs
        self.user_list_url = reverse('users:user-list')
        self.user_detail_url = lambda user_id: reverse('users:user-detail', args=[user_id])
        self.user_change_password_url = lambda user_id: reverse('users:user-change-password', args=[user_id])
        self.user_delete_profile_url = lambda user_id: reverse('users:user-delete-profile', args=[user_id])

    def test_list_users_unauthenticated(self):
        """Test that unauthenticated users can list users"""
        response = self.client.get(self.user_list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 3)  # 3 users in total

    def test_list_users_authenticated(self):
        """Test that authenticated users can list users"""
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.user_token.key}')
        response = self.client.get(self.user_list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 3)

    def test_search_users(self):
        """Test searching users by email, first_name, last_name"""
        self.client.credentials()
        response = self.client.get(f"{self.user_list_url}?search=Regular")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)
        self.assertEqual(response.data['results'][0]['email'], 'user@example.com')

    def test_retrieve_user_unauthenticated(self):
        """Test retrieving user details without authentication"""
        url = self.user_detail_url(self.user.id)
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('email', response.data)
        self.assertNotIn('password', response.data)

    def test_update_user_unauthenticated(self):
        """Test updating user without authentication should fail"""
        url = self.user_detail_url(self.user.id)
        data = {'first_name': 'Updated'}
        response = self.client.patch(url, data)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_update_own_profile(self):
        """Test user can update their own profile"""
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.user_token.key}')
        url = self.user_detail_url(self.user.id)
        data = {
            'first_name': 'Updated',
            'last_name': 'User',
            'country': 'US'
        }
        response = self.client.patch(url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, 'Updated')
        self.assertEqual(self.user.country, 'US')

    def test_update_other_user_profile(self):
        """Test user cannot update another user's profile"""
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.user_token.key}')
        url = self.user_detail_url(self.other_user.id)
        data = {'first_name': 'Hacked'}
        response = self.client.patch(url, data)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_can_update_any_user(self):
        """Test admin can update any user's profile"""
        
        # Set admin authentication
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.admin_token.key}')
        
        # Make the update request
        url = self.user_detail_url(self.user.id)
        data = {'first_name': 'AdminUpdated'}
        response = self.client.patch(url, data)
        
        # Verify the response and data
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, 'AdminUpdated')

    def test_upload_profile_picture(self):
        """Test uploading a profile picture"""
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.user_token.key}')
        url = self.user_detail_url(self.user.id)

        # Create a test image
        image = create_test_image()

        data = {
            'featured_image': image
        }
        response = self.client.patch(url, data, format='multipart')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('featured_image', response.data)
        self.assertTrue(response.data['featured_image'].endswith('.jpg'))

    def test_delete_profile_own_account(self):
        """Test user can delete their own account"""
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.user_token.key}')
        url = self.user_delete_profile_url(self.user.id)
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(User.objects.filter(id=self.user.id).exists())

    def test_cannot_delete_other_users_account(self):
        """Test user cannot delete another user's account"""
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.user_token.key}')
        url = self.user_delete_profile_url(self.other_user.id)
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_can_delete_any_account(self):
        """Test admin can delete any user account"""
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.admin_token.key}')
        url = self.user_delete_profile_url(self.user.id)
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(User.objects.filter(id=self.user.id).exists())

    def test_filter_users_by_country(self):
        """Test filtering users by country"""
        # Set country for test user
        self.user.country = 'US'
        self.user.save()

        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.user_token.key}')
        response = self.client.get(f"{self.user_list_url}?country=US")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)
        self.assertEqual(response.data['results'][0]['email'], 'user@example.com')

    def test_pagination(self):
        """Test that user list is paginated"""
        # Create additional users to test pagination
        for i in range(15):
            User.objects.create_user(
                email=f'user{i}@example.com',
                password=f'testpass{i}',
                first_name=f'User{i}',
                last_name='Test'
            )

        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.user_token.key}')
        response = self.client.get(self.user_list_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('count', response.data)
        self.assertIn('next', response.data)
        self.assertIn('previous', response.data)
        self.assertIn('results', response.data)
        self.assertEqual(len(response.data['results']), 10)  # Default page size

        