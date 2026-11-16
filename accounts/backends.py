from django.contrib.auth.backends import ModelBackend
from django.contrib.auth import get_user_model
from django.db.models import Q

UserModel = get_user_model()


class EmailOrUsernameModelBackend(ModelBackend):
    """
    Authenticate against either username or email (case-insensitive).
    """

    def authenticate(self, request, username=None, password=None, **kwargs):
        if username is None:
            username = kwargs.get(UserModel.USERNAME_FIELD)
        if not username or password is None:
            return None

        identifier = username.strip()
        try:
            user = UserModel._default_manager.filter(
                Q(username__iexact=identifier) | Q(email__iexact=identifier)
            ).first()
        except UserModel.DoesNotExist:
            user = None

        if user is None:
            # Run the default password hasher once to mitigate timing attacks
            UserModel().set_password(password)
            return None

        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
