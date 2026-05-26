import os

class Config:
    """
    Configuration settings for the Flask application.
    Using SQLite to avoid setup and password issues.
    """
    SECRET_KEY = os.environ.get('SECRET_KEY', 'a-very-secret-key-that-you-should-change')

    # Point to the local SQLite database file in the project directory
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL', 'sqlite:///smartvision.db')

    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Google OAuth settings
    GOOGLE_CLIENT_ID = os.environ.get('GOOGLE_CLIENT_ID', '')
    GOOGLE_CLIENT_SECRET = os.environ.get('GOOGLE_CLIENT_SECRET', '')