import os
import face_recognition
import numpy as np
from datetime import date, datetime
from flask import render_template, redirect, url_for, flash, request, send_from_directory, jsonify, Blueprint
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from collections import defaultdict
from functools import wraps

from extensions import db
from models import User, Class, Teacher, Subject, Student, Attendance, StudentEditRequest
from auth.routes import save_base64_image

main_bp = Blueprint('main', __name__)

UPLOAD_FOLDER = 'temp_uploads'
FACES_FOLDER = os.path.join(UPLOAD_FOLDER, 'faces')
GROUP_PHOTOS_FOLDER = os.path.join(UPLOAD_FOLDER, 'group_photos')

os.makedirs(FACES_FOLDER, exist_ok=True)
os.makedirs(GROUP_PHOTOS_FOLDER, exist_ok=True)

# Decorator to ensure only logged in admins can access
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'admin':
            flash("Admin access is required to view this page.", "danger")
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function

# Helper queries to filter by admin multi-tenancy (allowing pre-populated global items where admin_id is null)
def get_admin_classes():
    return Class.query.filter((Class.admin_id == None) | (Class.admin_id == current_user.id)).all()

def get_admin_teachers():
    return Teacher.query.filter((Teacher.admin_id == None) | (Teacher.admin_id == current_user.id)).all()

def get_admin_subjects():
    return Subject.query.filter((Subject.admin_id == None) | (Subject.admin_id == current_user.id)).all()

def get_admin_students():
    # Retrieve students who belong to classes managed by this admin
    class_ids = [c.id for c in get_admin_classes()]
    return Student.query.filter(Student.class_id.in_(class_ids)).all()

@main_bp.route('/')
def index():
    if current_user.is_authenticated:
        if current_user.role == 'admin':
            return redirect(url_for('main.dashboard'))
        elif current_user.role == 'student':
            return redirect(url_for('student.dashboard'))

    # Load resources needed for unified auth SPA inside landing page
    from flask import session, current_app
    classes = Class.query.all()
    google_enabled = bool(current_app.config.get('GOOGLE_CLIENT_ID') and 
                          current_app.config.get('GOOGLE_CLIENT_SECRET'))
    google_data = session.get('google_signup_data')
    
    state = request.args.get('state', 'welcome')
    email = request.args.get('email', '')
    
    return render_template(
        'landing.html', 
        classes=classes, 
        google_enabled=google_enabled, 
        state=state, 
        google_data=google_data,
        email=email
    )

def get_retention_risk_students():
    """
    Identifies students with ZERO attendance records in the last 5 days.
    Matches admin-managed students under multi-tenancy.
    """
    from datetime import timedelta
    from sqlalchemy.orm import joinedload

    admin_students = get_admin_students()
    admin_student_ids = [s.id for s in admin_students]

    if not admin_student_ids:
        return []

    five_days_ago = date.today() - timedelta(days=5)

    # 1. Get IDs of all students with *any* attendance in the last 5 days
    attended_student_ids = db.session.query(Attendance.student_id).filter(
        Attendance.date >= five_days_ago,
        Attendance.student_id.in_(admin_student_ids)
    ).distinct().all()
    attended_student_ids = [s[0] for s in attended_student_ids]

    # 2. Get all students whose IDs are NOT in the attended list
    risk_students = Student.query.filter(
        Student.id.in_(admin_student_ids),
        Student.id.notin_(attended_student_ids)
    ).options(joinedload(Student.class_assigned)).all()

    return risk_students

