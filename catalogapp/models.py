from django.db import models

class Endpoint(models.Model):
    name = models.CharField(max_length=100)
    url  = models.URLField()
    logo = models.ImageField(
        upload_to='endpoint_logos/', 
        blank=True, 
        null=True
    )