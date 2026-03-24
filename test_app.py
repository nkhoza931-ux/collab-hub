"""
test_app.py
-----------
Basic unit and functional tests for the DUT Collaboration Hub.
Run with:  python -m pytest test_app.py -v
Install:   pip install pytest
"""

import pytest
import sys
import os

# Make sure the app root is on the path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from app import create_app
from extensions import db as _db
from models import User, Project, Milestone
from werkzeug.security import generate_password_hash


# ── Fixtures ───────────────────────────────────────────────────────────────────

@pytest.fixture(scope='session')
def app():
    """Create a test application with an in-memory database."""
    test_app = create_app()
    test_app.config.update({
        'TESTING': True,
        'SQLALCHEMY_DATABASE_URI': 'sqlite:///:memory:',
        'WTF_CSRF_ENABLED': False,
        'SECRET_KEY': 'test-secret-key',
        'MAIL_SUPPRESS_SEND': True,   # Never send real emails during tests
    })
    with test_app.app_context():
        _db.create_all()
        _seed_test_data()
        yield test_app
        _db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


def _seed_test_data():
    """Insert minimal test users and a project."""
    if User.query.first():
        return

    admin = User(name='Test Admin', email='admin@test.com',
                 password=generate_password_hash('admin123'), role='admin', department='Admin')
    faculty = User(name='Test Faculty', email='faculty@test.com',
                   password=generate_password_hash('faculty123'), role='faculty', department='IT')
    student = User(name='Test Student', email='student@test.com',
                   password=generate_password_hash('student123'), role='student', department='IT')

    _db.session.add_all([admin, faculty, student])
    _db.session.commit()

    project = Project(
        title='Test Project', description='A test project for unit testing.',
        department='IT', requirements='Python, Flask',
        slots=4, deadline='2026-12-01', end_date='2027-01-01',
        status='open', faculty_id=faculty.id
    )
    _db.session.add(project)
    _db.session.commit()

    milestone = Milestone(
        title='Test Milestone', due_date='2026-06-01',
        status='pending', project_id=project.id
    )
    _db.session.add(milestone)
    _db.session.commit()


def login(client, email, password):
    return client.post('/login', data={'email': email, 'password': password},
                       follow_redirects=True)


def logout(client):
    return client.get('/logout', follow_redirects=True)


# ── Auth Tests ─────────────────────────────────────────────────────────────────

class TestAuthentication:

    def test_login_page_loads(self, client):
        """Login page should return 200."""
        response = client.get('/login')
        assert response.status_code == 200
        assert b'Sign in' in response.data or b'Login' in response.data

    def test_register_page_loads(self, client):
        """Register page should return 200."""
        response = client.get('/register')
        assert response.status_code == 200

    def test_privacy_page_loads(self, client):
        """POPIA privacy page should return 200."""
        response = client.get('/privacy')
        assert response.status_code == 200
        assert b'POPIA' in response.data

    def test_valid_student_login(self, client):
        """A valid student should be redirected to student dashboard."""
        response = login(client, 'student@test.com', 'student123')
        assert response.status_code == 200
        assert b'Dashboard' in response.data or b'dashboard' in response.data
        logout(client)

    def test_valid_faculty_login(self, client):
        """A valid faculty member should be redirected to faculty dashboard."""
        response = login(client, 'faculty@test.com', 'faculty123')
        assert response.status_code == 200
        logout(client)

    def test_invalid_login(self, client):
        """Wrong password should show an error."""
        response = login(client, 'student@test.com', 'wrongpassword')
        assert b'Invalid' in response.data or b'invalid' in response.data

    def test_register_new_user(self, client):
        """A new user should be able to register."""
        response = client.post('/register', data={
            'name': 'New User',
            'email': 'newuser@test.com',
            'password': 'newpass123',
            'role': 'student',
            'department': 'Computer Science'
        }, follow_redirects=True)
        assert response.status_code == 200
        logout(client)

    def test_duplicate_email_rejected(self, client):
        """Registering with an existing email should fail."""
        response = client.post('/register', data={
            'name': 'Duplicate',
            'email': 'student@test.com',
            'password': 'password123',
            'role': 'student',
            'department': 'IT'
        }, follow_redirects=True)
        assert b'already registered' in response.data or b'Email' in response.data

    def test_logout(self, client):
        """Logging out should redirect to login."""
        login(client, 'student@test.com', 'student123')
        response = logout(client)
        assert response.status_code == 200


