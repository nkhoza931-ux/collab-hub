import os
import uuid
from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app, send_from_directory
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from extensions import db
from models import (Project, Milestone, Application, Enrollment, Notification, User,
                    ProjectFile, Message, MilestoneSubmission, SubmissionFeedback,
                    Workshop, WorkshopRegistration)

faculty_bp = Blueprint('faculty', __name__)


def faculty_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'faculty':
            flash('Access denied.', 'danger')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated


def allowed_file(filename):
    allowed = current_app.config.get('ALLOWED_EXTENSIONS', set())
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed


# ── Dashboard ──────────────────────────────────────────────────────────────────

@faculty_bp.route('/dashboard')
@login_required
@faculty_required
def dashboard():
    projects = Project.query.filter_by(faculty_id=current_user.id).all()
    project_ids = [p.id for p in projects]

    pending_apps = Application.query.filter(
        Application.project_id.in_(project_ids),
        Application.status == 'pending'
    ).all()

    total_students = Enrollment.query.filter(Enrollment.project_id.in_(project_ids)).count()

    from datetime import datetime, timedelta
    soon = (datetime.utcnow() + timedelta(days=30)).strftime('%Y-%m-%d')
    due_milestones = Milestone.query.filter(
        Milestone.project_id.in_(project_ids),
        Milestone.status != 'completed',
        Milestone.due_date <= soon
    ).count()

    # Pending submissions to review
    milestone_ids = [m.id for p in projects for m in p.milestones]
    pending_submissions = MilestoneSubmission.query.filter(
        MilestoneSubmission.milestone_id.in_(milestone_ids),
        MilestoneSubmission.status == 'submitted'
    ).count()

    my_workshops = Workshop.query.filter_by(organiser_id=current_user.id)\
        .order_by(Workshop.date.desc()).limit(3).all()

    return render_template('faculty/dashboard.html',
        projects=projects,
        pending_apps=pending_apps[:4],
        total_students=total_students,
        due_milestones=due_milestones,
        pending_submissions=pending_submissions,
        my_workshops=my_workshops
    )


# ── Post Project ───────────────────────────────────────────────────────────────

@faculty_bp.route('/post-project', methods=['GET', 'POST'])
@login_required
@faculty_required
def post_project():
    if request.method == 'POST':
        title = request.form.get('title')
        description = request.form.get('description')
        department = request.form.get('department')
        requirements = request.form.get('requirements')
        slots = int(request.form.get('slots', 4))
        deadline = request.form.get('deadline')
        end_date = request.form.get('end_date')

        project = Project(
            title=title, description=description,
            department=department, requirements=requirements,
            slots=slots, deadline=deadline, end_date=end_date,
            faculty_id=current_user.id
        )
        db.session.add(project)
        db.session.flush()

        m_titles = request.form.getlist('milestone_title[]')
        m_dates = request.form.getlist('milestone_date[]')
        for t, d in zip(m_titles, m_dates):
            if t.strip():
                db.session.add(Milestone(title=t.strip(), due_date=d, project_id=project.id))

        students = User.query.filter_by(role='student').all()
        from email_utils import send_new_project_notification
        for s in students:
            db.session.add(Notification(message=f'New project posted: {title}', user_id=s.id))
            send_new_project_notification(s, project)

        db.session.commit()
        flash(f'Project "{title}" published successfully!', 'success')
        return redirect(url_for('faculty.my_projects'))

    return render_template('faculty/post_project.html')


# ── My Projects ────────────────────────────────────────────────────────────────

@faculty_bp.route('/my-projects')
@login_required
@faculty_required
def my_projects():
    projects = Project.query.filter_by(faculty_id=current_user.id)\
        .order_by(Project.created_at.desc()).all()
    return render_template('faculty/my_projects.html', projects=projects)


# ── Project Detail ─────────────────────────────────────────────────────────────

