from celery import Celery

celery = Celery(__name__)


def init_celery(app):
    celery.conf.update(
        broker_url=app.config['broker_url'],
        result_backend=app.config['result_backend'],
        broker_connection_retry_on_startup=app.config.get('broker_connection_retry_on_startup', True)
    )
    return celery
