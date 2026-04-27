from celery import Celery

celery = Celery(__name__)


def init_celery(app):
    celery.conf.update(
        broker_url=app.config['REDIS_URL'],
        result_backend=app.config['REDIS_URL'],
        broker_connection_retry_on_startup=True,
    )
    return celery
