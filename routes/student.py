import os
from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app, send_from_directory
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from extensions import db
from models import Project, Application, Enrollment, Milestone, Notification, ProjectFile, Message, MilestoneSubmission, Workshop, WorkshopRegistration
import uuid

student_bp = Blueprint('student', __name__)


def student_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'student':
            flash('Access denied.', 'danger')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated


def allowed_file(filename):
    allowed = current_app.config.get('ALLOWED_EXTENSIONS', set())
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed


# ── Dashboard ──────────────────────────────────────────────────────────────────

@student_bp.route('/dashboard')
@login_required
@student_required
def dashboard():
    enrollments = Enrollment.query.filter_by(student_id=current_user.id).all()
    enrolled_project_ids = [e.project_id for e in enrollments]
    projects = Project.query.filter(Project.id.in_(enrolled_project_ids)).all()

    pending_applications = Application.query.filter_by(
        student_id=current_user.id, status='pending'
    ).count()

    notifications = Notification.query.filter_by(
        user_id=current_user.id, is_read=False
    ).order_by(Notification.created_at.desc()).limit(5).all()

    milestones = []
    for p in projects:
        milestones.extend(p.milestones)
    upcoming_deadlines = [m for m in milestones if m.status != 'completed']

    # Upcoming workshops
    from datetime import date
    today = date.today().strftime('%Y-%m-%d')
    my_workshop_ids = [r.workshop_id for r in WorkshopRegistration.query.filter_by(user_id=current_user.id).all()]
    upcoming_workshops = Workshop.query.filter(
        Workshop.date >= today
    ).order_by(Workshop.date.asc()).limit(3).all()

    return render_template('student/dashboard.html',
        projects=projects,
        enrollments=enrollments,
        pending_applications=pending_applications,
        notifications=notifications,
        milestones=milestones[:5],
        upcoming_count=len(upcoming_deadlines),
        upcoming_workshops=upcoming_workshops,
        my_workshop_ids=my_workshop_ids
    )


# ── Browse ─────────────────────────────────────────────────────────────────────

@student_bp.route('/browse')
@login_required
@student_required
def browse():
    dept_filter = request.args.get('dept', 'All')
    search = request.args.get('search', '').strip()
    status_filter = request.args.get('status', 'open')
    sort_by = request.args.get('sort', 'newest')

    query = Project.query
    if status_filter and status_filter != 'all':
        query = query.filter_by(status=status_filter)
    if dept_filter and dept_filter != 'All':
        query = query.filter_by(department=dept_filter)
    if search:
        query = query.filter(
            db.or_(
                Project.title.ilike(f'%{search}%'),
                Project.description.ilike(f'%{search}%'),
                Project.requirements.ilike(f'%{search}%')
            )
        )
    if sort_by == 'deadline':
        query = query.order_by(Project.deadline.asc())
    elif sort_by == 'slots':
        query = query.order_by(Project.slots.desc())
    else:
        query = query.order_by(Project.created_at.desc())

    projects = query.all()
    departments = ['All'] + [d[0] for d in db.session.query(Project.department).distinct().all()]
    my_apps = {a.project_id for a in Application.query.filter_by(student_id=current_user.id).all()}
    my_enrollments = {e.project_id for e in Enrollment.query.filter_by(student_id=current_user.id).all()}

    return render_template('student/browse.html',
        projects=projects, departments=departments,
        dept_filter=dept_filter, search=search,
        status_filter=status_filter, sort_by=sort_by,
        my_apps=my_apps, my_enrollments=my_enrollments
    )


# ── Apply ──────────────────────────────────────────────────────────────────────

@student_bp.route('/apply/<int:project_id>', methods=['GET', 'POST'])
@login_required
@student_required
def apply(project_id):
    project = Project.query.get_or_404(project_id)
    existing = Application.query.filter_by(student_id=current_user.id, project_id=project_id).first()
    if existing:
        flash('You have already applied to this project.', 'warning')
        return redirect(url_for('student.browse'))

    if request.method == 'POST':
        motivation = request.form.get('motivation', '').strip()
        app_obj = Application(student_id=current_user.id, project_id=project_id, motivation=motivation)
        db.session.add(app_obj)
        db.session.commit()
        from email_utils import send_application_received
        send_application_received(current_user, project)
        flash(f'Application submitted for "{project.title}"!', 'success')
        return redirect(url_for('student.browse'))

    return render_template('student/apply.html', project=project)


# ── My Projects ────────────────────────────────────────────────────────────────

@student_bp.route('/my-projects')
@login_required
@student_required
def my_projects():
    enrollments = Enrollment.query.filter_by(student_id=current_user.id).all()
    applications = Application.query.filter_by(student_id=current_user.id).all()
    return render_template('student/my_projects.html', enrollments=enrollments, applications=applications)


