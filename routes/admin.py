from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from extensions import db
from models import User, Project, Application, Enrollment, MilestoneSubmission, Workshop, WorkshopRegistration

admin_bp = Blueprint('admin', __name__)


def admin_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'admin':
            flash('Access denied.', 'danger')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated


@admin_bp.route('/dashboard')
@login_required
@admin_required
def dashboard():
    total_users = User.query.count()
    total_students = User.query.filter_by(role='student').count()
    total_faculty = User.query.filter_by(role='faculty').count()
    total_projects = Project.query.count()
    active_projects = Project.query.filter_by(status='open').count()
    closed_projects = Project.query.filter_by(status='closed').count()
    total_apps = Application.query.count()
    total_workshops = Workshop.query.count()

    recent_users = User.query.order_by(User.created_at.desc()).limit(5).all()
    recent_projects = Project.query.order_by(Project.created_at.desc()).limit(5).all()

    return render_template('admin/dashboard.html',
        total_users=total_users, total_students=total_students,
        total_faculty=total_faculty, total_projects=total_projects,
        active_projects=active_projects, closed_projects=closed_projects,
        total_apps=total_apps, total_workshops=total_workshops,
        recent_users=recent_users, recent_projects=recent_projects
    )


@admin_bp.route('/users')
@login_required
@admin_required
def users():
    role_filter = request.args.get('role', 'all')
    if role_filter != 'all':
        all_users = User.query.filter_by(role=role_filter).order_by(User.created_at.desc()).all()
    else:
        all_users = User.query.order_by(User.created_at.desc()).all()
    return render_template('admin/users.html', users=all_users, role_filter=role_filter)


@admin_bp.route('/user/<int:user_id>/toggle')
@login_required
@admin_required
def toggle_user(user_id):
    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        flash("You cannot deactivate your own account.", 'danger')
    else:
        user.is_active_account = not user.is_active_account
        db.session.commit()
        status = 'activated' if user.is_active_account else 'suspended'
        flash(f'User {user.name} has been {status}.', 'info')
    return redirect(url_for('admin.users'))


@admin_bp.route('/projects')
@login_required
@admin_required
def projects():
    search = request.args.get('search', '').strip()
    dept_filter = request.args.get('dept', 'All')
    status_filter = request.args.get('status', 'all')

    query = Project.query
    if search:
        query = query.filter(
            db.or_(Project.title.ilike(f'%{search}%'), Project.description.ilike(f'%{search}%'))
        )
    if dept_filter and dept_filter != 'All':
        query = query.filter_by(department=dept_filter)
    if status_filter and status_filter != 'all':
        query = query.filter_by(status=status_filter)

    all_projects = query.order_by(Project.created_at.desc()).all()
    departments = ['All'] + [d[0] for d in db.session.query(Project.department).distinct().all()]

    return render_template('admin/projects.html',
        projects=all_projects, departments=departments,
        dept_filter=dept_filter, status_filter=status_filter, search=search
    )


@admin_bp.route('/project/<int:project_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_project(project_id):
    project = Project.query.get_or_404(project_id)
    db.session.delete(project)
    db.session.commit()
    flash('Project removed.', 'info')
    return redirect(url_for('admin.projects'))


@admin_bp.route('/workshops')
@login_required
@admin_required
def workshops():
    all_workshops = Workshop.query.order_by(Workshop.date.desc()).all()
    return render_template('admin/workshops.html', workshops=all_workshops)


@admin_bp.route('/report')
@login_required
@admin_required
def report():
    projects = Project.query.all()
    closed_projects = [p for p in projects if p.status == 'closed']
    total_submissions = MilestoneSubmission.query.count()
    total_workshops = Workshop.query.count()
    total_registrations = WorkshopRegistration.query.count()
    total_attended = WorkshopRegistration.query.filter_by(attended=True).count()

    # Per-department breakdown
    departments = db.session.query(Project.department).distinct().all()
    dept_stats = []
    for (dept,) in departments:
        dept_projects = Project.query.filter_by(department=dept).all()
        dept_students = sum(p.filled_slots for p in dept_projects)
        dept_stats.append({
            'name': dept,
            'projects': len(dept_projects),
            'students': dept_students,
            'closed': sum(1 for p in dept_projects if p.status == 'closed')
        })

    return render_template('admin/report.html',
        projects=projects,
        closed_projects=closed_projects,
        total_submissions=total_submissions,
        total_workshops=total_workshops,
        total_registrations=total_registrations,
        total_attended=total_attended,
        dept_stats=dept_stats
    )
