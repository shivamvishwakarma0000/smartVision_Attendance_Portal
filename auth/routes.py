import os
import base64
import random
import string
import face_recognition
from datetime import datetime, timedelta
from flask import render_template, redirect, url_for, flash, request, Blueprint, session, current_app
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.utils import secure_filename
from extensions import db, oauth
from models import User, Student, Class

auth_bp = Blueprint('auth', __name__)

FACES_FOLDER = os.path.join('temp_uploads', 'faces')

def save_base64_image(base64_str, roll_no, name, folder):
    """
    Decodes a base64 data URL and saves it as a file in the specified folder.
    Returns the saved file's secure filename or None.
    """
    if not base64_str or not base64_str.startswith('data:image/'):
        return None
    try:
        format, imgstr = base64_str.split(';base64,')
        ext = format.split('/')[-1]
        if ext == 'jpeg':
            ext = 'jpg'
        image_data = base64.b64decode(imgstr)
        
        filename = secure_filename(f"{roll_no}_{name}_captured.{ext}")
        filepath = os.path.join(folder, filename)
        
        os.makedirs(folder, exist_ok=True)
        with open(filepath, 'wb') as f:
            f.write(image_data)
        return filename, filepath
    except Exception as e:
        print(f"Error decoding base64 image: {e}")
        return None

# Helper to check if Google credentials are configured
def is_google_configured():
    return (current_app.config.get('GOOGLE_CLIENT_ID') and 
            current_app.config.get('GOOGLE_CLIENT_SECRET'))

def generate_otp(length=6):
    """Generate a numeric OTP of given length."""
    return ''.join(random.choices(string.digits, k=length))

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        if current_user.role == 'admin':
            return redirect(url_for('main.dashboard'))
        elif current_user.role == 'student':
            return redirect(url_for('student.dashboard'))

    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        login_role = request.form.get('login_role', 'student')  # role hint from UI tab

        user = User.query.filter_by(email=email).first()

        if user and user.check_password(password):
            # Verify the user is logging in via the correct portal
            if login_role == 'admin' and user.role != 'admin':
                flash('This account is not an administrator account. Please use the Student portal.', 'danger')
                return redirect(url_for('main.index', state='login'))
            if login_role == 'student' and user.role != 'student':
                flash('This account is an administrator account. Please use the Admin portal.', 'danger')
                return redirect(url_for('main.index', state='login'))

            login_user(user)
            flash(f'Welcome back, {user.name}!', 'success')
            if user.role == 'admin':
                return redirect(url_for('main.dashboard'))
            elif user.role == 'student':
                return redirect(url_for('student.dashboard'))
        else:
            flash('Invalid email or password.', 'danger')
            return redirect(url_for('main.index', state='login'))

    # Redirect GET requests to the unified index page with state='login'
    return redirect(url_for('main.index', state='login'))

@auth_bp.route('/admin-login', methods=['GET', 'POST'])
def admin_login():
    if current_user.is_authenticated:
        if current_user.role == 'admin':
            return redirect(url_for('main.dashboard'))
        elif current_user.role == 'student':
            return redirect(url_for('student.dashboard'))

    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')

        user = User.query.filter_by(email=email).first()

        if user and user.check_password(password):
            if user.role != 'admin':
                flash('This portal is restricted to administrators. Please use the Student portal.', 'danger')
                return redirect(url_for('auth.admin_login'))

            login_user(user)
            flash(f'Welcome back, {user.name}!', 'success')
            return redirect(url_for('main.dashboard'))
        else:
            flash('Invalid email or password.', 'danger')
            return redirect(url_for('auth.admin_login'))

    return render_template('admin_login.html')

