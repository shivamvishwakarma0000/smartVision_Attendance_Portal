from datetime import datetime, timedelta, timezone
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from authlib.integrations.flask_client import OAuth

db = SQLAlchemy()
login_manager = LoginManager()
oauth = OAuth()

login_manager.login_view = 'auth.login'
login_manager.login_message_category = 'info'

# Indian Standard Time (IST - UTC + 5:30) helper for accurate local timestamps across all environments
IST = timezone(timedelta(hours=5, minutes=30))

def get_current_date():
    return datetime.now(IST).date()

def get_current_time_str():
    return datetime.now(IST).strftime('%I:%M %p')

def get_current_datetime_str():
    return datetime.now(IST).strftime('%Y%m%d%H%M%S')