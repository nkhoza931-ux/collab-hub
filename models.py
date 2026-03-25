from extensions import db
from flask_login import UserMixin
from datetime import datetime


class User(UserMixin, db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(20), nullable=False)
    department = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_active_account = db.Column(db.Boolean, default=True)

    projects_created = db.relationship('Project', backref='faculty', lazy=True, foreign_keys='Project.faculty_id')
    applications = db.relationship('Application', backref='student', lazy=True, foreign_keys='Application.student_id')
    notifications = db.relationship('Notification', backref='user', lazy=True)
    enrollments = db.relationship('Enrollment', backref='student', lazy=True)
    sent_messages = db.relationship('Message', backref='sender', lazy=True, foreign_keys='Message.sender_id')
    submissions = db.relationship('MilestoneSubmission', backref='student', lazy=True, foreign_keys='MilestoneSubmission.student_id')
    workshop_registrations = db.relationship('WorkshopRegistration', backref='user', lazy=True)

    def __repr__(self):
        return f'<User {self.name} ({self.role})>'


class Project(db.Model):
    __tablename__ = 'projects'

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=False)
    department = db.Column(db.String(100), nullable=False)
    requirements = db.Column(db.Text)
    slots = db.Column(db.Integer, default=4)
    deadline = db.Column(db.String(20))
    end_date = db.Column(db.String(20))
    status = db.Column(db.String(20), default='open')
    progress = db.Column(db.Integer, default=0)
    final_outcome = db.Column(db.Text)  # recorded when project is closed
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    faculty_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

    milestones = db.relationship('Milestone', backref='project', lazy=True, cascade='all, delete-orphan')
    applications = db.relationship('Application', backref='project', lazy=True, cascade='all, delete-orphan')
    enrollments = db.relationship('Enrollment', backref='project', lazy=True, cascade='all, delete-orphan')
    files = db.relationship('ProjectFile', backref='project', lazy=True, cascade='all, delete-orphan')
    messages = db.relationship('Message', backref='project', lazy=True, cascade='all, delete-orphan')

    @property
    def filled_slots(self):
        return Enrollment.query.filter_by(project_id=self.id).count()

    @property
    def tags(self):
        return [r.strip() for r in (self.requirements or '').split(',')][:3]

    @property
    def completion_percentage(self):
        if not self.milestones:
            return 0
        completed = sum(1 for m in self.milestones if m.status == 'completed')
        return int((completed / len(self.milestones)) * 100)

    def __repr__(self):
        return f'<Project {self.title}>'


class Milestone(db.Model):
    __tablename__ = 'milestones'

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    due_date = db.Column(db.String(20))
    status = db.Column(db.String(20), default='pending')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False)
    submissions = db.relationship('MilestoneSubmission', backref='milestone', lazy=True, cascade='all, delete-orphan')

    def __repr__(self):
        return f'<Milestone {self.title}>'


class Application(db.Model):
    __tablename__ = 'applications'

    id = db.Column(db.Integer, primary_key=True)
    motivation = db.Column(db.Text)
    status = db.Column(db.String(20), default='pending')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    student_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False)

    def __repr__(self):
        return f'<Application student={self.student_id} project={self.project_id}>'


class Enrollment(db.Model):
    __tablename__ = 'enrollments'

    id = db.Column(db.Integer, primary_key=True)
    enrolled_at = db.Column(db.DateTime, default=datetime.utcnow)
    task = db.Column(db.String(200))
    task_progress = db.Column(db.Integer, default=0)

    student_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False)

    def __repr__(self):
        return f'<Enrollment student={self.student_id} project={self.project_id}>'


class Notification(db.Model):
    __tablename__ = 'notifications'

    id = db.Column(db.Integer, primary_key=True)
    message = db.Column(db.Text, nullable=False)
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

    def __repr__(self):
        return f'<Notification user={self.user_id}>'


class ProjectFile(db.Model):
    __tablename__ = 'project_files'

    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255), nullable=False)
    stored_name = db.Column(db.String(255), nullable=False)
    file_size = db.Column(db.Integer)
    mime_type = db.Column(db.String(100))
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)

    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False)
    uploader_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    uploader = db.relationship('User', backref='uploaded_files')

    def __repr__(self):
        return f'<ProjectFile {self.filename}>'


class Message(db.Model):
    __tablename__ = 'messages'

    id = db.Column(db.Integer, primary_key=True)
    body = db.Column(db.Text, nullable=False)
    sent_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_read = db.Column(db.Boolean, default=False)

    sender_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=False)

    def __repr__(self):
        return f'<Message sender={self.sender_id} project={self.project_id}>'


# ── Milestone Submissions ──────────────────────────────────────────────────────
class MilestoneSubmission(db.Model):
    __tablename__ = 'milestone_submissions'

    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255), nullable=False)
    stored_name = db.Column(db.String(255), nullable=False)
    file_size = db.Column(db.Integer)
    notes = db.Column(db.Text)
    submitted_at = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(20), default='submitted')  # submitted, reviewed

    milestone_id = db.Column(db.Integer, db.ForeignKey('milestones.id'), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

    feedback = db.relationship('SubmissionFeedback', backref='submission', lazy=True,
                               cascade='all, delete-orphan', uselist=False)

    def __repr__(self):
        return f'<MilestoneSubmission student={self.student_id} milestone={self.milestone_id}>'


# ── Submission Feedback ────────────────────────────────────────────────────────
class SubmissionFeedback(db.Model):
    __tablename__ = 'submission_feedback'

    id = db.Column(db.Integer, primary_key=True)
    comment = db.Column(db.Text, nullable=False)
    grade = db.Column(db.String(10))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    submission_id = db.Column(db.Integer, db.ForeignKey('milestone_submissions.id'), nullable=False)
    faculty_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    faculty = db.relationship('User', backref='feedbacks_given')

    def __repr__(self):
        return f'<SubmissionFeedback submission={self.submission_id}>'


# ── Workshop Scheduling ────────────────────────────────────────────────────────
class Workshop(db.Model):
    __tablename__ = 'workshops'

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    location = db.Column(db.String(200))
    date = db.Column(db.String(20), nullable=False)
    time = db.Column(db.String(10), nullable=False)
    duration_mins = db.Column(db.Integer, default=60)
    is_online = db.Column(db.Boolean, default=False)
    meeting_link = db.Column(db.String(500))
    max_participants = db.Column(db.Integer, default=30)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    organiser_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    organiser = db.relationship('User', backref='workshops_organised')
    project_id = db.Column(db.Integer, db.ForeignKey('projects.id'), nullable=True)
    project = db.relationship('Project', backref='workshops')

    registrations = db.relationship('WorkshopRegistration', backref='workshop', lazy=True,
                                    cascade='all, delete-orphan')

    @property
    def participant_count(self):
        return WorkshopRegistration.query.filter_by(workshop_id=self.id).count()

    def __repr__(self):
        return f'<Workshop {self.title}>'


# ── Workshop Registration ──────────────────────────────────────────────────────
class WorkshopRegistration(db.Model):
    __tablename__ = 'workshop_registrations'

    id = db.Column(db.Integer, primary_key=True)
    registered_at = db.Column(db.DateTime, default=datetime.utcnow)
    attended = db.Column(db.Boolean, default=False)

    workshop_id = db.Column(db.Integer, db.ForeignKey('workshops.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

    def __repr__(self):
        return f'<WorkshopRegistration user={self.user_id} workshop={self.workshop_id}>'
   


   






 
