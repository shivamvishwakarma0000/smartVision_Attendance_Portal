import os
import face_recognition
import numpy as np
from flask import render_template, redirect, url_for, flash, request, Blueprint, current_app
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from functools import wraps

from extensions import db
from models import User, Student, Class, Subject, Attendance, StudentEditRequest
from auth.routes import save_base64_image

student_bp = Blueprint('student', __name__)

FACES_FOLDER = os.path.join('temp_uploads', 'faces')

def student_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'student':
            flash("Student access is required to view this page.", "danger")
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function

@student_bp.route('/student/dashboard')
@login_required
@student_required
def dashboard():
    # Retrieve the linked student profile
    student = current_user.student_profile
    if not student:
        flash("Student profile not found. Please contact administration.", "danger")
        return redirect(url_for('auth.logout'))

    # Retrieve all subjects assigned to this student's class
    subjects = Subject.query.filter_by(class_id=student.class_id).all()
    
    subject_names = []
    attendance_percentages = []
    
    subject_stats = {}
    
    # Calculate attendance percentages for each subject
    for subject in subjects:
        # Sessions held: unique dates that attendance was taken for this subject
        total_sessions = db.session.query(db.func.count(db.func.distinct(Attendance.date)))\
            .filter_by(subject_id=subject.id).scalar() or 0
            
        if total_sessions > 0:
            # Marked present sessions
            present_count = Attendance.query.filter_by(
                student_id=student.id,
                subject_id=subject.id,
                status='Present'
            ).count()
            
            percentage = (present_count / total_sessions) * 100
            rounded_percentage = round(percentage, 2)
            
            subject_names.append(subject.name)
            attendance_percentages.append(rounded_percentage)
            
            subject_stats[subject.name] = {
                'present': present_count,
                'total': total_sessions,
                'percentage': rounded_percentage,
                'teacher': subject.teacher.name if subject.teacher else "No Teacher"
            }
        else:
            subject_names.append(subject.name)
            attendance_percentages.append(0.0)
            subject_stats[subject.name] = {
                'present': 0,
                'total': 0,
                'percentage': 0.0,
                'teacher': subject.teacher.name if subject.teacher else "No Teacher"
            }

    # Fetch all detailed attendance logs for this student
    records = Attendance.query.filter_by(student_id=student.id).order_by(Attendance.date.desc()).all()

    # Check for pending edit requests
    pending_request = StudentEditRequest.query.filter_by(student_id=student.id, status='Pending').first()

    return render_template(
        'student_dashboard.html',
        student=student,
        subject_names=subject_names,
        attendance_percentages=attendance_percentages,
        subject_stats=subject_stats,
        records=records,
        pending_request=pending_request
    )

@student_bp.route('/student/profile/photo', methods=['GET', 'POST'])
@login_required
@student_required
def update_photo():
    student = current_user.student_profile
    if not student:
        flash("Student profile not found.", "danger")
        return redirect(url_for('auth.logout'))

    if request.method == 'POST':
        student_photo = request.files.get('student_photo')
        captured_base64 = request.form.get('captured_image_base64')

        if captured_base64 and captured_base64.strip():
            result = save_base64_image(captured_base64, student.roll_no, student.name, FACES_FOLDER)
            if result:
                filename, filepath = result
                try:
                    image = face_recognition.load_image_file(filepath)
                    encodings = face_recognition.face_encodings(image)
                    if len(encodings) == 1:
                        face_encoding_bytes = encodings[0].tobytes()
                        
                        # Delete old photo if it exists
                        if student.image_filename:
                            old_path = os.path.join(FACES_FOLDER, student.image_filename)
                            if os.path.exists(old_path):
                                os.remove(old_path)
                        
                        # Update student record
                        student.face_encoding = face_encoding_bytes
                        student.image_filename = filename
                        db.session.commit()
                        flash('Your face registration photo has been successfully updated!', 'success')
                        return redirect(url_for('student.dashboard'))
                    else:
                        flash(f'{len(encodings)} faces found. Please use a clear photo containing ONLY your own face.', 'danger')
                        if os.path.exists(filepath):
                            os.remove(filepath)
                except Exception as e:
                    flash(f'An error occurred while scanning face encoding: {e}', 'danger')
                    if os.path.exists(filepath):
                        os.remove(filepath)
            else:
                flash('Invalid captured photo.', 'danger')
        elif student_photo and student_photo.filename:
            os.makedirs(FACES_FOLDER, exist_ok=True)
            filename = secure_filename(f"{student.roll_no}_{student.name}_{student_photo.filename}")
            filepath = os.path.join(FACES_FOLDER, filename)
            student_photo.save(filepath)

            try:
                image = face_recognition.load_image_file(filepath)
                encodings = face_recognition.face_encodings(image)
                if len(encodings) == 1:
                    face_encoding_bytes = encodings[0].tobytes()
                    
                    # Delete old photo if it exists
                    if student.image_filename:
                        old_path = os.path.join(FACES_FOLDER, student.image_filename)
                        if os.path.exists(old_path):
                            os.remove(old_path)
                    
                    # Update student record
                    student.face_encoding = face_encoding_bytes
                    student.image_filename = filename
                    db.session.commit()
                    flash('Your face registration photo has been successfully updated!', 'success')
                    return redirect(url_for('student.dashboard'))
                else:
                    flash(f'{len(encodings)} faces found. Please use a clear photo containing ONLY your own face.', 'danger')
                    if os.path.exists(filepath):
                        os.remove(filepath)
            except Exception as e:
                flash(f'An error occurred while scanning face encoding: {e}', 'danger')
                if os.path.exists(filepath):
                    os.remove(filepath)
        else:
            flash('Please upload a valid photo file.', 'danger')
            return redirect(request.url)

    return render_template('student_register_photo.html', student=student)