@main_bp.route('/dashboard')
@login_required
@admin_required
def dashboard():
    students_list = get_admin_students()
    subjects = get_admin_subjects()
    classes = get_admin_classes()

    total_students = len(students_list)
    subjects_managed = len(subjects)
    
    subject_names = [sub.name for sub in subjects]
    attendance_percentages = []
    today = date.today()

    for subject in subjects:
        # Count registered students in this subject's class
        students_in_class = Student.query.filter_by(class_id=subject.class_id).count()
        if students_in_class > 0:
            present_count = db.session.query(Attendance.student_id).filter_by(
                subject_id=subject.id, date=today, status='Present'
            ).distinct().count()
            percentage = (present_count / students_in_class) * 100
            attendance_percentages.append(round(percentage, 2))
        else:
            attendance_percentages.append(0)

    # Calculate overall attendance dynamically for each student
    for student in students_list:
        student_subjects = Subject.query.filter_by(class_id=student.class_id).all()
        total_p = 0
        total_s = 0
        for sub in student_subjects:
            total_sessions = db.session.query(db.func.count(db.func.distinct(Attendance.date)))\
                .filter_by(subject_id=sub.id).scalar() or 0
            if total_sessions > 0:
                present_count = Attendance.query.filter_by(
                    student_id=student.id,
                    subject_id=sub.id,
                    status='Present'
                ).count()
                total_p += present_count
                total_s += total_sessions
        student.overall_attendance = round((total_p / total_s) * 100, 2) if total_s > 0 else 0.0

    # Build Class-wise Interactive Metrics Map
    class_details = {}
    for c in classes:
        c_students = [s for s in students_list if s.class_id == c.id]
        enroll_count = len(c_students)
        
        c_subjects = Subject.query.filter_by(class_id=c.id).all()
        class_teacher_name = c.class_teacher.name if c.class_teacher else "No Class Teacher Assigned"
        teachers_list = list(set([sub.teacher.name for sub in c_subjects if sub.teacher]))
        teachers_str = ", ".join(teachers_list) if teachers_list else "None"
        faculty_display = f"Class Teacher: {class_teacher_name} | Subjects: {teachers_str}"
        
        total_p = 0
        total_s = 0
        for student in c_students:
            for sub in c_subjects:
                total_sessions = db.session.query(db.func.count(db.func.distinct(Attendance.date)))\
                    .filter_by(subject_id=sub.id).scalar() or 0
                if total_sessions > 0:
                    present_count = Attendance.query.filter_by(
                        student_id=student.id,
                        subject_id=sub.id,
                        status='Present'
                    ).count()
                    total_p += present_count
                    total_s += total_sessions
        
        avg_attendance = round((total_p / total_s) * 100, 2) if total_s > 0 else 0.0
        
        class_details[f"class-{c.id}"] = {
            "name": c.name,
            "enrolled": enroll_count,
            "faculty": faculty_display,
            "avg_attendance": f"{avg_attendance}%"
        }

    # "All Classes" global metrics
    all_teachers = list(set([sub.teacher.name for sub in subjects if sub.teacher]))
    all_teachers_str = ", ".join(all_teachers) if all_teachers else "No Faculty"
    all_teachers_display = f"Subjects: {all_teachers_str}"
    
    overall_p = 0
    overall_s = 0
    for student in students_list:
        student_subjects = Subject.query.filter_by(class_id=student.class_id).all()
        for sub in student_subjects:
            total_sessions = db.session.query(db.func.count(db.func.distinct(Attendance.date)))\
                .filter_by(subject_id=sub.id).scalar() or 0
            if total_sessions > 0:
                present_count = Attendance.query.filter_by(
                    student_id=student.id,
                    subject_id=sub.id,
                    status='Present'
                ).count()
                overall_p += present_count
                overall_s += total_sessions
    overall_avg = round((overall_p / overall_s) * 100, 2) if overall_s > 0 else 0.0
    
    class_details["all"] = {
        "name": "All Classes",
        "enrolled": total_students,
        "faculty": "",
        "avg_attendance": f"{overall_avg}%"
    }

    # For default load
    all_teachers_str = ""

    retention_risk_students = get_retention_risk_students()

    return render_template(
        'dashboard.html',
        student_count=total_students,
        subjects_managed=subjects_managed,
        students=students_list,
        subject_names=subject_names,
        attendance_percentages=attendance_percentages,
        retention_risk_students=retention_risk_students,
        classes=classes,
        class_details=class_details,
        overall_avg=overall_avg,
        all_teachers_str=all_teachers_str
    )