@faculty_bp.route('/project/<int:project_id>')
@login_required
@faculty_required
def project_detail(project_id):
    project = Project.query.get_or_404(project_id)
    enrollments = Enrollment.query.filter_by(project_id=project_id).all()
    milestones = Milestone.query.filter_by(project_id=project_id).order_by(Milestone.due_date).all()
    files = ProjectFile.query.filter_by(project_id=project_id).order_by(ProjectFile.uploaded_at.desc()).all()
    messages = Message.query.filter_by(project_id=project_id).order_by(Message.sent_at.asc()).all()

    # Gather all submissions for this project's milestones
    milestone_ids = [m.id for m in milestones]
    submissions = MilestoneSubmission.query.filter(
        MilestoneSubmission.milestone_id.in_(milestone_ids)
    ).order_by(MilestoneSubmission.submitted_at.desc()).all()

    return render_template('faculty/project_detail.html',
        project=project, enrollments=enrollments,
        milestones=milestones, files=files,
        messages=messages, submissions=submissions
    )


# ── Close Project / Record Outcome ────────────────────────────────────────────

@faculty_bp.route('/project/<int:project_id>/close', methods=['POST'])
@login_required
@faculty_required
def close_project(project_id):
    project = Project.query.get_or_404(project_id)
    final_outcome = request.form.get('final_outcome', '').strip()
    project.status = 'closed'
    project.final_outcome = final_outcome
    db.session.commit()
    flash('Project closed and outcome recorded.', 'success')
    return redirect(url_for('faculty.project_detail', project_id=project_id))


# ── Applications ───────────────────────────────────────────────────────────────

@faculty_bp.route('/applications')
@login_required
@faculty_required
def applications():
    projects = Project.query.filter_by(faculty_id=current_user.id).all()
    project_ids = [p.id for p in projects]
    apps = Application.query.filter(
        Application.project_id.in_(project_ids)
    ).order_by(Application.created_at.desc()).all()
    return render_template('faculty/applications.html', applications=apps)


@faculty_bp.route('/application/<int:app_id>/<action>')
@login_required
@faculty_required
def handle_application(app_id, action):
    application = Application.query.get_or_404(app_id)
    from email_utils import send_application_approved, send_application_rejected

    if action == 'approve':
        application.status = 'approved'
        enrollment = Enrollment(student_id=application.student_id, project_id=application.project_id)
        db.session.add(enrollment)
        db.session.add(Notification(
            message=f'Your application to "{application.project.title}" has been approved!',
            user_id=application.student_id
        ))
        send_application_approved(application.student, application.project)
        flash('Application approved and student enrolled.', 'success')
    elif action == 'reject':
        application.status = 'rejected'
        db.session.add(Notification(
            message=f'Your application to "{application.project.title}" was not accepted this time.',
            user_id=application.student_id
        ))
        send_application_rejected(application.student, application.project)
        flash('Application rejected.', 'info')

    db.session.commit()
    return redirect(url_for('faculty.applications'))


# ── Milestones ─────────────────────────────────────────────────────────────────

@faculty_bp.route('/milestone/<int:milestone_id>/update', methods=['POST'])
@login_required
@faculty_required
def update_milestone(milestone_id):
    milestone = Milestone.query.get_or_404(milestone_id)
    milestone.status = request.form.get('status', milestone.status)
    db.session.commit()
    flash('Milestone updated.', 'success')
    return redirect(url_for('faculty.project_detail', project_id=milestone.project_id))


# ── Submissions & Feedback ─────────────────────────────────────────────────────

@faculty_bp.route('/submissions')
@login_required
@faculty_required
def submissions():
    """View all student milestone submissions across all faculty's projects."""
    projects = Project.query.filter_by(faculty_id=current_user.id).all()
    milestone_ids = [m.id for p in projects for m in p.milestones]
    all_submissions = MilestoneSubmission.query.filter(
        MilestoneSubmission.milestone_id.in_(milestone_ids)
    ).order_by(MilestoneSubmission.submitted_at.desc()).all()
    return render_template('faculty/submissions.html', submissions=all_submissions)


@faculty_bp.route('/submission/<int:submission_id>')
@login_required
@faculty_required
def view_submission(submission_id):
    sub = MilestoneSubmission.query.get_or_404(submission_id)
    return render_template('faculty/view_submission.html', sub=sub)


