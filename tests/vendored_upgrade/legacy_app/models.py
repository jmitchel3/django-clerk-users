from django.conf import settings
from django.db import models


class Note(models.Model):
    """Downstream row that references users by primary key."""

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    body = models.CharField(max_length=100)