@main_bp.route('/manage_classes', methods=['GET', 'POST'])
@login_required
@admin_required
def manage_classes():
    if request.method == 'POST':
        class_name = request.form.get('class_name')
        class_teacher_id = request.form.get('class_teacher_id')
        if class_name:
            existing = Class.query.filter_by(name=class_name).first()
            if existing:
                flash('Class name already exists.', 'warning')
            else:
                teacher_id = int(class_teacher_id) if class_teacher_id else None
                new_class = Class(name=class_name, admin_id=current_user.id, class_teacher_id=teacher_id)
                db.session.add(new_class)
                db.session.commit()
                flash(f"Class '{class_name}' added successfully!", 'success')
        else:
            flash('Class name cannot be empty.', 'warning')
        return redirect(url_for('main.manage_classes'))

    classes = get_admin_classes()
    teachers = get_admin_teachers()
    return render_template('manage_classes.html', classes=classes, teachers=teachers)

@main_bp.route('/assign_class_teacher/<int:class_id>', methods=['POST'])
@login_required
@admin_required
def assign_class_teacher(class_id):
    class_item = Class.query.get_or_404(class_id)
    if class_item.admin_id and class_item.admin_id != current_user.id:
        flash("You do not have permission to modify this class.", "danger")
        return redirect(url_for('main.manage_classes'))
    
    teacher_id = request.form.get('class_teacher_id')
    if teacher_id:
        class_item.class_teacher_id = int(teacher_id)
    else:
        class_item.class_teacher_id = None
        
    db.session.commit()
    flash(f"Class Teacher updated successfully for '{class_item.name}'!", "success")
    return redirect(url_for('main.manage_classes'))

@main_bp.route('/delete_class/<int:class_id>', methods=['POST'])
@login_required
@admin_required
def delete_class(class_id):
    # Ensure this class belongs to the admin
    class_to_delete = Class.query.get_or_404(class_id)
    if class_to_delete.admin_id and class_to_delete.admin_id != current_user.id:
        flash("You do not have permission to delete this class.", "danger")
        return redirect(url_for('main.manage_classes'))
        
    try:
        db.session.delete(class_to_delete)
        db.session.commit()
        flash(f"Class '{class_to_delete.name}' and all its associated data have been deleted.", 'success')
    except Exception as e:
        db.session.rollback()
        flash(f"Error deleting class: {e}", 'danger')
    return redirect(url_for('main.manage_classes'))

@main_bp.route('/add_teacher', methods=['POST'])
@login_required
@admin_required
def add_teacher():
    teacher_name = request.form.get('teacher_name')
    if teacher_name:
        existing = Teacher.query.filter_by(name=teacher_name, admin_id=current_user.id).first()
        if existing:
            flash('Teacher already exists under your profile.', 'warning')
        else:
            new_teacher = Teacher(name=teacher_name, admin_id=current_user.id)
            db.session.add(new_teacher)
            db.session.commit()
            flash(f"Teacher '{teacher_name}' added successfully!", 'success')
    else:
        flash('Teacher name cannot be empty.', 'warning')
    return redirect(url_for('main.manage_subjects'))

@main_bp.route('/manage_subjects', methods=['GET', 'POST'])
@login_required
@admin_required
def manage_subjects():
    if request.method == 'POST':
        subject_name = request.form.get('subject_name')
        teacher_id = request.form.get('teacher_id')
        class_id = request.form.get('class_id')

        if not all([subject_name, teacher_id, class_id]):
            flash('All fields are required.', 'warning')
            return redirect(url_for('main.manage_subjects'))

        existing = Subject.query.filter_by(name=subject_name, class_id=class_id, admin_id=current_user.id).first()
        if existing:
            flash('This subject already exists for this class.', 'warning')
        else:
            new_subject = Subject(name=subject_name, teacher_id=teacher_id, class_id=class_id, admin_id=current_user.id)
            db.session.add(new_subject)
            db.session.commit()
            flash('New subject added successfully!', 'success')
        return redirect(url_for('main.manage_subjects'))

    teachers = get_admin_teachers()
    subjects = get_admin_subjects()
    classes = get_admin_classes()
    return render_template('manage_subjects.html', teachers=teachers, subjects=subjects, classes=classes)

