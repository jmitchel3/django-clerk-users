"""
View decorators for django-clerk-users.
"""

from __future__ import annotations

import functools
from typing import TYPE_CHECKING, Callable

from django.http import JsonResponse

if TYPE_CHECKING:
    from django.http import HttpRequest, HttpResponse


def clerk_user_required(view_func: Callable) -> Callable:
    """
    Decorator that requires a Clerk-authenticated user.

    Use this decorator on views that require authentication.
    Returns a 401 response if the user is not authenticated.

    Example:
        from django_clerk_users.decorators import clerk_user_required

        @clerk_user_required
        def my_protected_view(request):
            user = request.clerk_user
            return JsonResponse({"email": user.email})

    Args:
        view_func: The view function to wrap.

    Returns:
        The wrapped view function.
    """

    @functools.wraps(view_func)
    def wrapper(request: "HttpRequest", *args, **kwargs) -> "HttpResponse":
        clerk_user = getattr(request, "clerk_user", None)

        if not clerk_user or not clerk_user.is_authenticated:
            return JsonResponse(
                {"error": "Authentication required"},
                status=401,
            )

        return view_func(request, *args, **kwargs)

    return wrapper


def clerk_org_required(view_func: Callable) -> Callable:
    """
    Decorator that requires an organization context.

    Use this decorator on views that require both authentication
    and an organization context. Returns a 401 response if not
    authenticated, or a 403 response if no organization is set.

    Example:
        from django_clerk_users.decorators import clerk_org_required

        @clerk_org_required
        def my_org_view(request):
            org_id = request.org
            return JsonResponse({"org_id": org_id})

    Args:
        view_func: The view function to wrap.

    Returns:
        The wrapped view function.
    """

    @functools.wraps(view_func)
    def wrapper(request: "HttpRequest", *args, **kwargs) -> "HttpResponse":
        clerk_user = getattr(request, "clerk_user", None)

        if not clerk_user or not clerk_user.is_authenticated:
            return JsonResponse(
                {"error": "Authentication required"},
                status=401,
            )

        org = getattr(request, "org", None)
        if not org:
            return JsonResponse(
                {"error": "Organization context required"},
                status=403,
            )

        return view_func(request, *args, **kwargs)

    return wrapper


def clerk_staff_required(view_func: Callable) -> Callable:
    """
    Decorator that requires a staff user.

    Use this decorator on views that require staff access.
    Returns a 401 response if not authenticated, or a 403 response
    if the user is not staff.

    Example:
        from django_clerk_users.decorators import clerk_staff_required

        @clerk_staff_required
        def admin_view(request):
            return JsonResponse({"message": "Staff access granted"})

    Args:
        view_func: The view function to wrap.

    Returns:
        The wrapped view function.
    """

    @functools.wraps(view_func)
    def wrapper(request: "HttpRequest", *args, **kwargs) -> "HttpResponse":
        clerk_user = getattr(request, "clerk_user", None)

        if not clerk_user or not clerk_user.is_authenticated:
            return JsonResponse(
                {"error": "Authentication required"},
                status=401,
            )

        if not clerk_user.is_staff:
            return JsonResponse(
                {"error": "Staff access required"},
                status=403,
            )

        return view_func(request, *args, **kwargs)

    return wrapper


def clerk_superuser_required(view_func: Callable) -> Callable:
    """
    Decorator that requires a superuser.

    Use this decorator on views that require superuser access.
    Returns a 401 response if not authenticated, or a 403 response
    if the user is not a superuser.

    Example:
        from django_clerk_users.decorators import clerk_superuser_required

        @clerk_superuser_required
        def superuser_view(request):
            return JsonResponse({"message": "Superuser access granted"})

    Args:
        view_func: The view function to wrap.

    Returns:
        The wrapped view function.
    """

    @functools.wraps(view_func)
    def wrapper(request: "HttpRequest", *args, **kwargs) -> "HttpResponse":
        clerk_user = getattr(request, "clerk_user", None)

        if not clerk_user or not clerk_user.is_authenticated:
            return JsonResponse(
                {"error": "Authentication required"},
                status=401,
            )

        if not clerk_user.is_superuser:
            return JsonResponse(
                {"error": "Superuser access required"},
                status=403,
            )

        return view_func(request, *args, **kwargs)

    return wrapper
