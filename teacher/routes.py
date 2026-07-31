import os
import face_recognition
import numpy as np
from datetime import date, datetime
from collections import defaultdict
from functools import wraps
from flask import render_template, redirect, url_for, flash, request, Blueprint, jsonify, make_response
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename

from extensions import db, get_current_date, get_current_time_str, get_current_datetime_str
from models import User, Teacher, Class, Subject, Student, Attendance
from auth.routes import save_base64_image

teacher_bp = Blueprint('teacher', __name__)

UPLOAD_FOLDER = 'temp_uploads'
GROUP_PHOTOS_FOLDER = os.path.join(UPLOAD_FOLDER, 'group_photos')
os.makedirs(GROUP_PHOTOS_FOLDER, exist_ok=True)

def teacher_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'teacher':
            flash("Teacher access is required to view this page.", "danger")
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function

def get_current_teacher():
    """Helper to retrieve teacher profile for logged-in user."""
    if hasattr(current_user, 'teacher_profile') and current_user.teacher_profile:
        return current_user.teacher_profile
    # Fallback search by email
    return Teacher.query.filter_by(email=current_user.email).first()

@teacher_bp.route('/teacher/dashboard')
@login_required
@teacher_required
def dashboard():
    teacher = get_current_teacher()
    if not teacher:
        flash("Teacher profile not found. Please contact an administrator.", "danger")
        return redirect(url_for('auth.logout'))

    # Subjects taught by this teacher
    subjects = Subject.query.filter_by(teacher_id=teacher.id).all()
    # Classes where teacher is class teacher
    directed_classes = Class.query.filter_by(class_teacher_id=teacher.id).all()
    
    # Collect all class IDs the teacher is involved in
    assigned_class_ids = set([sub.class_id for sub in subjects] + [c.id for c in directed_classes])
    assigned_classes = Class.query.filter(Class.id.in_(assigned_class_ids)).all() if assigned_class_ids else []

    today = get_current_date()
    subject_stats = []
    
    for subject in subjects:
        total_students = Student.query.filter_by(class_id=subject.class_id).count()
        total_sessions = db.session.query(db.func.count(db.func.distinct(Attendance.date)))\
            .filter_by(subject_id=subject.id).scalar() or 0
        
        today_present = db.session.query(Attendance.student_id).filter_by(
            subject_id=subject.id, date=today, status='Present'
        ).distinct().count()

        avg_attendance = 0.0
        if total_sessions > 0 and total_students > 0:
            total_present_records = Attendance.query.filter_by(subject_id=subject.id, status='Present').count()
            avg_attendance = round((total_present_records / (total_sessions * total_students)) * 100, 2)

        subject_stats.append({
            'subject': subject,
            'class_name': subject.class_assigned.name if subject.class_assigned else 'N/A',
            'total_students': total_students,
            'total_sessions': total_sessions,
            'today_present': today_present,
            'avg_attendance': avg_attendance
        })

    # Fetch recent attendance records for subjects taught by this teacher
    subject_ids = [sub.id for sub in subjects]
    recent_records = []
    if subject_ids:
        recent_records = Attendance.query.filter(Attendance.subject_id.in_(subject_ids))\
            .order_by(Attendance.date.desc(), Attendance.id.desc()).limit(20).all()

    return render_template(
        'teacher_dashboard.html',
        teacher=teacher,
        subjects=subjects,
        directed_classes=directed_classes,
        assigned_classes=assigned_classes,
        subject_stats=subject_stats,
        recent_records=recent_records,
        today=today.strftime('%Y-%m-%d')
    )