@main_bp.route('/delete_teacher/<int:teacher_id>', methods=['POST'])
@login_required
@admin_required
def delete_teacher(teacher_id):
    teacher_to_delete = Teacher.query.get_or_404(teacher_id)
    if teacher_to_delete.admin_id and teacher_to_delete.admin_id != current_user.id:
        flash("You do not have permission to delete this teacher.", "danger")
        return redirect(url_for('main.manage_subjects'))

    if teacher_to_delete.subjects:
        flash(f"Cannot delete '{teacher_to_delete.name}'. They are still assigned to one or more subjects.", 'danger')
    else:
        db.session.delete(teacher_to_delete)
        db.session.commit()
        flash(f"Teacher '{teacher_to_delete.name}' deleted successfully.", 'success')
    return redirect(url_for('main.manage_subjects'))

@main_bp.route('/delete_subject/<int:subject_id>', methods=['POST'])
@login_required
@admin_required
def delete_subject(subject_id):
    subject_to_delete = Subject.query.get_or_404(subject_id)
    if subject_to_delete.admin_id and subject_to_delete.admin_id != current_user.id:
        flash("You do not have permission to delete this subject.", "danger")
        return redirect(url_for('main.manage_subjects'))

    try:
        Attendance.query.filter_by(subject_id=subject_id).delete()
        db.session.delete(subject_to_delete)
        db.session.commit()
        flash(f"Subject '{subject_to_delete.name}' deleted successfully.", 'success')
    except Exception as e:
        db.session.rollback()
        flash(f"Error deleting subject: {e}", 'danger')
    return redirect(url_for('main.manage_subjects'))

@main_bp.route('/register_student', methods=['GET', 'POST'])
@login_required
@admin_required
def register_student():
    if request.method == 'POST':
        name = request.form.get('name')
        roll_no = request.form.get('roll_no')
        enrollment_no = request.form.get('enrollment_no')
        class_id = request.form.get('class_id')
        student_photo = request.files.get('student_photo')
        captured_base64 = request.form.get('captured_image_base64')

        if not class_id:
            flash('You must select a class.', 'danger')
            return redirect(request.url)
        
        # Check if either base64 captured photo or uploaded photo is provided
        if not (captured_base64 and captured_base64.strip()) and not student_photo:
            flash('No photo was provided.', 'danger')
            return redirect(request.url)

        if Student.query.filter_by(roll_no=roll_no).first() or Student.query.filter_by(enrollment_no=enrollment_no).first():
            flash('A student with this roll or enrollment number already exists.', 'danger')
            return redirect(request.url)

        # Handle face scan
        face_encoding_bytes = None
        filename = None
        
        if captured_base64 and captured_base64.strip():
            result = save_base64_image(captured_base64, roll_no, name, FACES_FOLDER)
            if result:
                filename, filepath = result
                try:
                    image = face_recognition.load_image_file(filepath)
                    encodings = face_recognition.face_encodings(image)
                    if len(encodings) == 1:
                        face_encoding_bytes = encodings[0].tobytes()
                    else:
                        flash(f'{len(encodings)} faces found in captured photo. Please capture a clear image of ONLY one student.', 'danger')
                        if os.path.exists(filepath):
                            os.remove(filepath)
                        return redirect(request.url)
                except Exception as e:
                    flash(f'An error occurred: {e}', 'danger')
                    if os.path.exists(filepath):
                        os.remove(filepath)
                    return redirect(request.url)
            else:
                flash('Invalid captured photo.', 'danger')
                return redirect(request.url)
        elif student_photo and student_photo.filename:
            filename = secure_filename(f"{roll_no}_{name}_{student_photo.filename}")
            filepath = os.path.join(FACES_FOLDER, filename)
            student_photo.save(filepath)
            
            try:
                image = face_recognition.load_image_file(filepath)
                encodings = face_recognition.face_encodings(image)
                if len(encodings) == 1:
                    face_encoding_bytes = encodings[0].tobytes()
                else:
                    flash(f'{len(encodings)} faces found. Please use a photo of only one student.', 'danger')
                    if os.path.exists(filepath):
                        os.remove(filepath)
                    return redirect(request.url)
            except Exception as e:
                flash(f'An error occurred: {e}', 'danger')
                if os.path.exists(filepath):
                    os.remove(filepath)
                return redirect(request.url)
        else:
            flash('No photo was uploaded.', 'danger')
            return redirect(request.url)

        new_student = Student(
            name=name, 
            roll_no=roll_no, 
            enrollment_no=enrollment_no, 
            class_id=class_id,
            face_encoding=face_encoding_bytes, 
            image_filename=filename
        )
        db.session.add(new_student)
        db.session.commit()
        flash('Student registered successfully!', 'success')
        return redirect(url_for('main.dashboard'))

    classes = get_admin_classes()
    return render_template('register_student.html', classes=classes)

