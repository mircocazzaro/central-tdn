from django.db import models


class Endpoint(models.Model):
    name = models.CharField(max_length=100)
    url  = models.URLField()
    logo = models.ImageField(
        upload_to='endpoint_logos/', 
        blank=True, 
        null=True
    )
    # Ed25519 public key (base64) of an endpoint that joined through the
    # enrollment protocol. Endpoints added by hand have none and receive no
    # catalog or ontology updates.
    public_key = models.CharField(max_length=64, blank=True, default='')
    catalog_version = models.PositiveIntegerField(null=True, blank=True)
    ontology_version = models.PositiveIntegerField(null=True, blank=True)

    @property
    def logo_url(self):
        """URL of the logo, or '' when none was uploaded (logo is optional)."""
        return self.logo.url if self.logo else ''

    @property
    def fingerprint(self):
        from .hdnsig import fingerprint
        return fingerprint(self.public_key) if self.public_key else ''


class EnrollmentRequest(models.Model):
    """Application of an endpoint to join this Central, awaiting the manager."""
    PENDING = 'pending'
    REJECTED = 'rejected'
    STATUS_CHOICES = [(PENDING, 'Pending'), (REJECTED, 'Rejected')]

    name = models.CharField(max_length=100)
    url = models.URLField()
    public_key = models.CharField(max_length=64, unique=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=PENDING)
    remote_addr = models.GenericIPAddressField(null=True, blank=True)
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created']

    @property
    def fingerprint(self):
        from .hdnsig import fingerprint
        return fingerprint(self.public_key)


class SeenNonce(models.Model):
    """Nonces of accepted signed requests (replay protection)."""
    sender = models.CharField(max_length=64)
    nonce = models.CharField(max_length=64)
    seen = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['sender', 'nonce'], name='unique_sender_nonce')]


class CatalogRelease(models.Model):
    """A published version of the query catalog, as sent to the endpoints."""
    version = models.PositiveIntegerField(unique=True)
    document = models.JSONField()
    digest = models.CharField(max_length=64)  # content hash, version excluded
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-version']


class OntologyRelease(models.Model):
    """A published version of the ontology (Turtle) with the mapping template
    written for it (.obda), as sent to the endpoints. Always both."""
    version = models.PositiveIntegerField(unique=True)
    filename = models.CharField(max_length=200)
    ttl = models.TextField()
    sha256 = models.CharField(max_length=64)
    template_filename = models.CharField(max_length=200, default='')
    mapping_template = models.TextField(default='')
    template_sha256 = models.CharField(max_length=64, default='')
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-version']
