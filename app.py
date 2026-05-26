import os
from flask import Flask
from config import Config
from extensions import db, login_manager, oauth
import db_migrations

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # Initialize extensions
    db.init_app(app)
    login_manager.init_app(app)
    oauth.init_app(app)

    # Register Google OAuth Client if configured
    if app.config.get('GOOGLE_CLIENT_ID') and app.config.get('GOOGLE_CLIENT_SECRET'):
        oauth.register(
            name='google',
            client_id=app.config['GOOGLE_CLIENT_ID'],
            client_secret=app.config['GOOGLE_CLIENT_SECRET'],
            access_token_url='https://oauth2.googleapis.com/token',
            access_token_params=None,
            authorize_url='https://accounts.google.com/o/oauth2/v2/auth',
            authorize_params=None,
            api_base_url='https://www.googleapis.com/oauth2/v2/',
            client_kwargs={'scope': 'openid email profile'},
            server_metadata_url='https://accounts.google.com/.well-known/openid-configuration'
        )

    # Register modular Blueprints
    from auth.routes import auth_bp
    from main.routes import main_bp
    from student.routes import student_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(student_bp)

    # Run SQLite safe structural migrations on startup
    db_uri = app.config.get('SQLALCHEMY_DATABASE_URI', 'sqlite:///smartvision.db')
    if db_uri.startswith('sqlite:///'):
        db_path = db_uri.replace('sqlite:///', '')
        if not db_path.startswith('/'):
            db_path = os.path.join(app.instance_path, db_path)
        db_migrations.run_migrations(db_path)

    # Initialize Database & Initial Seed Data inside application context
    with app.app_context():
        db.create_all()
        setup_initial_data()

    return app

def setup_initial_data():
    from models import User, Teacher
    # Create default Admin if not exists
    if not User.query.filter_by(email='admin@smartvision.com').first():
        admin = User(name='Admin', email='admin@smartvision.com', role='admin')
        admin.set_password('password123')
        db.session.add(admin)
        print("[Database Seed] Default Admin user created: admin@smartvision.com / password123")
    
    # Create default Teachers if none exists
    if not Teacher.query.first():
        teacher1 = Teacher(name='Dr. Sharma')
        teacher2 = Teacher(name='Prof. Singh')
        db.session.add_all([teacher1, teacher2])
        print("[Database Seed] Default Teachers added.")
        
    db.session.commit()

# Create the application instance for Gunicorn production deployment (Gunicorn looks for 'app')
app = create_app()

if __name__ == '__main__':
    # Run the development server (threaded is True by default to prevent blocking on heavy deep-learning scans)
    app.run(host='127.0.0.1', port=9999, debug=True)