@main_bp.route('/take_attendance', methods=['GET', 'POST'])
@login_required
@admin_required
def take_attendance():
    today = date.today()
    results = None

    if request.method == 'POST':
        class_id = request.form.get('class_id')
        subject_id = request.form.get('subject_id')
        group_photos = request.files.getlist('group_photo')
        captured_base64_list = request.form.getlist('captured_images_base64')

        if not all([class_id, subject_id]):
            flash('Please select both a class and a subject.', 'warning')
            return redirect(url_for('main.take_attendance'))

        has_uploaded_files = any(p.filename for p in group_photos)
        has_captured_photos = any(c.strip() for c in captured_base64_list)

        if not has_uploaded_files and not has_captured_photos:
            flash('No group photos were uploaded or captured.', 'danger')
            return redirect(url_for('main.take_attendance'))

        # Fetch registered students in this class
        known_students = Student.query.filter_by(class_id=class_id).all()
        subject = Subject.query.get(subject_id)
        if not known_students:
            flash('No students are registered in this class.', 'danger')
            return redirect(url_for('main.take_attendance'))

        # Filter out students who don't have face encodings yet
        valid_students = [s for s in known_students if s.face_encoding is not None]
        if not valid_students:
            flash('None of the registered students in this class have uploaded face photos.', 'danger')
            return redirect(url_for('main.take_attendance'))

        known_face_encodings = [np.frombuffer(s.face_encoding, dtype=np.float64) for s in valid_students]
        known_student_data = {s.id: s for s in valid_students}
        present_student_ids = set()
        total_faces_found = 0

        # Collect temporary image file paths to process
        temp_photo_paths = []

        # 1. Process uploaded files
        if has_uploaded_files:
            for group_photo in group_photos:
                if group_photo.filename:
                    filename = secure_filename(f"upload_{datetime.now().strftime('%Y%m%d%H%M%S')}_{group_photo.filename}")
                    filepath = os.path.join(GROUP_PHOTOS_FOLDER, filename)
                    group_photo.save(filepath)
                    temp_photo_paths.append(filepath)

        # 2. Process camera-captured base64 photos
        if has_captured_photos:
            import base64
            import uuid
            for idx, base64_str in enumerate(captured_base64_list):
                if base64_str and base64_str.startswith('data:image/'):
                    try:
                        format, imgstr = base64_str.split(';base64,')
                        ext = format.split('/')[-1]
                        if ext == 'jpeg':
                            ext = 'jpg'
                        image_data = base64.b64decode(imgstr)
                        filename = f"camera_{datetime.now().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:8]}.{ext}"
                        filepath = os.path.join(GROUP_PHOTOS_FOLDER, filename)
                        with open(filepath, 'wb') as f:
                            f.write(image_data)
                        temp_photo_paths.append(filepath)
                    except Exception as e:
                        flash(f"Error saving captured camera frame {idx + 1}: {e}", "danger")

        # Now run face recognition on all collected photo paths
        for filepath in temp_photo_paths:
            try:
                unknown_image = face_recognition.load_image_file(filepath)
                unknown_face_encodings = face_recognition.face_encodings(unknown_image)
                total_faces_found += len(unknown_face_encodings)
                for face_encoding in unknown_face_encodings:
                    matches = face_recognition.compare_faces(known_face_encodings, face_encoding, tolerance=0.6)
                    if True in matches:
                        first_match_index = matches.index(True)
                        student_id = valid_students[first_match_index].id
                        present_student_ids.add(student_id)
            except Exception as e:
                flash(f"Error processing image {os.path.basename(filepath)}: {e}", "danger")
            finally:
                if os.path.exists(filepath):
                    try:
                        os.remove(filepath)
                    except Exception as e:
                        print(f"Error removing temp file {filepath}: {e}")

        # Record Present records
        time_now = datetime.now().strftime('%I:%M %p')
        for student_id in present_student_ids:
            if not Attendance.query.filter_by(student_id=student_id, date=today, subject_id=subject_id).first():
                new_attendance = Attendance(
                    student_id=student_id, 
                    date=today, 
                    status='Present', 
                    subject_id=subject_id,
                    time_marked=time_now
                )
                db.session.add(new_attendance)
        db.session.commit()

        # Compile list of present students
        present_students_details = [known_student_data[sid] for sid in present_student_ids]
        results = {
            'total_faces': total_faces_found,
            'present_students': present_students_details,
            'subject_name': subject.name
        }
        flash(f"Attendance marked for {len(present_students_details)} student(s) in {subject.name}.", 'success')

    classes = get_admin_classes()
    subjects = get_admin_subjects()
    
    # Restrict today's records view to the admin's students
    admin_student_ids = [s.id for s in get_admin_students()]
    todays_records = Attendance.query.filter(
        Attendance.date == today, 
        Attendance.student_id.in_(admin_student_ids)
    ).all()
    
    attendance_log = defaultdict(list)
    for record in todays_records:
        if record.subject:
            attendance_log[record.subject.name].append(record)

    return render_template('take_attendance.html', classes=classes, subjects=subjects,
                           attendance_log=dict(attendance_log), today=today.strftime('%Y-%m-%d'),
                           results=results)

