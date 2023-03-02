from django.db import models

class AvailablePlayer(models.Model):
    channel_name = models.TextField()