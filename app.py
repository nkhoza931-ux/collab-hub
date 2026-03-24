import os
from flask import Flask
from extensions import db, login_manager, mail
from models import User


def load_env():
    """Manually load .env file without needing python-dotenv package."""
    env_path = os.path.join(os.path.abspath(os.path.dirname(__file__)), '.env')
    if not os.path.exists(env_path):
        return
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            # Skip comments and empty lines
            if not line or line.startswith('#'):
                continue
            if '=' in line:
                key, value = line.split('=', 1)
                key = key.strip()
                value = value.strip()
                # Only set if not already set in environment
                if key and value and key not in os.environ:
                    os.environ[key] = value


# Load .env on startup
load_env()


def create_app():
    app = Flask(__name__)

    # ── Core config ────────────────────────────────────────────────────────────
    app.config['SECRET_KEY'] = 'dut-group14-thefolks-secretkey'
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///collab_hub.db'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    # ── File upload config ─────────────────────────────────────────────────────
    BASE_DIR = os.path.abspath(os.path.dirname(__file__))
    app.config['UPLOAD_FOLDER'] = os.path.join(BASE_DIR, 'uploads')
    app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024   # 16 MB limit
    app.config['ALLOWED_EXTENSIONS'] = {
        'pdf', 'doc', 'docx', 'ppt', 'pptx',
        'xls', 'xlsx', 'txt', 'png', 'jpg', 'jpeg', 'zip'
    }
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

    # ── Email config (loaded from .env) ───────────────────────────────────────
    app.config['MAIL_SERVER'] = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
    app.config['MAIL_PORT'] = int(os.environ.get('MAIL_PORT', 587))
    app.config['MAIL_USE_TLS'] = True
    app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME', '')
    app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD', '')
    app.config['MAIL_DEFAULT_SENDER'] = os.environ.get(
        'MAIL_DEFAULT_SENDER', os.environ.get('MAIL_USERNAME', 'noreply@dut.ac.za')
    )

    # ── Init extensions ────────────────────────────────────────────────────────
    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    mail.init_app(app)

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    # ── Register Blueprints ────────────────────────────────────────────────────
    from routes.auth import auth_bp
    from routes.student import student_bp
    from routes.faculty import faculty_bp
    from routes.admin import admin_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(student_bp, url_prefix='/student')
    app.register_blueprint(faculty_bp, url_prefix='/faculty')
    app.register_blueprint(admin_bp, url_prefix='/admin')

    # ── Create tables & seed ───────────────────────────────────────────────────
    with app.app_context():
        db.create_all()
        seed_data()

    return app


def seed_data():
    """Seed the database with sample data if empty."""
    from models import User, Project, Milestone, Notification
    from werkzeug.security import generate_password_hash

    if User.query.first():
        return  # Already seeded

    admin = User(name='Admin User', email='admin@dut.ac.za',
                 password=generate_password_hash('admin123'), role='admin',
                 department='Administration')
    faculty1 = User(name='Dr. N. Mokoena', email='nmokoena@dut.ac.za',
                    password=generate_password_hash('faculty123'), role='faculty',
                    department='Computer Science')
    faculty2 = User(name='Prof. A. Singh', email='asingh@dut.ac.za',
                    password=generate_password_hash('faculty123'), role='faculty',
                    department='Electrical Engineering')
    student1 = User(name='Sipho Ndlovu', email='sipho@dut.ac.za',
                    password=generate_password_hash('student123'), role='student',
                    department='Computer Science')
    student2 = User(name='Ayesha Patel', email='ayesha@dut.ac.za',
                    password=generate_password_hash('student123'), role='student',
                    department='Information Technology')

    db.session.add_all([admin, faculty1, faculty2, student1, student2])
    db.session.commit()

    p1 = Project(
        title='AI-Assisted Crop Disease Detection',
        description='Developing a machine learning model to identify common crop diseases from smartphone images.',
        department='Computer Science',
        requirements='Python, Machine Learning, OpenCV',
        slots=4, deadline='2025-08-30', end_date='2025-10-30',
        status='open', faculty_id=faculty1.id
    )
    p2 = Project(
        title='Smart Campus Energy Management',
        description='IoT-based system to monitor and optimize energy consumption across campus buildings.',
        department='Electrical Engineering',
        requirements='IoT, Embedded Systems, Data Analysis',
        slots=3, deadline='2025-09-15', end_date='2025-11-15',
        status='open', faculty_id=faculty2.id
    )
    p3 = Project(
        title='NLP for Zulu Language Processing',
        description='Building NLP tools and datasets for isiZulu including a sentiment analysis engine.',
        department='Computer Science',
        requirements='Python, NLP, Linguistics',
        slots=6, deadline='2025-12-01', end_date='2026-02-01',
        status='open', faculty_id=faculty1.id
    )

    db.session.add_all([p1, p2, p3])
    db.session.commit()

    milestones = [
        Milestone(title='Project Proposal Approved', due_date='2025-03-15', status='completed', project_id=p1.id),
        Milestone(title='Literature Review & Data Collection', due_date='2025-04-30', status='completed', project_id=p1.id),
        Milestone(title='Prototype Development (v1)', due_date='2025-06-20', status='in_progress', project_id=p1.id),
        Milestone(title='User Testing & Feedback Round', due_date='2025-07-15', status='pending', project_id=p1.id),
        Milestone(title='Final Submission & Presentation', due_date='2025-08-30', status='pending', project_id=p1.id),
    ]
    db.session.add_all(milestones)

    notifs = [
        Notification(message='Welcome to DUT Collaboration Hub!', user_id=student1.id),
        Notification(message='New project posted: NLP for Zulu Language Processing', user_id=student1.id),
        Notification(message='New project posted: NLP for Zulu Language Processing', user_id=student2.id),
    ]
    db.session.add_all(notifs)
    db.session.commit()


if __name__ == '__main__':
    app = create_app()
    app.run(debug=True)
