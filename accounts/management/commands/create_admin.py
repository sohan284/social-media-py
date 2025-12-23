from django.core.management.base import BaseCommand
from accounts.models import User


class Command(BaseCommand):
    help = 'Creates an admin user with username "user" and password "1234"'

    def handle(self, *args, **options):
        username = 'user'
        password = '1234'
        email = 'admin@example.com'  # You can change this if needed

        # Check if user already exists
        if User.objects.filter(username=username).exists():
            self.stdout.write(
                self.style.WARNING(f'User with username "{username}" already exists.')
            )
            user = User.objects.get(username=username)
            # Update user to be admin
            user.role = 'admin'
            user.email_verified = True  # Set email as verified for admin
            user.set_password(password)
            user.save()
            self.stdout.write(
                self.style.SUCCESS(f'Successfully updated user "{username}" to admin role.')
            )
        else:
            # Create new admin user
            user = User.objects.create_user(
                username=username,
                email=email,
                password=password,
                role='admin',
                email_verified=True  # Set email as verified for admin
            )
            self.stdout.write(
                self.style.SUCCESS(f'Successfully created admin user "{username}"')
            )