@main_bp.route('/delete_attendance/<int:attendance_id>', methods=['POST'])
@login_required
@admin_required
def delete_attendance(attendance_id):
    record_to_delete = Attendance.query.get_or_404(attendance_id)
    # Validate permission: student must belong to admin
    student = Student.query.get(record_to_delete.student_id)
    admin_classes = [c.id for c in get_admin_classes()]
    if student.class_id not in admin_classes:
        flash("Unauthorized action.", "danger")
        return redirect(url_for('main.take_attendance'))

    db.session.delete(record_to_delete)
    db.session.commit()
    flash('Attendance record deleted.', 'success')
    return redirect(url_for('main.take_attendance'))

@main_bp.route('/delete_todays_attendance', methods=['POST'])
@login_required
@admin_required
def delete_todays_attendance():
    today = date.today()
    admin_student_ids = [s.id for s in get_admin_students()]
    try:
        # Delete only records belonging to the admin's students
        Attendance.query.filter(
            Attendance.date == today, 
            Attendance.student_id.in_(admin_student_ids)
        ).delete(synchronize_session=False)
        db.session.commit()
        flash("All of today's attendance records for your students have been deleted.", 'success')
    except Exception as e:
        db.session.rollback()
        flash(f"An error occurred: {e}", 'danger')
    return redirect(url_for('main.take_attendance'))

@main_bp.route('/reports')
@login_required
@admin_required
def view_reports():
    all_students = get_admin_students()
    # Sort by class name and student name
    all_students = sorted(all_students, key=lambda x: (x.class_assigned.name, x.name))
    return render_template('view_reports.html', students=all_students)