# ── Milestones ─────────────────────────────────────────────────────────────────

@student_bp.route('/milestones')
@login_required
@student_required
def milestones():
    enrollments = Enrollment.query.filter_by(student_id=current_user.id).all()
    project_ids = [e.project_id for e in enrollments]
    all_milestones = Milestone.query.filter(
        Milestone.project_id.in_(project_ids)
    ).order_by(Milestone.due_date).all()
    # Get student's existing submissions
    my_submission_ids = {s.milestone_id for s in MilestoneSubmission.query.filter_by(student_id=current_user.id).all()}
    return render_template('student/milestones.html', milestones=all_milestones, my_submission_ids=my_submission_ids)


# ── Milestone Submission ───────────────────────────────────────────────────────

@student_bp.route('/milestone/<int:milestone_id>/submit', methods=['GET', 'POST'])
@login_required
@student_required
def submit_milestone(milestone_id):
    milestone = Milestone.query.get_or_404(milestone_id)
    # Verify student is enrolled in the project
    enrollment = Enrollment.query.filter_by(
        student_id=current_user.id, project_id=milestone.project_id
    ).first()
    if not enrollment:
        flash('You are not enrolled in this project.', 'danger')
        return redirect(url_for('student.milestones'))

    existing = MilestoneSubmission.query.filter_by(
        milestone_id=milestone_id, student_id=current_user.id
    ).first()

    if request.method == 'POST':
        notes = request.form.get('notes', '').strip()
        file = request.files.get('file')

        if not file or file.filename == '':
            flash('Please select a file to submit.', 'warning')
            return redirect(request.url)

        if not allowed_file(file.filename):
            flash('File type not allowed.', 'danger')
            return redirect(request.url)

        original_name = secure_filename(file.filename)
        ext = original_name.rsplit('.', 1)[1].lower()
        stored_name = f"{uuid.uuid4().hex}.{ext}"
        save_path = os.path.join(current_app.config['UPLOAD_FOLDER'], stored_name)
        file.save(save_path)

        if existing:
            # Replace old submission
            try:
                os.remove(os.path.join(current_app.config['UPLOAD_FOLDER'], existing.stored_name))
            except OSError:
                pass
            existing.filename = original_name
            existing.stored_name = stored_name
            existing.file_size = os.path.getsize(save_path)
            existing.notes = notes
            existing.status = 'submitted'
            existing.submitted_at = db.func.now()
        else:
            sub = MilestoneSubmission(
                filename=original_name,
                stored_name=stored_name,
                file_size=os.path.getsize(save_path),
                notes=notes,
                milestone_id=milestone_id,
                student_id=current_user.id
            )
            db.session.add(sub)

        # Auto-update milestone status: pending → in_progress on first submission
        if milestone.status == 'pending':
            milestone.status = 'in_progress'

        # Notify faculty
        db.session.add(Notification(
            message=f'{current_user.name} submitted proof for milestone: "{milestone.title}"',
            user_id=milestone.project.faculty_id
        ))
        db.session.commit()
        flash('Submission uploaded successfully! Milestone marked as In Progress.', 'success')
        return redirect(url_for('student.milestones'))

    return render_template('student/submit_milestone.html', milestone=milestone, existing=existing)


@student_bp.route('/submission/<int:submission_id>/download')
@login_required
def download_submission(submission_id):
    sub = MilestoneSubmission.query.get_or_404(submission_id)
    # Only the student who submitted or faculty of the project can download
    if sub.student_id != current_user.id and current_user.role not in ['faculty', 'admin']:
        flash('Access denied.', 'danger')
        return redirect(url_for('student.milestones'))
    return send_from_directory(
        current_app.config['UPLOAD_FOLDER'],
        sub.stored_name,
        as_attachment=True,
        download_name=sub.filename
    )


# ── Notifications ──────────────────────────────────────────────────────────────

@student_bp.route('/notifications')
@login_required
@student_required
def notifications():
    notifs = Notification.query.filter_by(user_id=current_user.id)\
        .order_by(Notification.created_at.desc()).all()
    for n in notifs:
        n.is_read = True
    db.session.commit()
    return render_template('student/notifications.html', notifications=notifs)


# ── Project Detail ─────────────────────────────────────────────────────────────

@student_bp.route('/project/<int:project_id>')
@login_required
@student_required
def project_detail(project_id):
    project = Project.query.get_or_404(project_id)
    enrollment = Enrollment.query.filter_by(student_id=current_user.id, project_id=project_id).first()
    if not enrollment:
        flash('You are not enrolled in this project.', 'danger')
        return redirect(url_for('student.browse'))

    files = ProjectFile.query.filter_by(project_id=project_id).order_by(ProjectFile.uploaded_at.desc()).all()
    messages = Message.query.filter_by(project_id=project_id).order_by(Message.sent_at.asc()).all()
    milestones = Milestone.query.filter_by(project_id=project_id).order_by(Milestone.due_date).all()
    my_submissions = {s.milestone_id: s for s in MilestoneSubmission.query.filter_by(student_id=current_user.id).all()}

    return render_template('student/project_detail.html',
        project=project, enrollment=enrollment,
        files=files, messages=messages,
        milestones=milestones, my_submissions=my_submissions
    )


