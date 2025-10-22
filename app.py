import os
import face_recognition
import numpy as np
from datetime import date
from werkzeug.utils import secure_filename
from flask import Flask, render_template, redirect, url_for, request, flash, send_from_directory, jsonify
from config import Config
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from collections import defaultdict

# --- App and Database Initialization ---
app = Flask(__name__)
app.config.from_object(Config)

UPLOAD_FOLDER = 'uploads'
FACES_FOLDER = os.path.join(UPLOAD_FOLDER, 'faces')
GROUP_PHOTOS_FOLDER = os.path.join(UPLOAD_FOLDER, 'group_photos')
os.makedirs(FACES_FOLDER, exist_ok=True)
os.makedirs(GROUP_PHOTOS_FOLDER, exist_ok=True)

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'


# --- Database Models ---

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    email = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), default='user')

    def set_password(self, password): self.password_hash = generate_password_hash(password)

    def check_password(self, password): return check_password_hash(self.password_hash, password)


class Class(db.Model):
    __tablename__ = 'classes'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    students = db.relationship('Student', backref='class_assigned', lazy=True, cascade="all, delete-orphan")
    subjects = db.relationship('Subject', backref='class_assigned', lazy=True, cascade="all, delete-orphan")


class Teacher(db.Model):
    __tablename__ = 'teachers'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    subjects = db.relationship('Subject', backref='teacher', lazy=True)


class Subject(db.Model):
    __tablename__ = 'subjects'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    teacher_id = db.Column(db.Integer, db.ForeignKey('teachers.id'), nullable=False)
    class_id = db.Column(db.Integer, db.ForeignKey('classes.id'), nullable=False)


class Student(db.Model):
    __tablename__ = 'students'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    roll_no = db.Column(db.String(50), unique=True, nullable=False)
    enrollment_no = db.Column(db.String(50), unique=True, nullable=False)
    class_id = db.Column(db.Integer, db.ForeignKey('classes.id'), nullable=False)
    face_encoding = db.Column(db.LargeBinary, nullable=False)
    image_filename = db.Column(db.String(255), nullable=False)
    attendance_records = db.relationship('Attendance', backref='student', lazy=True, cascade="all, delete-orphan")


