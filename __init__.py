import os
from flask import Flask
from smartvision_app.config import Config
from smartvision_app.extensions import db, login_manager


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Initialize extensions
    db.init_app(app)
    login_manager.init_app(app)

    # Create upload directories
    os.makedirs(app.config['UPLOAD_FACES_FOLDER'], exist_ok=True)
    os.makedirs(app.config['UPLOAD_GROUP_PHOTOS_FOLDER'], exist_ok=True)

    # Register blueprints
    from smartvision_app.auth.routes import auth_bp
    from smartvision_app.main.routes import main_bp

    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(main_bp)

    return app