@faculty_bp.route('/submission/<int:submission_id>/feedback', methods=['POST'])
@login_required
@faculty_required
def give_feedback(submission_id):
    sub = MilestoneSubmission.query.get_or_404(submission_id)
    comment = request.form.get('comment', '').strip()
    grade = request.form.get('grade', '').strip()

    if not comment:
        flash('Feedback comment cannot be empty.', 'warning')
        return redirect(url_for('faculty.view_submission', submission_id=submission_id))

    if sub.feedback:
        sub.feedback.comment = comment
        sub.feedback.grade = grade
    else:
        feedback = SubmissionFeedback(
            comment=comment, grade=grade,
            submission_id=submission_id,
            faculty_id=current_user.id
        )
        db.session.add(feedback)

    sub.status = 'reviewed'

    # Auto-complete the milestone when faculty reviews the submission
    if sub.milestone.status != 'completed':
        sub.milestone.status = 'completed'

    db.session.add(Notification(
        message=f'Your submission for "{sub.milestone.title}" has been reviewed. Check your feedback!',
        user_id=sub.student_id
    ))
    db.session.commit()
    flash('Feedback submitted successfully.', 'success')
    return redirect(url_for('faculty.submissions'))


@faculty_bp.route('/submission/<int:submission_id>/download')
@login_required
@faculty_required
def download_submission(submission_id):
    sub = MilestoneSubmission.query.get_or_404(submission_id)
    return send_from_directory(
        current_app.config['UPLOAD_FOLDER'],
        sub.stored_name, as_attachment=True, download_name=sub.filename
    )


# ── File Upload/Download ───────────────────────────────────────────────────────

@faculty_bp.route('/project/<int:project_id>/upload', methods=['POST'])
@login_required
@faculty_required
def upload_file(project_id):
    project = Project.query.get_or_404(project_id)
    if 'file' not in request.files or request.files['file'].filename == '':
        flash('No file selected.', 'warning')
        return redirect(url_for('faculty.project_detail', project_id=project_id))

    f = request.files['file']
    if not allowed_file(f.filename):
        flash('File type not allowed.', 'danger')
        return redirect(url_for('faculty.project_detail', project_id=project_id))

    original_name = secure_filename(f.filename)
    ext = original_name.rsplit('.', 1)[1].lower()
    stored_name = f"{uuid.uuid4().hex}.{ext}"
    save_path = os.path.join(current_app.config['UPLOAD_FOLDER'], stored_name)
    f.save(save_path)

    pf = ProjectFile(filename=original_name, stored_name=stored_name,
                     file_size=os.path.getsize(save_path), mime_type=f.content_type,
                     project_id=project_id, uploader_id=current_user.id)
    db.session.add(pf)
    db.session.commit()
    flash(f'"{original_name}" uploaded.', 'success')
    return redirect(url_for('faculty.project_detail', project_id=project_id))


@faculty_bp.route('/file/<int:file_id>/delete', methods=['POST'])
@login_required
@faculty_required
def delete_file(file_id):
    pf = ProjectFile.query.get_or_404(file_id)
    project_id = pf.project_id
    try:
        os.remove(os.path.join(current_app.config['UPLOAD_FOLDER'], pf.stored_name))
    except OSError:
        pass
    db.session.delete(pf)
    db.session.commit()
    flash('File deleted.', 'info')
    return redirect(url_for('faculty.project_detail', project_id=project_id))


@faculty_bp.route('/download/<int:file_id>')
@login_required
def download_file(file_id):
    pf = ProjectFile.query.get_or_404(file_id)
    return send_from_directory(
        current_app.config['UPLOAD_FOLDER'],
        pf.stored_name, as_attachment=True, download_name=pf.filename
    )


# ── Delete Project ─────────────────────────────────────────────────────────────

@faculty_bp.route('/project/<int:project_id>/delete', methods=['POST'])
@login_required
@faculty_required
def delete_project(project_id):
    project = Project.query.get_or_404(project_id)
    db.session.delete(project)
    db.session.commit()
    flash('Project deleted.', 'info')
    return redirect(url_for('faculty.my_projects'))


# ── Chat ───────────────────────────────────────────────────────────────────────