@main_bp.route('/delete_student/<int:student_id>', methods=['POST'])
@login_required
@admin_required
def delete_student(student_id):
    student_to_delete = Student.query.get_or_404(student_id)
    
    # Check permissions
    admin_classes = [c.id for c in get_admin_classes()]
    if student_to_delete.class_id not in admin_classes:
        flash("Unauthorized action.", "danger")
        return redirect(url_for('main.dashboard'))

    referrer = request.referrer
    try:
        if student_to_delete.image_filename:
            image_filepath = os.path.join(FACES_FOLDER, student_to_delete.image_filename)
            if os.path.exists(image_filepath): 
                os.remove(image_filepath)
                
        # If student has an associated User login, delete that too
        if student_to_delete.user_id:
            student_user = User.query.get(student_to_delete.user_id)
            if student_user:
                db.session.delete(student_user)

        db.session.delete(student_to_delete)
        db.session.commit()
        flash('Student deleted successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting student: {e}', 'danger')

    if referrer and 'dashboard' in referrer:
        return redirect(url_for('main.dashboard'))
    else:
        return redirect(url_for('main.view_reports'))

@main_bp.route('/uploads/faces/<filename>')
def uploaded_face(filename):
    return send_from_directory(FACES_FOLDER, filename)

@main_bp.route('/get_subjects/<int:class_id>')
@login_required
def get_subjects(class_id):
    # Expose subjects of a class, ensuring the class is visible
    class_item = Class.query.get_or_404(class_id)
    if class_item.admin_id and class_item.admin_id != current_user.id:
        return jsonify({'error': 'Unauthorized'}), 403
        
    subjects = Subject.query.filter_by(class_id=class_id).all()
    subject_list = [
        {
            'id': subject.id,
            'name': subject.name,
            'teacher_name': subject.teacher.name if subject.teacher else 'No Teacher'
        } for subject in subjects
    ]
    return jsonify({'subjects': subject_list})

@main_bp.route('/admin/approvals')
@login_required
@admin_required
def approvals():
    admin_classes = [c.id for c in get_admin_classes()]
    edit_requests = StudentEditRequest.query.join(Student).filter(
        Student.class_id.in_(admin_classes),
        StudentEditRequest.status == 'Pending'
    ).order_by(StudentEditRequest.created_at.desc()).all()
    
    return render_template('admin_approvals.html', requests=edit_requests)

@main_bp.route('/admin/approval/<int:request_id>/<action>', methods=['POST'])
@login_required
@admin_required
def handle_approval(request_id, action):
    req = StudentEditRequest.query.get_or_404(request_id)
    
    # Check permissions
    admin_classes = [c.id for c in get_admin_classes()]
    if req.student.class_id not in admin_classes:
        flash("You do not have permission to review this request.", "danger")
        return redirect(url_for('main.approvals'))

    student = req.student
    
    if action == 'approve':
        try:
            # Delete old face photo from disk if new photo was uploaded
            if req.new_image_filename and req.new_image_filename != student.image_filename:
                # Rename the new image from pending_ to clean name
                old_path = os.path.join(FACES_FOLDER, student.image_filename) if student.image_filename else None
                if old_path and os.path.exists(old_path):
                    os.remove(old_path)

            # Update student record
            student.name = req.new_name
            student.roll_no = req.new_roll_no
            student.enrollment_no = req.new_enrollment_no
            student.class_id = req.new_class_id
            student.image_filename = req.new_image_filename
            student.face_encoding = req.new_face_encoding
            
            # If student has a linked User account, update their display name there too
            if student.user_id:
                user = User.query.get(student.user_id)
                if user:
                    user.name = req.new_name

            db.session.delete(req) # Remove request from queue
            db.session.commit()
            flash(f"Profile change request for student '{student.name}' approved successfully!", "success")
        except Exception as e:
            db.session.rollback()
            flash(f"An error occurred while approving: {e}", "danger")
            
    elif action == 'reject':
        try:
            # If they uploaded a new face photo, delete that pending photo from disk to save space
            if req.new_image_filename and req.new_image_filename != student.image_filename:
                filepath = os.path.join(FACES_FOLDER, req.new_image_filename)
                if os.path.exists(filepath):
                    os.remove(filepath)
            
            db.session.delete(req) # Remove request from queue
            db.session.commit()
            flash(f"Profile change request for student '{student.name}' rejected and discarded.", "info")
        except Exception as e:
            db.session.rollback()
            flash(f"An error occurred: {e}", "danger")

    return redirect(url_for('main.approvals'))

