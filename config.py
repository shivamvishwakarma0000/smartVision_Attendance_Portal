# config.py

class Config:
    """
    Configuration settings for the Flask application.
    Using SQLite to avoid setup and password issues.
    """
    SECRET_KEY = 'a-very-secret-key-that-you-should-change'

    # This line sets up the simple SQLite database file named 'smartvision.db'
    SQLALCHEMY_DATABASE_URI = 'sqlite:///smartvision.db'

    SQLALCHEMY_TRACK_MODIFICATIONS = False