@student_bp.route('/student/profile/edit', methods=['GET', 'POST'])
@login_required
@student_required
def edit_profile():
    student = current_user.student_profile
    if not student:
        flash("Student profile not found.", "danger")
        return redirect(url_for('auth.logout'))

    # Check if there is already a pending edit request
    pending_request = StudentEditRequest.query.filter_by(student_id=student.id, status='Pending').first()

    if request.method == 'POST':
        if pending_request:
            flash("You already have a pending profile change request. Please wait for an administrator to review it.", "warning")
            return redirect(url_for('student.dashboard'))

        name = request.form.get('name')
        class_id = request.form.get('class_id')
        roll_no = request.form.get('roll_no')
        enrollment_no = request.form.get('enrollment_no')
        student_photo = request.files.get('student_photo')

        if not all([name, class_id, roll_no, enrollment_no]):
            flash("Name, Class, Roll Number, and Enrollment Number are required.", "danger")
            return redirect(request.url)

        # Check unique constraints against OTHER students
        existing_roll = Student.query.filter(Student.roll_no == roll_no, Student.id != student.id).first()
        existing_enroll = Student.query.filter(Student.enrollment_no == enrollment_no, Student.id != student.id).first()
        if existing_roll or existing_enroll:
            flash("A student with this roll or enrollment number already exists.", "danger")
            return redirect(request.url)

        new_filename = None
        new_face_encoding_bytes = None

        # Check photo upload
        captured_base64 = request.form.get('captured_image_base64')
        if captured_base64 and captured_base64.strip():
            result = save_base64_image(captured_base64, f"pending_{roll_no}", name, FACES_FOLDER)
            if result:
                new_filename, filepath = result
                try:
                    image = face_recognition.load_image_file(filepath)
                    encodings = face_recognition.face_encodings(image)
                    if len(encodings) == 1:
                        new_face_encoding_bytes = encodings[0].tobytes()
                    else:
                        flash(f'{len(encodings)} faces found in captured photo. Please capture a clear image of ONLY your own face.', 'danger')
                        if os.path.exists(filepath):
                            os.remove(filepath)
                        return redirect(request.url)
                except Exception as e:
                    flash(f'Facial scanning failed: {e}', 'danger')
                    if os.path.exists(filepath):
                        os.remove(filepath)
                    return redirect(request.url)
        elif student_photo and student_photo.filename:
            os.makedirs(FACES_FOLDER, exist_ok=True)
            new_filename = secure_filename(f"pending_{roll_no}_{name}_{student_photo.filename}")
            filepath = os.path.join(FACES_FOLDER, new_filename)
            student_photo.save(filepath)

            try:
                image = face_recognition.load_image_file(filepath)
                encodings = face_recognition.face_encodings(image)
                if len(encodings) == 1:
                    new_face_encoding_bytes = encodings[0].tobytes()
                else:
                    flash(f'{len(encodings)} faces found in photo. Please use a clear image of ONLY your own face.', 'danger')
                    if os.path.exists(filepath):
                        os.remove(filepath)
                    return redirect(request.url)
            except Exception as e:
                flash(f'Facial scanning failed: {e}', 'danger')
                if os.path.exists(filepath):
                    os.remove(filepath)
                return redirect(request.url)

        # Create edit request
        new_request = StudentEditRequest(
            student_id=student.id,
            new_name=name,
            new_roll_no=roll_no,
            new_enrollment_no=enrollment_no,
            new_class_id=class_id,
            new_image_filename=new_filename if new_filename else student.image_filename,
            new_face_encoding=new_face_encoding_bytes if new_face_encoding_bytes else student.face_encoding,
            status='Pending'
        )
        db.session.add(new_request)
        db.session.commit()
        flash("Your profile change request has been successfully submitted and is pending administrator approval.", "success")
        return redirect(url_for('student.dashboard'))

    classes = Class.query.all()
    return render_template('student_profile_edit.html', student=student, classes=classes, pending_request=pending_request)
