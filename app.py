import os
from flask import Flask
from config import Config
from extensions import db, login_manager, oauth
import face_recognition
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
    from teacher.routes import teacher_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(student_bp)
    app.register_blueprint(teacher_bp)

    # Run SQLite safe structural migrations on startup
    db_uri = app.config.get('SQLALCHEMY_DATABASE_URI', 'sqlite:///smartvision.db')
    if db_uri.startswith('sqlite:///'):
        db_path = db_uri.replace('sqlite:///', '')
        if not db_path.startswith('/'):
            db_path = os.path.join(app.instance_path, db_path)
        # Ensure database directory exists (vital for persistent volume paths on Render)
        db_dir = os.path.dirname(db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)
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
    
    # Create default Teachers and their User accounts if none exists
    if not Teacher.query.first():
        user1 = User(name='Dr. Sharma', email='sharma@smartvision.com', role='teacher')
        user1.set_password('password123')
        user2 = User(name='Prof. Singh', email='singh@smartvision.com', role='teacher')
        user2.set_password('password123')
        
        db.session.add_all([user1, user2])
        db.session.flush()

        teacher1 = Teacher(name='Dr. Sharma', email='sharma@smartvision.com', user_id=user1.id)
        teacher2 = Teacher(name='Prof. Singh', email='singh@smartvision.com', user_id=user2.id)
        db.session.add_all([teacher1, teacher2])
        print("[Database Seed] Default Teachers created with accounts: sharma@smartvision.com & singh@smartvision.com / password123")
        
    db.session.commit()

# Create the application instance for Gunicorn production deployment (Gunicorn looks for 'app')
app = create_app()

if __name__ == '__main__':
    import os
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", 7860))
    # Run server (threaded is True by default to prevent blocking on heavy deep-learning scans)
    app.run(host=host, port=port, debug=True)