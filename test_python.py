import os
from app import app, setup_initial_data
try:
    with app.app_context():
        setup_initial_data()
    print("setup_initial_data succeeded")
except Exception as e:
    print(f"Error: {e}")