@teacher_bp.route('/teacher/take_attendance', methods=['GET', 'POST'])
@login_required
@teacher_required
def take_attendance():
    teacher = get_current_teacher()
    if not teacher:
        flash("Teacher profile not found.", "danger")
        return redirect(url_for('auth.logout'))

    subjects = Subject.query.filter_by(teacher_id=teacher.id).all()
    today = get_current_date()
    results = None

    if request.method == 'POST':
        subject_id = request.form.get('subject_id')
        group_photos = request.files.getlist('group_photo')
        captured_base64_list = request.form.getlist('captured_images_base64')

        if not subject_id:
            flash('Please select a subject.', 'warning')
            return redirect(url_for('teacher.take_attendance'))

        subject = Subject.query.get(subject_id)
        if not subject or subject.teacher_id != teacher.id:
            flash('Unauthorized subject selection.', 'danger')
            return redirect(url_for('teacher.take_attendance'))

        class_id = subject.class_id
        known_students = Student.query.filter_by(class_id=class_id).all()
        if not known_students:
            flash('No students registered in this class.', 'danger')
            return redirect(url_for('teacher.take_attendance'))

        valid_students = [s for s in known_students if s.face_encoding is not None]
        if not valid_students:
            flash('None of the students in this class have uploaded facial registration photos.', 'danger')
            return redirect(url_for('teacher.take_attendance'))

        has_uploaded_files = any(p.filename for p in group_photos)
        has_captured_photos = any(c.strip() for c in captured_base64_list)

        if not has_uploaded_files and not has_captured_photos:
            flash('No classroom photos were uploaded or captured.', 'danger')
            return redirect(url_for('teacher.take_attendance'))

        known_face_encodings = [np.frombuffer(s.face_encoding, dtype=np.float64) for s in valid_students]
        known_student_data = {s.id: s for s in valid_students}
        present_student_ids = set()
        total_faces_found = 0
        temp_photo_paths = []

        if has_uploaded_files:
            for group_photo in group_photos:
                if group_photo.filename:
                    filename = secure_filename(f"teacher_{teacher.id}_{get_current_datetime_str()}_{group_photo.filename}")
                    filepath = os.path.join(GROUP_PHOTOS_FOLDER, filename)
                    group_photo.save(filepath)
                    temp_photo_paths.append(filepath)

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
                        filename = f"teacher_cam_{get_current_datetime_str()}_{uuid.uuid4().hex[:8]}.{ext}"
                        filepath = os.path.join(GROUP_PHOTOS_FOLDER, filename)
                        with open(filepath, 'wb') as f:
                            f.write(image_data)
                        temp_photo_paths.append(filepath)
                    except Exception as e:
                        flash(f"Error saving camera frame {idx+1}: {e}", "danger")

        for filepath in temp_photo_paths:
            try:
                unknown_image = face_recognition.load_image_file(filepath)
                # Downsample large images to max dimension 800px for 10x CPU speedup
                h, w = unknown_image.shape[:2]
                if max(h, w) > 800:
                    scaling = 800.0 / float(max(h, w))
                    new_w, new_h = int(w * scaling), int(h * scaling)
                    try:
                        import cv2
                        unknown_image = cv2.resize(unknown_image, (new_w, new_h), interpolation=cv2.INTER_AREA)
                    except ImportError:
                        from PIL import Image
                        pil_img = Image.fromarray(unknown_image)
                        unknown_image = np.array(pil_img.resize((new_w, new_h), Image.Resampling.LANCZOS))

                unknown_face_encodings = face_recognition.face_encodings(unknown_image)
                total_faces_found += len(unknown_face_encodings)
                for face_encoding in unknown_face_encodings:
                    matches = face_recognition.compare_faces(known_face_encodings, face_encoding, tolerance=0.6)
                    if True in matches:
                        first_match_index = matches.index(True)
                        student_id = valid_students[first_match_index].id
                        present_student_ids.add(student_id)
            except Exception as e:
                flash(f"Error scanning photo {os.path.basename(filepath)}: {e}", "danger")
            finally:
                if os.path.exists(filepath):
                    try:
                        os.remove(filepath)
                    except Exception:
                        pass

        time_now = get_current_time_str()
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

        present_students_details = [known_student_data[sid] for sid in present_student_ids]
        results = {
            'total_faces': total_faces_found,
            'present_students': present_students_details,
            'subject_name': subject.name
        }
        flash(f"Attendance marked for {len(present_students_details)} student(s) in {subject.name}.", 'success')

    # Fetch today's records for subjects taught by this teacher
    subject_ids = [sub.id for sub in subjects]
    todays_records = []
    if subject_ids:
        todays_records = Attendance.query.filter(
            Attendance.date == today,
            Attendance.subject_id.in_(subject_ids)
        ).all()

    attendance_log = defaultdict(list)
    for record in todays_records:
        if record.subject:
            attendance_log[record.subject.name].append(record)

    return render_template(
        'teacher_take_attendance.html',
        subjects=subjects,
        attendance_log=dict(attendance_log),
        today=today.strftime('%Y-%m-%d'),
        results=results
    )

@teacher_bp.route('/teacher/reports')
@login_required
@teacher_required
def view_reports():
    teacher = get_current_teacher()
    if not teacher:
        flash("Teacher profile not found.", "danger")
        return redirect(url_for('auth.logout'))

    subjects = Subject.query.filter_by(teacher_id=teacher.id).all()
    subject_id = request.args.get('subject_id')

    selected_subject = None
    if subject_id:
        try:
            selected_subject = Subject.query.get(int(subject_id))
        except ValueError:
            pass

    if selected_subject and selected_subject.teacher_id == teacher.id:
        students = Student.query.filter_by(class_id=selected_subject.class_id).all()
        records = Attendance.query.filter_by(subject_id=selected_subject.id).order_by(Attendance.date.desc()).all()
    else:
        # Load all students across teacher's subjects
        class_ids = set([s.class_id for s in subjects])
        students = Student.query.filter(Student.class_id.in_(class_ids)).all() if class_ids else []
        subject_ids = [s.id for s in subjects]
        records = Attendance.query.filter(Attendance.subject_id.in_(subject_ids)).order_by(Attendance.date.desc()).all() if subject_ids else []

    return render_template('teacher_reports.html', subjects=subjects, students=students, records=records, selected_subject=selected_subject)

@teacher_bp.route('/teacher/download_report')
@login_required
@teacher_required
def download_report():
    import io
    import csv

    teacher = get_current_teacher()
    if not teacher:
        return redirect(url_for('auth.logout'))

    subject_id = request.args.get('subject_id')
    subjects = Subject.query.filter_by(teacher_id=teacher.id).all()
    subject_ids = [s.id for s in subjects]

    if subject_id:
        records = Attendance.query.filter_by(subject_id=int(subject_id)).all()
    else:
        records = Attendance.query.filter(Attendance.subject_id.in_(subject_ids)).all() if subject_ids else []

    si = io.StringIO()
    cw = csv.writer(si)
    cw.writerow(['Student Name', 'Roll Number', 'Enrollment Number', 'Class', 'Subject', 'Date', 'Time Marked', 'Status'])

    for rec in records:
        student = rec.student
        subject = rec.subject
        class_name = student.class_assigned.name if student and student.class_assigned else 'N/A'
        cw.writerow([
            student.name if student else 'N/A',
            student.roll_no if student else 'N/A',
            student.enrollment_no if student else 'N/A',
            class_name,
            subject.name if subject else 'N/A',
            rec.date.strftime('%Y-%m-%d'),
            rec.time_marked or 'N/A',
            rec.status
        ])

    output = si.getvalue()
    response = make_response(output)
    response.headers["Content-Disposition"] = f"attachment; filename=Teacher_Attendance_Report_{date.today().strftime('%Y%m%d')}.csv"
    response.headers["Content-type"] = "text/csv"
    return response
