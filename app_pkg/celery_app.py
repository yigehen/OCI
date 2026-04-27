from app_pkg import create_app
from app_pkg.extensions import celery, init_celery

app = create_app()
init_celery(app)

# Ensure task modules are imported so task registration happens for workers.
from app_pkg.tasks import oci_tasks as _oci_tasks  # noqa: F401

__all__ = ['app', 'celery']