@auth_bp.route('/signup', methods=['GET', 'POST'])
def signup():
    if current_user.is_authenticated:
        return redirect(url_for('auth.login'))

    if request.method == 'POST':
        role = request.form.get('signup_role')
        name = request.form.get('name')
        email = request.form.get('email')
        password = request.form.get('password')

        if not all([role, name, email, password]):
            flash('Name, email, and password are required.', 'danger')
            return redirect(url_for('main.index', state='signup'))

        if len(password) < 8:
            flash('Password must be at least 8 characters long.', 'danger')
            return redirect(url_for('main.index', state='signup'))

        if User.query.filter_by(email=email).first():
            flash('This email address is already registered. Please log in.', 'danger')
            return redirect(url_for('main.index', state='signup'))

        # --- ADMIN REGISTRATION ---
        if role == 'admin':
            new_user = User(name=name, email=email, role='admin')
            new_user.set_password(password)
            db.session.add(new_user)
            db.session.commit()
            flash('Administrator account created successfully! Please login.', 'success')
            return redirect(url_for('main.index', state='login'))

        # --- STUDENT REGISTRATION ---
        elif role == 'student':
            mobile = request.form.get('mobile', '').strip()
            roll_no = request.form.get('roll_no', '').strip()
            enrollment_no = request.form.get('enrollment_no', '').strip()
            student_photo = request.files.get('student_photo')

            if not all([roll_no, enrollment_no]):
                flash('Roll Number and Enrollment Number are required for student registration.', 'danger')
                return redirect(url_for('main.index', state='signup'))

            if Student.query.filter_by(roll_no=roll_no).first():
                flash('A student with this Roll Number already exists.', 'danger')
                return redirect(url_for('main.index', state='signup'))

            if Student.query.filter_by(enrollment_no=enrollment_no).first():
                flash('A student with this Enrollment Number already exists.', 'danger')
                return redirect(url_for('main.index', state='signup'))

            # Create User account first
            new_user = User(name=name, email=email, role='student', mobile=mobile or None)
            new_user.set_password(password)

            # Handle Face Photo (optional during self-registration)
            face_encoding_bytes = None
            image_filename = None
            captured_base64 = request.form.get('captured_image_base64')

            if captured_base64 and captured_base64.strip():
                result = save_base64_image(captured_base64, roll_no, name, FACES_FOLDER)
                if result:
                    image_filename, filepath = result
                    try:
                        image = face_recognition.load_image_file(filepath)
                        encodings = face_recognition.face_encodings(image)
                        if len(encodings) == 1:
                            face_encoding_bytes = encodings[0].tobytes()
                        elif len(encodings) == 0:
                            flash('No face detected in the captured photo. Please capture a clear face photo.', 'warning')
                            if os.path.exists(filepath):
                                os.remove(filepath)
                            return redirect(url_for('main.index', state='signup'))
                        else:
                            flash(f'{len(encodings)} faces found in captured photo. Please capture a clear image of ONLY one face.', 'danger')
                            if os.path.exists(filepath):
                                os.remove(filepath)
                            return redirect(url_for('main.index', state='signup'))
                    except Exception as e:
                        flash(f'An error occurred during facial scanning: {e}', 'danger')
                        if os.path.exists(filepath):
                            os.remove(filepath)
                        return redirect(url_for('main.index', state='signup'))
            elif student_photo and student_photo.filename:
                os.makedirs(FACES_FOLDER, exist_ok=True)
                filename = secure_filename(f"{roll_no}_{name}_{student_photo.filename}")
                filepath = os.path.join(FACES_FOLDER, filename)
                student_photo.save(filepath)

                try:
                    image = face_recognition.load_image_file(filepath)
                    encodings = face_recognition.face_encodings(image)
                    if len(encodings) == 1:
                        face_encoding_bytes = encodings[0].tobytes()
                        image_filename = filename
                    elif len(encodings) == 0:
                        flash('No face detected in the photo. Please upload a clear face photo.', 'warning')
                        if os.path.exists(filepath):
                            os.remove(filepath)
                        return redirect(url_for('main.index', state='signup'))
                    else:
                        flash(f'{len(encodings)} faces found in photo. Please use a clear image of ONLY one face.', 'danger')
                        if os.path.exists(filepath):
                            os.remove(filepath)
                        return redirect(url_for('main.index', state='signup'))
                except Exception as e:
                    flash(f'An error occurred during facial scanning: {e}', 'danger')
                    if os.path.exists(filepath):
                        os.remove(filepath)
                    return redirect(url_for('main.index', state='signup'))

            try:
                db.session.add(new_user)
                db.session.flush()  # Get new_user.id

                # Retrieve selected class_id from form (optional - admin will assign if not provided)
                selected_class_id = request.form.get('class_id')
                class_id_int = None
                if selected_class_id:
                    try:
                        class_id_int = int(selected_class_id)
                    except ValueError:
                        pass
                
                new_student = Student(
                    name=name,
                    roll_no=roll_no,
                    enrollment_no=enrollment_no,
                    mobile=mobile or None,
                    class_id=class_id_int,
                    face_encoding=face_encoding_bytes,
                    image_filename=image_filename,
                    user_id=new_user.id
                )

                db.session.add(new_student)
                db.session.commit()

                flash(
                    'Student account registered successfully! '
                    'An administrator will assign your class. You can now log in.',
                    'success'
                )
                return redirect(url_for('main.index', state='login'))
            except Exception as e:
                db.session.rollback()
                flash(f'Registration failed: {e}', 'danger')
                return redirect(url_for('main.index', state='signup'))

        else:
            flash('Invalid role selected.', 'danger')
            return redirect(url_for('main.index', state='signup'))

    # Redirect GET requests to the unified index page with state='signup'
    return redirect(url_for('main.index', state='signup'))

