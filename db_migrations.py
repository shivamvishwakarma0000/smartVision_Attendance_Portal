import sqlite3
import os

def run_migrations(db_path="smartvision.db"):
    """
    Safely runs SQLite migrations to add new columns and tables required
    for Google OAuth, multi-tenancy, and approvals queues without data loss.
    """
    if not os.path.exists(db_path):
        print(f"[Migration] Database file {db_path} does not exist yet. It will be created by SQLAlchemy.")
        return

    print(f"[Migration] Inspecting database {db_path} for updates...")
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Columns to add: (table_name, column_name, sql_definition)
        migrations = [
            ("users", "google_id", "VARCHAR(100)"),
            ("users", "mobile", "VARCHAR(20)"),          # NEW: for OTP delivery
            ("users", "status", "VARCHAR(20) DEFAULT 'Approved'"),
            ("classes", "admin_id", "INTEGER"),
            ("classes", "class_teacher_id", "INTEGER"),
            ("teachers", "admin_id", "INTEGER"),
            ("teachers", "user_id", "INTEGER"),
            ("teachers", "email", "VARCHAR(100)"),
            ("teachers", "emp_id", "VARCHAR(50)"),
            ("teachers", "mobile", "VARCHAR(20)"),
            ("teachers", "image_filename", "VARCHAR(255)"),
            ("teachers", "face_encoding", "BLOB"),
            ("teachers", "status", "VARCHAR(20) DEFAULT 'Approved'"),
            ("subjects", "admin_id", "INTEGER"),
            ("students", "user_id", "INTEGER"),
            ("students", "mobile", "VARCHAR(20)"),
            ("student_edit_requests", "new_mobile", "VARCHAR(20)"),
            ("attendance", "time_marked", "VARCHAR(20)")
        ]

        for table, column, col_type in migrations:
            # Check if column exists
            cursor.execute(f"PRAGMA table_info({table})")
            columns = [info[1] for info in cursor.fetchall()]
            
            if column not in columns:
                print(f"[Migration] Adding column '{column}' to table '{table}'...")
                cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")
                conn.commit()
                print(f"[Migration] Column '{column}' added successfully.")

        # Check if table 'student_edit_requests' exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='student_edit_requests';")
        if not cursor.fetchone():
            print("[Migration] Creating table 'student_edit_requests'...")
            cursor.execute("""
                CREATE TABLE student_edit_requests (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    student_id INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
                    new_name VARCHAR(100) NOT NULL,
                    new_roll_no VARCHAR(50) NOT NULL,
                    new_enrollment_no VARCHAR(50) NOT NULL,
                    new_class_id INTEGER NOT NULL REFERENCES classes(id) ON DELETE CASCADE,
                    new_image_filename VARCHAR(255),
                    new_face_encoding BLOB,
                    status VARCHAR(20) DEFAULT 'Pending',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            conn.commit()
            print("[Migration] Table 'student_edit_requests' created successfully.")

        conn.close()
        print("[Migration] Database is fully up-to-date.")
    except Exception as e:
        print(f"[Migration ERROR] Failed to run database migrations: {e}")

if __name__ == '__main__':
    run_migrations()