class Attendance(db.Model):
    __tablename__ = 'attendance'
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False)
    subject_id = db.Column(db.Integer, db.ForeignKey('subjects.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    status = db.Column(db.String(10), nullable=False)
    subject = db.relationship('Subject', backref='attendance_records', lazy=True)


# --- User Loader ---
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


# --- Routes ---

@app.route('/')
@login_required
def dashboard():
    total_students = Student.query.count()
    subjects = Subject.query.all()
    all_students_list = Student.query.all()

    subject_names = [subject.name for subject in subjects]
    attendance_percentages = []
    today = date.today()

    for subject in subjects:
        if total_students > 0:
            present_count = db.session.query(Attendance.student_id).filter_by(
                subject_id=subject.id, date=today, status='Present'
            ).distinct().count()
            percentage = (present_count / total_students) * 100
            attendance_percentages.append(round(percentage, 2))
        else:
            attendance_percentages.append(0)

    return render_template(
        'dashboard.html',
        student_count=total_students,
        subjects_managed=len(subjects),
        students=all_students_list,
        subject_names=subject_names,
        attendance_percentages=attendance_percentages
    )


@app.route('/manage_classes', methods=['GET', 'POST'])
@login_required
def manage_classes():
    if request.method == 'POST':
        class_name = request.form.get('class_name')
        if class_name and not Class.query.filter_by(name=class_name).first():
            new_class = Class(name=class_name)
            db.session.add(new_class)
            db.session.commit()
            flash(f"Class '{class_name}' added successfully!", 'success')
        else:
            flash('Class name cannot be empty or already exists.', 'warning')
        return redirect(url_for('manage_classes'))

    classes = Class.query.all()
    return render_template('manage_classes.html', classes=classes)


@app.route('/delete_class/<int:class_id>', methods=['POST'])
@login_required
def delete_class(class_id):
    class_to_delete = Class.query.get_or_404(class_id)
    try:
        db.session.delete(class_to_delete)
        db.session.commit()
        flash(f"Class '{class_to_delete.name}' and all its data have been deleted.", 'success')
    except Exception as e:
        db.session.rollback()
        flash(f"Error deleting class: {e}", 'danger')
    return redirect(url_for('manage_classes'))


@app.route('/add_teacher', methods=['POST'])
@login_required
def add_teacher():
    if request.method == 'POST':
        teacher_name = request.form.get('teacher_name')
        if teacher_name and not Teacher.query.filter_by(name=teacher_name).first():
            new_teacher = Teacher(name=teacher_name)
            db.session.add(new_teacher)
            db.session.commit()
            flash(f"Teacher '{teacher_name}' added successfully!", 'success')
        else:
            flash('Teacher name cannot be empty or already exists.', 'warning')
    return redirect(url_for('manage_subjects'))


@app.route('/manage_subjects', methods=['GET', 'POST'])
@login_required
def manage_subjects():
    if request.method == 'POST':
        subject_name = request.form.get('subject_name')
        teacher_id = request.form.get('teacher_id')
        class_id = request.form.get('class_id')

        if not all([subject_name, teacher_id, class_id]):
            flash('All fields are required.', 'warning')
            return redirect(url_for('manage_subjects'))

        if Subject.query.filter_by(name=subject_name, class_id=class_id).first():
            flash('This subject already exists for this class.', 'warning')
        else:
            new_subject = Subject(name=subject_name, teacher_id=teacher_id, class_id=class_id)
            db.session.add(new_subject)
            db.session.commit()
            flash('New subject added successfully!', 'success')
        return redirect(url_for('manage_subjects'))

    teachers = Teacher.query.all()
    subjects = Subject.query.all()
    classes = Class.query.all()
    return render_template('manage_subjects.html', teachers=teachers, subjects=subjects, classes=classes)


@app.route('/delete_teacher/<int:teacher_id>', methods=['POST'])
@login_required
def delete_teacher(teacher_id):
    teacher_to_delete = Teacher.query.get_or_404(teacher_id)
    if teacher_to_delete.subjects:
        flash(f"Cannot delete '{teacher_to_delete.name}'. They are still assigned to one or more subjects.", 'danger')
    else:
        db.session.delete(teacher_to_delete)
        db.session.commit()
        flash(f"Teacher '{teacher_to_delete.name}' deleted successfully.", 'success')
    return redirect(url_for('manage_subjects'))


@app.route('/delete_subject/<int:subject_id>', methods=['POST'])
@login_required
def delete_subject(subject_id):
    subject_to_delete = Subject.query.get_or_404(subject_id)
    try:
        Attendance.query.filter_by(subject_id=subject_id).delete()
        db.session.delete(subject_to_delete)
        db.session.commit()
        flash(f"Subject '{subject_to_delete.name}' deleted successfully.", 'success')
    except Exception as e:
        db.session.rollback()
        flash(f"Error deleting subject: {e}", 'danger')
    return redirect(url_for('manage_subjects'))


@app.route('/register_student', methods=['GET', 'POST'])
@login_required
def register_student():
    if request.method == 'POST':
        name = request.form.get('name')
        roll_no = request.form.get('roll_no')
        enrollment_no = request.form.get('enrollment_no')
        class_id = request.form.get('class_id')
        student_photo = request.files.get('student_photo')

        if not class_id:
            flash('You must select a class.', 'danger')
            return redirect(request.url)
        if not student_photo:
            flash('No photo was uploaded.', 'danger')
            return redirect(request.url)
        if Student.query.filter_by(roll_no=roll_no).first() or Student.query.filter_by(
                enrollment_no=enrollment_no).first():
            flash('A student with this roll or enrollment number already exists.', 'danger')
            return redirect(request.url)

        filename = secure_filename(f"{roll_no}_{name}_{student_photo.filename}")
        filepath = os.path.join(FACES_FOLDER, filename)
        student_photo.save(filepath)
        try:
            image = face_recognition.load_image_file(filepath)
            encodings = face_recognition.face_encodings(image)
            if len(encodings) == 1:
                face_encoding_bytes = encodings[0].tobytes()
                new_student = Student(name=name, roll_no=roll_no, enrollment_no=enrollment_no, class_id=class_id,
                                      face_encoding=face_encoding_bytes, image_filename=filename)
                db.session.add(new_student)
                db.session.commit()
                flash('Student registered successfully!', 'success')
                return redirect(url_for('dashboard'))
            else:
                flash(f'{len(encodings)} faces found. Please use a photo of only one student.', 'danger')
        except Exception as e:
            flash(f'An error occurred: {e}', 'danger')
        os.remove(filepath)
        return redirect(request.url)

    classes = Class.query.all()
    return render_template('register_student.html', classes=classes)


@app.route('/take_attendance', methods=['GET', 'POST'])
@login_required
def take_attendance():
    today = date.today()

    if request.method == 'POST':
        class_id = request.form.get('class_id')
        subject_id = request.form.get('subject_id')
        group_photos = request.files.getlist('group_photo')

        if not all([class_id, subject_id]):
            flash('Please select both a class and a subject.', 'warning')
            return redirect(url_for('take_attendance'))

        known_students = Student.query.filter_by(class_id=class_id).all()
        subject = Subject.query.get(subject_id)
        if not known_students:
            flash('No students are registered in this class.', 'danger')
            return redirect(url_for('take_attendance'))

        known_face_encodings = [np.frombuffer(s.face_encoding, dtype=np.float64) for s in known_students]
        known_student_data = {s.id: s for s in known_students}
        present_student_ids = set()
        total_faces_found = 0

        for group_photo in group_photos:
            if group_photo.filename:
                filename = secure_filename(group_photo.filename)
                filepath = os.path.join(GROUP_PHOTOS_FOLDER, filename)
                group_photo.save(filepath)
                unknown_image = face_recognition.load_image_file(filepath)
                unknown_face_encodings = face_recognition.face_encodings(unknown_image)
                total_faces_found += len(unknown_face_encodings)
                for face_encoding in unknown_face_encodings:
                    matches = face_recognition.compare_faces(known_face_encodings, face_encoding, tolerance=0.6)
                    if True in matches:
                        first_match_index = matches.index(True)
                        student_id = known_students[first_match_index].id
                        present_student_ids.add(student_id)
                os.remove(filepath)

        for student_id in present_student_ids:
            if not Attendance.query.filter_by(student_id=student_id, date=today, subject_id=subject_id).first():
                new_attendance = Attendance(student_id=student_id, date=today, status='Present', subject_id=subject_id)
                db.session.add(new_attendance)
        db.session.commit()

    classes = Class.query.all()
    subjects = Subject.query.all()
    todays_records = Attendance.query.filter_by(date=today).all()
    attendance_log = defaultdict(list)
    for record in todays_records:
        attendance_log[record.subject.name].append(record)

    return render_template('take_attendance.html', classes=classes, subjects=subjects,
                           attendance_log=dict(attendance_log), today=today.strftime('%Y-%m-%d'))


@app.route('/delete_attendance/<int:attendance_id>', methods=['POST'])
@login_required
def delete_attendance(attendance_id):
    record_to_delete = Attendance.query.get_or_404(attendance_id)
    db.session.delete(record_to_delete)
    db.session.commit()
    flash('Attendance record deleted.', 'success')
    return redirect(url_for('take_attendance'))


@app.route('/delete_todays_attendance', methods=['POST'])
@login_required
def delete_todays_attendance():
    today = date.today()
    try:
        Attendance.query.filter_by(date=today).delete()
        db.session.commit()
        flash("All of today's attendance records have been deleted.", 'success')
    except Exception as e:
        db.session.rollback()
        flash(f"An error occurred: {e}", 'danger')
    return redirect(url_for('take_attendance'))


@app.route('/reports')
@login_required
def view_reports():
    students = Student.query.all()
    return render_template('view_reports.html', students=students)


@app.route('/delete_student/<int:student_id>', methods=['POST'])
@login_required
def delete_student(student_id):
    student_to_delete = Student.query.get_or_404(student_id)
    try:
        image_filepath = os.path.join(FACES_FOLDER, student_to_delete.image_filename)
        if os.path.exists(image_filepath): os.remove(image_filepath)
        db.session.delete(student_to_delete)
        db.session.commit()
        flash('Student deleted successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting student: {e}', 'danger')
    return redirect(url_for('view_reports'))


@app.route('/uploads/faces/<filename>')
def uploaded_face(filename):
    return send_from_directory(FACES_FOLDER, filename)


@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated: return redirect(url_for('dashboard'))
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        user = User.query.filter_by(email=email).first()
        if user and user.check_password(password):
            login_user(user)
            next_page = request.args.get('next')
            return redirect(next_page or url_for('dashboard'))
        else:
            flash('Invalid email or password.', 'danger')
    return render_template('login.html')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))


@app.route('/get_subjects/<int:class_id>')
@login_required
def get_subjects(class_id):
    subjects = Subject.query.filter_by(class_id=class_id).all()
    subject_list = [{'id': subject.id, 'name': subject.name} for subject in subjects]
    return jsonify({'subjects': subject_list})


def setup_initial_data():
    with app.app_context():
        db.create_all()
        if not User.query.filter_by(email='admin@smartvision.com').first():
            admin = User(name='Admin', email='admin@smartvision.com', role='admin')
            admin.set_password('password123')
            db.session.add(admin)
        if not Teacher.query.first():
            teacher1 = Teacher(name='Dr. Sharma')
            teacher2 = Teacher(name='Prof. Singh')
            db.session.add_all([teacher1, teacher2])
        db.session.commit()

2
if __name__ == '__main__':
    setup_initial_data()
    app.run(debug=True)