@auth_bp.route('/login/google')
def google_login():
    if not is_google_configured():
        flash('Google Login is not configured by the administrator.', 'warning')
        return redirect(url_for('main.index', state='login'))
    
    redirect_uri = url_for('auth.google_callback', _external=True)
    return oauth.google.authorize_redirect(redirect_uri)

@auth_bp.route('/login/google/callback')
def google_callback():
    if not is_google_configured():
        return redirect(url_for('main.index', state='login'))

    try:
        token = oauth.google.authorize_access_token()
        resp = oauth.google.get('userinfo')
        user_info = resp.json()
        email = user_info.get('email')
        name = user_info.get('name')
        google_id = user_info.get('id')

        user = User.query.filter_by(email=email).first()
        if user:
            if not user.google_id:
                user.google_id = google_id
                db.session.commit()
            login_user(user)
            flash(f'Logged in with Google as {user.name}!', 'success')
            if user.role == 'admin':
                return redirect(url_for('main.dashboard'))
            elif user.role == 'student':
                return redirect(url_for('student.dashboard'))
        else:
            session['google_signup_data'] = {
                'email': email,
                'name': name,
                'google_id': google_id
            }
            flash('Google authenticated successfully! Please complete your account details.', 'info')
            return redirect(url_for('main.index', state='google-complete'))
    except Exception as e:
        flash(f'Google OAuth failed: {str(e)}', 'danger')
        return redirect(url_for('main.index', state='login'))

