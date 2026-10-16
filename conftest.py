import os

from django.conf import settings


def pytest_configure():
    # pytest-xdist workers would otherwise share the file-based cache directory and clobber each other's keys.
    worker = os.environ.get("PYTEST_XDIST_WORKER")
    if worker:
        settings.CACHES["default"]["LOCATION"] = f"{settings.CACHES['default']['LOCATION']}_{worker}"