@main_bp.route('/retention_risk_report')
@login_required
@admin_required
def retention_risk_report():
    """Generates and displays the detailed report on at-risk students."""
    from datetime import date, timedelta
    
    risk_students = get_retention_risk_students()

    today = date.today()
    five_days_ago = today - timedelta(days=5)

    student_details = []
    for student in risk_students:
        # Get count of attendance records for the risk period
        attendance_count = Attendance.query.filter(
            Attendance.student_id == student.id,
            Attendance.date >= five_days_ago
        ).count()

        student_details.append({
            'student': student,
            'class_name': student.class_assigned.name if student.class_assigned else 'No Class',
            'attendance_count': attendance_count
        })

    return render_template(
        'retention_risk_report.html',
        risk_students_data=student_details,
        report_start_date=five_days_ago.strftime('%Y-%m-%d'),
        report_end_date=today.strftime('%Y-%m-%d'),
        total_risk_students=len(student_details)
    )

@main_bp.route('/download_risk_report')
@login_required
@admin_required
def download_risk_report():
    """Generates a CSV file of the retention risk students for download."""
    import io
    import csv
    from flask import make_response
    
    risk_students = get_retention_risk_students()
    today = date.today()

    si = io.StringIO()
    cw = csv.writer(si)

    # CSV Header
    cw.writerow(['Name', 'Roll Number', 'Enrollment Number', 'Class Name', 'Status (Last 5 Days)'])

    # CSV Data Rows
    for student in risk_students:
        cw.writerow([
            student.name,
            student.roll_no,
            student.enrollment_no,
            student.class_assigned.name if student.class_assigned else 'No Class',
            'ZERO Attendance'
        ])

    output = si.getvalue()
    response = make_response(output)
    response.headers["Content-Disposition"] = f"attachment; filename=Retention_Risk_Report_{today.strftime('%Y%m%d')}.csv"
    response.headers["Content-type"] = "text/csv"

    return response

# ─────────────────────────────────────────────────────────────────────────────
# ASSIGN STUDENTS TO CLASSES (Admin Panel)
# ─────────────────────────────────────────────────────────────────────────────

@main_bp.route('/assign_students', methods=['GET', 'POST'])
@login_required
@admin_required
def assign_students():
    """Admin assigns unclassified students (class_id=None) to classes."""
    classes = get_admin_classes()

    if request.method == 'POST':
        assigned_count = 0
        for key, value in request.form.items():
            if key.startswith('class_for_student_') and value:
                try:
                    student_id = int(key.replace('class_for_student_', ''))
                    class_id = int(value)
                    student = Student.query.get(student_id)
                    target_class = Class.query.filter(
                        Class.id == class_id,
                        (Class.admin_id == None) | (Class.admin_id == current_user.id)
                    ).first()
                    if student and target_class:
                        student.class_id = class_id
                        assigned_count += 1
                except (ValueError, TypeError):
                    continue
        if assigned_count:
            db.session.commit()
            flash(f'Successfully assigned {assigned_count} student(s) to their classes.', 'success')
        else:
            flash('No assignments were made. Please select a class for at least one student.', 'warning')
        return redirect(url_for('main.assign_students'))

    unclassified_students = Student.query.filter(Student.class_id == None).all()
    return render_template('assign_students.html',
                           unclassified_students=unclassified_students,
                           classes=classes)

@main_bp.app_context_processor
def inject_pending_approvals():
    if current_user.is_authenticated and current_user.role == 'admin':
        try:
            class_ids = [c.id for c in get_admin_classes()]
            count = StudentEditRequest.query.join(Student).filter(
                Student.class_id.in_(class_ids),
                StudentEditRequest.status == 'Pending'
            ).count()
            unclassified_count = Student.query.filter(Student.class_id == None).count()
            return {
                'pending_approvals_count': count,
                'unclassified_students_count': unclassified_count
            }
        except Exception:
            return {'pending_approvals_count': 0, 'unclassified_students_count': 0}
    return {'pending_approvals_count': 0, 'unclassified_students_count': 0}