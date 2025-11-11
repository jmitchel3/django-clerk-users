from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("django-clerk-users")
except PackageNotFoundError:
    # Package is not installed
    __version__ = "unknown"


def __getattr__(name):
    """Lazy import to avoid loading Django models before apps are ready."""
    if name == "hello_world":
        from django_clerk_users.main import hello_world

        return hello_world
    raise AttributeError(f"Module 'django_clerk' has no attribute '{name}'")


__all__ = [
    "__version__",
    "hello_world",
]
