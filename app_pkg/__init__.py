from datetime import timedelta
from flask import Flask
from celery.signals import worker_ready

from .config import Config
from .extensions import init_celery
from .core.runtime_paths import ensure_runtime_files


def create_app():
    ensure_runtime_files()
    app = Flask(__name__, template_folder='../templates', static_folder='../static')
    app.config.from_object(Config)
    app.secret_key = app.config['SECRET_KEY']
    app.permanent_session_lifetime = timedelta(hours=app.config['PERMANENT_SESSION_LIFETIME_HOURS'])
    init_celery(app)

    from .web.auth_routes import auth_bp, install_auth_hooks
    from .web.oci_routes import oci_bp
    from .api.oci_api_routes import api_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(oci_bp, url_prefix='/oci')
    app.register_blueprint(api_bp, url_prefix='/api/v1/oci')
    install_auth_hooks(app)

    @worker_ready.connect
    def _on_worker_ready(**kwargs):
        with app.app_context():
            from .tasks.oci_tasks import recover_snatching_tasks
            recover_snatching_tasks()

    return app
