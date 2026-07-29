from datetime import datetime, date
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from extensions import db, login_manager

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    email = db.Column(db.String(100), unique=True, nullable=False)
    mobile = db.Column(db.String(20), nullable=True)  # For OTP delivery
    password_hash = db.Column(db.String(255), nullable=True) # Nullable to support Google-only signups
    role = db.Column(db.String(20), default='user') # 'admin', 'teacher', or 'student'
    status = db.Column(db.String(20), default='Approved') # 'Pending', 'Approved', 'Rejected'
    google_id = db.Column(db.String(100), nullable=True) # For Gmail Login

    # Relationship to get the student record if role is student
    student_profile = db.relationship('Student', backref='user_account', uselist=False, lazy=True, foreign_keys='Student.user_id')
    # Relationship to get the teacher record if role is teacher
    teacher_profile = db.relationship('Teacher', backref='user_account', uselist=False, lazy=True, foreign_keys='Teacher.user_id')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password, method='pbkdf2:sha256')

    def check_password(self, password):
        if not self.password_hash:
            return False
        return check_password_hash(self.password_hash, password)

class Class(db.Model):
    __tablename__ = 'classes'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    admin_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True) # Multi-tenancy
    class_teacher_id = db.Column(db.Integer, db.ForeignKey('teachers.id'), nullable=True)

    students = db.relationship('Student', backref='class_assigned', lazy=True, cascade="all, delete-orphan")
    subjects = db.relationship('Subject', backref='class_assigned', lazy=True, cascade="all, delete-orphan")
    class_teacher = db.relationship('Teacher', backref='classes_directed', foreign_keys=[class_teacher_id])

class Teacher(db.Model):
    __tablename__ = 'teachers'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), nullable=True)
    emp_id = db.Column(db.String(50), nullable=True)
    mobile = db.Column(db.String(20), nullable=True)
    image_filename = db.Column(db.String(255), nullable=True)
    face_encoding = db.Column(db.LargeBinary, nullable=True)
    status = db.Column(db.String(20), default='Approved') # 'Pending', 'Approved', 'Rejected'
    admin_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True) # Multi-tenancy
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True, unique=True) # Associated User login account
    
    subjects = db.relationship('Subject', backref='teacher', lazy=True)

class Subject(db.Model):
    __tablename__ = 'subjects'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    teacher_id = db.Column(db.Integer, db.ForeignKey('teachers.id'), nullable=False)
    class_id = db.Column(db.Integer, db.ForeignKey('classes.id'), nullable=False)
    admin_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True) # Multi-tenancy

class Student(db.Model):
    __tablename__ = 'students'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    roll_no = db.Column(db.String(50), unique=True, nullable=False)
    enrollment_no = db.Column(db.String(50), unique=True, nullable=False)
    mobile = db.Column(db.String(20), nullable=True)
    class_id = db.Column(db.Integer, db.ForeignKey('classes.id'), nullable=True)  # Nullable: admin assigns class after registration
    face_encoding = db.Column(db.LargeBinary, nullable=True) # Nullable so student can sign up before photo upload
    image_filename = db.Column(db.String(255), nullable=True) # Nullable initially
    
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True, unique=True) # Associated User account
    attendance_records = db.relationship('Attendance', backref='student', lazy=True, cascade="all, delete-orphan")

class StudentEditRequest(db.Model):
    __tablename__ = 'student_edit_requests'
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id', ondelete='CASCADE'), nullable=False)
    new_name = db.Column(db.String(100), nullable=False)
    new_roll_no = db.Column(db.String(50), nullable=False)
    new_enrollment_no = db.Column(db.String(50), nullable=False)
    new_mobile = db.Column(db.String(20), nullable=True)
    new_class_id = db.Column(db.Integer, db.ForeignKey('classes.id', ondelete='CASCADE'), nullable=False)
    new_image_filename = db.Column(db.String(255), nullable=True)
    new_face_encoding = db.Column(db.LargeBinary, nullable=True)
    status = db.Column(db.String(20), default='Pending') # 'Pending', 'Approved', 'Rejected'
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationships
    student = db.relationship('Student', backref=db.backref('edit_requests', lazy=True, cascade='all, delete-orphan'))
    class_assigned = db.relationship('Class')

class Attendance(db.Model):
    __tablename__ = 'attendance'
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False)
    subject_id = db.Column(db.Integer, db.ForeignKey('subjects.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    status = db.Column(db.String(10), nullable=False) # 'Present' or 'Absent'
    time_marked = db.Column(db.String(20), nullable=True) # e.g. "09:56 AM"

    subject = db.relationship('Subject', backref='attendance_records', lazy=True)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))