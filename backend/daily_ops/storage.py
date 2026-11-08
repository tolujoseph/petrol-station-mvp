"""Private Cloudinary evidence; credentials never appear in saved file names or API output."""
import io
import re
import time
import uuid
from urllib.parse import urlparse, unquote, quote
from urllib.request import urlopen
from urllib.error import HTTPError

import cloudinary.api
import cloudinary.uploader
import cloudinary.utils
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.files.base import File
from django.core.files.storage import Storage, FileSystemStorage

class CloudinaryUploadError(OSError):
    def __init__(self, storage_name):
        super().__init__('Cloudinary upload failed. Please retry.')
        self.storage_name = storage_name



class CloudinaryEvidenceStorage(Storage):
    def __init__(self):
        parsed = urlparse(settings.CLOUDINARY_URL)
        if parsed.scheme != 'cloudinary' or not all((parsed.hostname, parsed.username, parsed.password)):
            raise ImproperlyConfigured('A valid CLOUDINARY_URL is required for evidence storage.')
        self.options = dict(cloud_name=parsed.hostname, api_key=unquote(parsed.username), api_secret=unquote(parsed.password), secure=True)
        self.legacy = FileSystemStorage()

    def _asset(self, name):
        if not re.fullmatch(r'cloudinary/petrol-station/[0-9a-f]{32}\.[a-z0-9]+', name):
            raise ValueError('Invalid application media identifier.')
        return name[len('cloudinary/'):].rsplit('.', 1)

    def _save(self, name, content):
        public_id = 'petrol-station/' + uuid.uuid4().hex
        try:
            result = cloudinary.uploader.upload(content, public_id=public_id, resource_type='image', type='authenticated', overwrite=False, backup=False, timeout=60, **self.options)
            extension = result['format']
            saved = 'cloudinary/' + public_id + '.' + extension
            self._asset(saved)
            return saved
        except Exception:
            # A timed-out upload can have reached Cloudinary; the caller records a retryable cleanup job.
            raise CloudinaryUploadError('cloudinary/' + public_id + '.jpg') from None

    def _open(self, name, mode='rb'):
        if not name.startswith('cloudinary/'):
            return self.legacy.open(name, mode)
        public_id, extension = self._asset(name)
        url = cloudinary.utils.private_download_url(public_id, extension, resource_type='image', type='authenticated', expires_at=int(time.time()) + 120, **self.options)
        try:
            with urlopen(url, timeout=60) as response:
                return File(io.BytesIO(response.read()), name=name)
        except HTTPError as exc:
            if exc.code == 404:
                raise FileNotFoundError('Photo no longer exists in Cloudinary.') from None
            raise OSError('Cloudinary could not deliver this photo.') from None
        except Exception:
            raise OSError('Cloudinary could not deliver this photo.') from None

    def delete(self, name):
        if not name:
            return
        if not name.startswith('cloudinary/'):
            self.legacy.delete(name)
            return
        public_id, _ = self._asset(name)
        try:
            result = cloudinary.uploader.destroy(public_id, resource_type='image', type='authenticated', invalidate=True, timeout=60, **self.options)
            if result.get('result') not in {'ok', 'not found'}:
                raise OSError('Cloudinary did not confirm deletion.')
            # Verify with the origin API, not a potentially cached delivery URL.
            if self.exists(name):
                raise OSError('Photo still exists in Cloudinary.')
        except Exception:
            raise OSError('Cloudinary deletion could not be verified. Retry removal.') from None

    def exists(self, name):
        if not name.startswith('cloudinary/'):
            return self.legacy.exists(name)
        public_id, _ = self._asset(name)
        try:
            cloudinary.api.resource(public_id, resource_type='image', type='authenticated', timeout=30, **self.options)
            return True
        except cloudinary.api.NotFound:
            return False

    def size(self, name):
        if not name.startswith('cloudinary/'):
            return self.legacy.size(name)
        public_id, _ = self._asset(name)
        return cloudinary.api.resource(public_id, resource_type='image', type='authenticated', timeout=30, **self.options)['bytes']

    def url(self, name):
        return '/api/media/file/?name=' + quote(name, safe='')