# ── File Download ──────────────────────────────────────────────────────────────

@student_bp.route('/download/<int:file_id>')
@login_required
@student_required
def download_file(file_id):
    pf = ProjectFile.query.get_or_404(file_id)
    enrollment = Enrollment.query.filter_by(student_id=current_user.id, project_id=pf.project_id).first()
    if not enrollment:
        flash('Access denied.', 'danger')
        return redirect(url_for('student.browse'))
    return send_from_directory(
        current_app.config['UPLOAD_FOLDER'],
        pf.stored_name, as_attachment=True, download_name=pf.filename
    )


# ── Chat ───────────────────────────────────────────────────────────────────────

@student_bp.route('/project/<int:project_id>/chat', methods=['POST'])
@login_required
@student_required
def send_message(project_id):
    project = Project.query.get_or_404(project_id)
    enrollment = Enrollment.query.filter_by(student_id=current_user.id, project_id=project_id).first()
    if not enrollment:
        flash('You are not enrolled in this project.', 'danger')
        return redirect(url_for('student.browse'))

    body = request.form.get('body', '').strip()
    if not body:
        flash('Message cannot be empty.', 'warning')
        return redirect(url_for('student.project_detail', project_id=project_id))

    msg = Message(body=body, sender_id=current_user.id, project_id=project_id)
    db.session.add(msg)
    from email_utils import send_new_message_notification
    send_new_message_notification(project.faculty, current_user, project)
    db.session.commit()
    return redirect(url_for('student.project_detail', project_id=project_id))


# ── Workshops ──────────────────────────────────────────────────────────────────

@student_bp.route('/workshops')
@login_required
@student_required
def workshops():
    from datetime import date
    today = date.today().strftime('%Y-%m-%d')
    upcoming = Workshop.query.filter(Workshop.date >= today).order_by(Workshop.date.asc()).all()
    past = Workshop.query.filter(Workshop.date < today).order_by(Workshop.date.desc()).all()
    my_reg_ids = {r.workshop_id for r in WorkshopRegistration.query.filter_by(user_id=current_user.id).all()}
    return render_template('student/workshops.html', upcoming=upcoming, past=past, my_reg_ids=my_reg_ids)


@student_bp.route('/workshop/<int:workshop_id>/register', methods=['POST'])
@login_required
@student_required
def register_workshop(workshop_id):
    workshop = Workshop.query.get_or_404(workshop_id)
    existing = WorkshopRegistration.query.filter_by(workshop_id=workshop_id, user_id=current_user.id).first()
    if existing:
        flash('You are already registered for this workshop.', 'warning')
        return redirect(url_for('student.workshops'))
    if workshop.participant_count >= workshop.max_participants:
        flash('This workshop is fully booked.', 'danger')
        return redirect(url_for('student.workshops'))

    reg = WorkshopRegistration(workshop_id=workshop_id, user_id=current_user.id)
    db.session.add(reg)
    db.session.add(Notification(
        message=f'You are registered for workshop: "{workshop.title}" on {workshop.date}',
        user_id=current_user.id
    ))
    db.session.commit()
    flash(f'Registered for "{workshop.title}"!', 'success')
    return redirect(url_for('student.workshops'))


@student_bp.route('/workshop/<int:workshop_id>/unregister', methods=['POST'])
@login_required
@student_required
def unregister_workshop(workshop_id):
    reg = WorkshopRegistration.query.filter_by(workshop_id=workshop_id, user_id=current_user.id).first()
    if reg:
        db.session.delete(reg)
        db.session.commit()
        flash('Unregistered from workshop.', 'info')
    return redirect(url_for('student.workshops'))


# ── Report ─────────────────────────────────────────────────────────────────────

@student_bp.route('/report')
@login_required
@student_required
def report():
    enrollments = Enrollment.query.filter_by(student_id=current_user.id).all()
    project_ids = [e.project_id for e in enrollments]
    projects = Project.query.filter(Project.id.in_(project_ids)).all()
    submissions = MilestoneSubmission.query.filter_by(student_id=current_user.id).all()
    workshops_attended = WorkshopRegistration.query.filter_by(user_id=current_user.id, attended=True).all()
    return render_template('student/report.html',
        projects=projects, submissions=submissions,
        workshops_attended=workshops_attended
    )