@faculty_bp.route('/project/<int:project_id>/chat', methods=['POST'])
@login_required
@faculty_required
def send_message(project_id):
    project = Project.query.get_or_404(project_id)
    body = request.form.get('body', '').strip()
    if not body:
        flash('Message cannot be empty.', 'warning')
        return redirect(url_for('faculty.project_detail', project_id=project_id))

    msg = Message(body=body, sender_id=current_user.id, project_id=project_id)
    db.session.add(msg)
    from email_utils import send_new_message_notification
    enrollments = Enrollment.query.filter_by(project_id=project_id).all()
    for e in enrollments:
        if e.student_id != current_user.id:
            send_new_message_notification(e.student, current_user, project)
    db.session.commit()
    return redirect(url_for('faculty.project_detail', project_id=project_id))


# ── Workshops ──────────────────────────────────────────────────────────────────

@faculty_bp.route('/workshops')
@login_required
@faculty_required
def workshops():
    my_workshops = Workshop.query.filter_by(organiser_id=current_user.id)\
        .order_by(Workshop.date.desc()).all()
    return render_template('faculty/workshops.html', workshops=my_workshops)


@faculty_bp.route('/workshops/create', methods=['GET', 'POST'])
@login_required
@faculty_required
def create_workshop():
    projects = Project.query.filter_by(faculty_id=current_user.id).all()
    if request.method == 'POST':
        title = request.form.get('title')
        description = request.form.get('description')
        date = request.form.get('date')
        time = request.form.get('time')
        duration_mins = int(request.form.get('duration_mins', 60))
        is_online = request.form.get('is_online') == 'on'
        location = request.form.get('location', '')
        meeting_link = request.form.get('meeting_link', '')
        max_participants = int(request.form.get('max_participants', 30))
        project_id = request.form.get('project_id') or None

        workshop = Workshop(
            title=title, description=description,
            date=date, time=time, duration_mins=duration_mins,
            is_online=is_online, location=location,
            meeting_link=meeting_link, max_participants=max_participants,
            project_id=project_id, organiser_id=current_user.id
        )
        db.session.add(workshop)
        db.session.flush()

        # Notify all students
        students = User.query.filter_by(role='student').all()
        for s in students:
            db.session.add(Notification(
                message=f'New workshop scheduled: "{title}" on {date} at {time}',
                user_id=s.id
            ))
        db.session.commit()
        flash(f'Workshop "{title}" created!', 'success')
        return redirect(url_for('faculty.workshops'))

    return render_template('faculty/create_workshop.html', projects=projects)


@faculty_bp.route('/workshop/<int:workshop_id>/delete', methods=['POST'])
@login_required
@faculty_required
def delete_workshop(workshop_id):
    workshop = Workshop.query.get_or_404(workshop_id)
    db.session.delete(workshop)
    db.session.commit()
    flash('Workshop deleted.', 'info')
    return redirect(url_for('faculty.workshops'))


@faculty_bp.route('/workshop/<int:workshop_id>/attendance', methods=['GET', 'POST'])
@login_required
@faculty_required
def mark_attendance(workshop_id):
    workshop = Workshop.query.get_or_404(workshop_id)
    registrations = WorkshopRegistration.query.filter_by(workshop_id=workshop_id).all()
    if request.method == 'POST':
        attended_ids = set(map(int, request.form.getlist('attended')))
        for reg in registrations:
            reg.attended = reg.user_id in attended_ids
        db.session.commit()
        flash('Attendance saved.', 'success')
        return redirect(url_for('faculty.workshops'))
    return render_template('faculty/mark_attendance.html', workshop=workshop, registrations=registrations)


# ── Report ─────────────────────────────────────────────────────────────────────

@faculty_bp.route('/report')
@login_required
@faculty_required
def report():
    projects = Project.query.filter_by(faculty_id=current_user.id).all()
    total_students = sum(p.filled_slots for p in projects)
    total_milestones = sum(len(p.milestones) for p in projects)
    completed_milestones = sum(
        sum(1 for m in p.milestones if m.status == 'completed') for p in projects
    )
    milestone_ids = [m.id for p in projects for m in p.milestones]
    total_submissions = MilestoneSubmission.query.filter(
        MilestoneSubmission.milestone_id.in_(milestone_ids)
    ).count()
    my_workshops = Workshop.query.filter_by(organiser_id=current_user.id).all()

    return render_template('faculty/report.html',
        projects=projects,
        total_students=total_students,
        total_milestones=total_milestones,
        completed_milestones=completed_milestones,
        total_submissions=total_submissions,
        my_workshops=my_workshops
    )
