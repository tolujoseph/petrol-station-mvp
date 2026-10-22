
from rest_framework.permissions import BasePermission

from ..models import User


class IsManager(BasePermission):
    message = "You must be a Manager assigned to a station."

    def has_permission(self, request, view):
        user = request.user

        return (
            user.is_authenticated
            and user.role == User.Role.MANAGER
            and user.station_id is not None
        )


class IsOwner(BasePermission):
    message = "You must be an Owner assigned to a station."

    def has_permission(self, request, view):
        user = request.user

        return (
            user.is_authenticated
            and user.role == User.Role.OWNER
            and user.station_id is not None
        )