@auth_bp.route('/signup/google/complete', methods=['GET', 'POST'])
def google_signup_complete():
    google_data = session.get('google_signup_data')
    if not google_data:
        flash('Session expired or invalid signup flow.', 'danger')
        return redirect(url_for('main.index', state='signup'))

    if request.method == 'POST':
        role = request.form.get('role')
        
        email = google_data['email']
        name = google_data['name']
        google_id = google_data['google_id']

        if User.query.filter_by(email=email).first():
            flash('Email already registered.', 'danger')
            return redirect(url_for('main.index', state='login'))

        new_user = User(name=name, email=email, role=role, google_id=google_id)

        if role == 'admin':
            db.session.add(new_user)
            db.session.commit()
            session.pop('google_signup_data', None)
            login_user(new_user)
            flash('Admin account created successfully with Google!', 'success')
            return redirect(url_for('main.dashboard'))

        elif role == 'student':
            mobile = request.form.get('mobile', '').strip()
            roll_no = request.form.get('roll_no')
            enrollment_no = request.form.get('enrollment_no')
            student_photo = request.files.get('student_photo')

            if not all([roll_no, enrollment_no]):
                flash('Roll Number and Enrollment Number are required.', 'danger')
                return redirect(url_for('main.index', state='google-complete'))

            if Student.query.filter_by(roll_no=roll_no).first() or Student.query.filter_by(enrollment_no=enrollment_no).first():
                flash('A student with this roll or enrollment number already exists.', 'danger')
                return redirect(url_for('main.index', state='google-complete'))

            face_encoding_bytes = None
            image_filename = None
            captured_base64 = request.form.get('captured_image_base64')

            if captured_base64 and captured_base64.strip():
                result = save_base64_image(captured_base64, roll_no, name, FACES_FOLDER)
                if result:
                    image_filename, filepath = result
                    try:
                        image = face_recognition.load_image_file(filepath)
                        encodings = face_recognition.face_encodings(image)
                        if len(encodings) == 1:
                            face_encoding_bytes = encodings[0].tobytes()
                        else:
                            flash(f'{len(encodings)} faces found in captured photo. Please capture a clear image of ONLY one face.', 'danger')
                            if os.path.exists(filepath):
                                os.remove(filepath)
                            return redirect(url_for('main.index', state='google-complete'))
                    except Exception as e:
                        db.session.rollback()
                        flash(f'An error occurred during facial scanning: {e}', 'danger')
                        if os.path.exists(filepath):
                            os.remove(filepath)
                        return redirect(url_for('main.index', state='google-complete'))
            elif student_photo and student_photo.filename:
                os.makedirs(FACES_FOLDER, exist_ok=True)
                filename = secure_filename(f"{roll_no}_{name}_{student_photo.filename}")
                filepath = os.path.join(FACES_FOLDER, filename)
                student_photo.save(filepath)

                try:
                    image = face_recognition.load_image_file(filepath)
                    encodings = face_recognition.face_encodings(image)
                    if len(encodings) == 1:
                        face_encoding_bytes = encodings[0].tobytes()
                        image_filename = filename
                    else:
                        flash(f'{len(encodings)} faces found in photo. Please use a clear image of ONLY one face.', 'danger')
                        if os.path.exists(filepath):
                            os.remove(filepath)
                        return redirect(url_for('main.index', state='google-complete'))
                except Exception as e:
                    db.session.rollback()
                    flash(f'An error occurred: {e}', 'danger')
                    if os.path.exists(filepath):
                        os.remove(filepath)
                    return redirect(url_for('main.index', state='google-complete'))

            try:
                new_user.mobile = mobile or None
                db.session.add(new_user)
                db.session.flush()

                new_student = Student(
                    name=name,
                    roll_no=roll_no,
                    enrollment_no=enrollment_no,
                    mobile=mobile or None,
                    class_id=None,  # Admin assigns class
                    face_encoding=face_encoding_bytes,
                    image_filename=image_filename,
                    user_id=new_user.id
                )
                db.session.add(new_student)
                db.session.commit()

                session.pop('google_signup_data', None)
                login_user(new_user)
                flash('Student account created successfully with Google! An admin will assign your class.', 'success')
                return redirect(url_for('student.dashboard'))
            except Exception as e:
                db.session.rollback()
                flash(f'Registration failed: {e}', 'danger')
                return redirect(url_for('main.index', state='google-complete'))

    return redirect(url_for('main.index', state='google-complete'))

# ─────────────────────────────────────────────────────────────────────────────
# FORGOT PASSWORD — OTP FLOW
# ─────────────────────────────────────────────────────────────────────────────

