from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import check_password_hash, generate_password_hash
from extensions import db
from models import User

auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for(f'{current_user.role}.dashboard'))
    return redirect(url_for('auth.login'))


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for(f'{current_user.role}.dashboard'))

    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '').strip()
        user = User.query.filter_by(email=email).first()

        if user and check_password_hash(user.password, password):
            if not user.is_active_account:
                flash('Your account has been suspended. Please contact admin.', 'danger')
                return redirect(url_for('auth.login'))
            login_user(user)
            flash(f'Welcome back, {user.name}!', 'success')
            return redirect(url_for(f'{user.role}.dashboard'))
        else:
            flash('Invalid email or password. Please try again.', 'danger')

    return render_template('auth/login.html')


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '').strip()
        role = request.form.get('role', '').strip()
        department = request.form.get('department', '').strip()

        # Server-side validation (defence against bypassed JS validation)
        if not name or not email or not password or not role or not department:
            flash('All fields are required.', 'danger')
            return redirect(url_for('auth.register'))

        if len(password) < 6:
            flash('Password must be at least 6 characters.', 'danger')
            return redirect(url_for('auth.register'))

        if User.query.filter_by(email=email).first():
            flash('Email already registered. Please log in.', 'danger')
            return redirect(url_for('auth.register'))

        user = User(
            name=name, email=email,
            password=generate_password_hash(password),
            role=role, department=department
        )
        db.session.add(user)
        db.session.commit()
        login_user(user)

        from email_utils import send_welcome_email
        send_welcome_email(user)

        flash(f'Account created! Welcome, {name}.', 'success')
        return redirect(url_for(f'{user.role}.dashboard'))

    return render_template('auth/register.html')


@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('auth.login'))


@auth_bp.route('/privacy')
def privacy():
    return render_template('auth/privacy.html')
