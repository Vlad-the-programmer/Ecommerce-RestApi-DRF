import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse_lazy
from rest_framework.test import APIClient
from users.models import Profile, Gender

User = get_user_model()


@pytest.mark.django_db
def test_debug_registration_completely():
    client = APIClient()

    # Test with a KNOWN valid data
    test_data = {
        'email': 'test@example.com',
        'first_name': 'John',
        'last_name': 'Doe',
        'phone_number': '+48501122333',  # Known valid
        'date_of_birth': '2000-01-01',
        'password1': 'SecurePass123!',
        'password2': 'SecurePass123!',
        'gender': Gender.MALE,
        'country': 'US',
    }

    print("=" * 50)
    print("DEBUG REGISTRATION TEST")
    print("=" * 50)
    print("Test data:", test_data)

    response = client.post(reverse_lazy('userAuth:rest_register'), test_data, format='json')

    print("Response status:", response.status_code)
    print("Response data:", response.content)

    # Handle different response types
    if hasattr(response, 'data'):
        response_data = response.data
        print("Response data (from .data):", response_data)
    else:
        # Try to parse as JSON
        try:
            import json
            response_data = json.loads(response.content.decode('utf-8'))
            print("Response data (from JSON):", response_data)
        except:
            response_data = {}
            print("Response content:", response.content.decode('utf-8'))

    if response.status_code == 201:
        print("✅ SUCCESS! Registration worked")
        user = User.objects.get(email='test@example.com')
        print(f"User created: {user.email}")
        print(f"User active: {user.is_active}")
        print(f"User username: {user.username}")

        profile = Profile.objects.get(user=user)
        print(f"Profile created with phone: {profile.phone_number}")
    else:
        print("❌ FAILED! Registration errors:")
        for field, errors in response_data.items():
            print(f"  {field}: {errors}")

        # Check if any users were created anyway
        users = User.objects.all()
        print(f"Users in database: {list(users.values_list('email', flat=True))}")


@pytest.mark.django_db
def test_complete_registration_with_verification():
    client = APIClient()

    # Registration data
    test_data = {
        'email': 'test@example.com',
        'first_name': 'John',
        'last_name': 'Doe',
        'phone_number': '+48501122333',
        'date_of_birth': '2000-01-01',
        'password1': 'SecurePass123!',
        'password2': 'SecurePass123!',
        'gender': Gender.MALE,
        'country': 'US',
    }

    # Step 1: Register
    response = client.post(reverse_lazy('userAuth:rest_register'), test_data, format='json')
    assert response.status_code == 201

    # Step 2: Get the user (should be inactive)
    user = User.objects.get(email='test@example.com')
    assert user.is_active == False

    # Step 3: In testing, we can get the email confirmation directly
    from allauth.account.models import EmailAddress
    email_address = EmailAddress.objects.get(email=user.email)

    # Step 4: Manually verify the email (since we can't click the link in tests)
    email_address.verified = True
    email_address.save()

    # Step 5: Activate the user
    user.is_active = True
    user.save()

    # Step 6: Verify user is now active and can login
    login_data = {
        'email': 'test@example.com',
        'password': 'SecurePass123!'
    }
    login_response = client.post(reverse_lazy('userAuth:rest_login'), login_data, format='json')
    assert login_response.status_code == 200
    assert 'key' in login_response.data  # Should have auth token

    print("✅ Complete registration and verification flow successful!")

if __name__ == "__main__":
    test_debug_registration_completely()