@auth_bp.route('/forgot_password', methods=['GET', 'POST'])
def forgot_password():
    """Step 1: User enters their email. We generate & store an OTP in session."""
    if current_user.is_authenticated:
        return redirect(url_for('auth.login'))

    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        user = User.query.filter_by(email=email).first()

        if user:
            otp = generate_otp(6)
            # Store OTP with expiry (10 minutes)
            session['otp_data'] = {
                'email': email,
                'otp': otp,
                'expires_at': (datetime.utcnow() + timedelta(minutes=10)).isoformat()
            }

            # Simulate sending OTP to email / mobile
            print("\n" + "=" * 80)
            print("[SMARTVISION OTP SYSTEM] PASSWORD RESET OTP GENERATED")
            print(f"  To    : {user.name} <{user.email}>")
            if user.mobile:
                print(f"  Mobile: {user.mobile}")
            print(f"  OTP   : {otp}  (valid for 10 minutes)")
            print("=" * 80 + "\n", flush=True)

        # Always redirect to OTP panel (don't reveal if email exists)
        return redirect(url_for('main.index', state='otp-verify', email=email))

    return redirect(url_for('main.index', state='forgot'))

@auth_bp.route('/verify_otp', methods=['POST'])
def verify_otp():
    """Step 2: User enters OTP. Validate and redirect to password reset panel."""
    entered_otp = request.form.get('otp', '').strip()
    otp_data = session.get('otp_data')

    if not otp_data:
        flash('OTP session expired. Please try again.', 'danger')
        return redirect(url_for('main.index', state='forgot'))

    # Check expiry
    expires_at = datetime.fromisoformat(otp_data['expires_at'])
    if datetime.utcnow() > expires_at:
        session.pop('otp_data', None)
        flash('OTP has expired. Please request a new one.', 'danger')
        return redirect(url_for('main.index', state='forgot'))

    if entered_otp != otp_data['otp']:
        flash('Incorrect OTP. Please try again.', 'danger')
        email = otp_data.get('email', '')
        return redirect(url_for('main.index', state='otp-verify', email=email))

    # OTP correct — mark as verified and allow password reset
    session['otp_verified_email'] = otp_data['email']
    session.pop('otp_data', None)
    return redirect(url_for('main.index', state='reset-password'))

@auth_bp.route('/reset_password_otp', methods=['POST'])
def reset_password_otp():
    """Step 3: OTP was verified — save the new password."""
    verified_email = session.get('otp_verified_email')
    if not verified_email:
        flash('Password reset session expired. Please start over.', 'danger')
        return redirect(url_for('main.index', state='forgot'))

    password = request.form.get('password', '')
    confirm_password = request.form.get('confirm_password', '')

    if len(password) < 8:
        flash('Password must be at least 8 characters long.', 'danger')
        return redirect(url_for('main.index', state='reset-password'))

    if password != confirm_password:
        flash('Passwords do not match.', 'danger')
        return redirect(url_for('main.index', state='reset-password'))

    user = User.query.filter_by(email=verified_email).first()
    if not user:
        flash('Account not found. Please register.', 'danger')
        session.pop('otp_verified_email', None)
        return redirect(url_for('main.index', state='signup'))

    user.set_password(password)
    db.session.commit()
    session.pop('otp_verified_email', None)
    flash('Your password has been successfully reset! You can now log in.', 'success')
    return redirect(url_for('main.index', state='login'))

# Legacy token-based reset (kept for backward compat with any emailed links still in use)
@auth_bp.route('/reset_password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    if current_user.is_authenticated:
        return redirect(url_for('auth.login'))

    from itsdangerous import URLSafeTimedSerializer
    s = URLSafeTimedSerializer(current_app.config['SECRET_KEY'])
    try:
        email = s.loads(token, salt='password-reset-salt', max_age=1800)
    except Exception:
        flash("The password reset link is invalid or has expired.", "danger")
        return redirect(url_for('main.index', state='login'))

    user = User.query.filter_by(email=email).first_or_404()

    if request.method == 'POST':
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')

        if password != confirm_password:
            flash("Passwords do not match.", "danger")
            return redirect(request.url)

        user.set_password(password)
        db.session.commit()
        flash("Your password has been successfully reset! You can now log in.", "success")
        return redirect(url_for('main.index', state='login'))

    return render_template('reset_password.html', email=user.email)

@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out successfully.', 'info')
    return redirect(url_for('main.index', state='login'))