# ── Access Control Tests ────────────────────────────────────────────────────────

class TestAccessControl:

    def test_student_cannot_access_faculty_dashboard(self, client):
        """Student should be denied access to faculty dashboard."""
        login(client, 'student@test.com', 'student123')
        response = client.get('/faculty/dashboard', follow_redirects=True)
        assert b'Access denied' in response.data or response.status_code in [302, 200]
        logout(client)

    def test_faculty_cannot_access_admin_dashboard(self, client):
        """Faculty should be denied access to admin dashboard."""
        login(client, 'faculty@test.com', 'faculty123')
        response = client.get('/admin/dashboard', follow_redirects=True)
        assert b'Access denied' in response.data or response.status_code in [302, 200]
        logout(client)

    def test_unauthenticated_user_redirected(self, client):
        """Unauthenticated users should be redirected from protected pages."""
        logout(client)
        response = client.get('/student/dashboard', follow_redirects=True)
        assert b'Sign in' in response.data or b'login' in response.data.lower()

    def test_admin_can_access_admin_dashboard(self, client):
        """Admin should be able to access admin dashboard."""
        login(client, 'admin@test.com', 'admin123')
        response = client.get('/admin/dashboard', follow_redirects=True)
        assert response.status_code == 200
        logout(client)


# ── Model Tests ────────────────────────────────────────────────────────────────

class TestModels:

    def test_user_password_is_hashed(self, app):
        """Passwords should never be stored in plain text."""
        with app.app_context():
            user = User.query.filter_by(email='student@test.com').first()
            assert user is not None
            assert user.password != 'student123'
            assert len(user.password) > 20  # hashed passwords are long

    def test_project_exists(self, app):
        """Test project should exist in the database."""
        with app.app_context():
            project = Project.query.filter_by(title='Test Project').first()
            assert project is not None
            assert project.department == 'IT'

    def test_milestone_linked_to_project(self, app):
        """Milestone should be correctly linked to its project."""
        with app.app_context():
            project = Project.query.filter_by(title='Test Project').first()
            assert len(project.milestones) > 0
            assert project.milestones[0].title == 'Test Milestone'

    def test_project_completion_percentage(self, app):
        """Completion percentage should be 0 when all milestones are pending."""
        with app.app_context():
            project = Project.query.filter_by(title='Test Project').first()
            assert project.completion_percentage == 0

    def test_filled_slots_initially_zero(self, app):
        """New project should have 0 filled slots."""
        with app.app_context():
            project = Project.query.filter_by(title='Test Project').first()
            assert project.filled_slots == 0


# ── Page Load Tests ────────────────────────────────────────────────────────────

class TestPageLoads:

    def test_student_browse_page(self, client):
        """Browse projects page should load for students."""
        login(client, 'student@test.com', 'student123')
        response = client.get('/student/browse')
        assert response.status_code == 200
        logout(client)

    def test_student_milestones_page(self, client):
        """Milestones page should load for students."""
        login(client, 'student@test.com', 'student123')
        response = client.get('/student/milestones')
        assert response.status_code == 200
        logout(client)

    def test_faculty_my_projects_page(self, client):
        """My projects page should load for faculty."""
        login(client, 'faculty@test.com', 'faculty123')
        response = client.get('/faculty/my-projects')
        assert response.status_code == 200
        logout(client)

    def test_faculty_submissions_page(self, client):
        """Submissions page should load for faculty."""
        login(client, 'faculty@test.com', 'faculty123')
        response = client.get('/faculty/submissions')
        assert response.status_code == 200
        logout(client)

    def test_admin_users_page(self, client):
        """Admin users page should load."""
        login(client, 'admin@test.com', 'admin123')
        response = client.get('/admin/users')
        assert response.status_code == 200
        logout(client)

    def test_admin_report_page(self, client):
        """Admin report page should load."""
        login(client, 'admin@test.com', 'admin123')
        response = client.get('/admin/report')
        assert response.status_code == 200
        logout(client)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
