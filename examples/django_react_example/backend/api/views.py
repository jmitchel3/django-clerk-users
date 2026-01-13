"""
Example API views demonstrating django-clerk-users authentication.
"""

from django.http import JsonResponse

from django_clerk_users.decorators import clerk_user_required


def public_view(request):
    """
    A public endpoint that doesn't require authentication.
    Shows the current auth status.
    """
    user = getattr(request, "clerk_user", None)

    if user and user.is_authenticated:
        return JsonResponse({
            "message": "Hello! You are authenticated.",
            "authenticated": True,
            "user_id": str(user.clerk_id),
        })

    return JsonResponse({
        "message": "Hello! You are not authenticated.",
        "authenticated": False,
    })


@clerk_user_required
def protected_view(request):
    """
    A protected endpoint that requires Clerk authentication.
    Returns 401 if not authenticated.
    """
    user = request.clerk_user

    return JsonResponse({
        "message": "You have accessed a protected resource!",
        "user": {
            "clerk_id": user.clerk_id,
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name,
        },
    })


@clerk_user_required
def user_profile_view(request):
    """
    Returns the full user profile for the authenticated user.
    """
    user = request.clerk_user

    return JsonResponse({
        "profile": {
            "clerk_id": user.clerk_id,
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "is_active": user.is_active,
            "is_staff": user.is_staff,
            "created_at": user.created_at.isoformat() if user.created_at else None,
            "last_login": user.last_login.isoformat() if user.last_login else None,
        },
        "org_id": getattr(request, "org", None),
    })
