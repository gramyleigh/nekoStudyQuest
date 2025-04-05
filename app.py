# app.py
from flask import Flask, render_template, request, jsonify, redirect, url_for, session, send_from_directory, flash
import json
import os
from datetime import datetime, date, timedelta
import re
import uuid
from flask_mail import Mail, Message
from dotenv import load_dotenv
from models.topic import Topic
from models.resource import Resource
from models.test import Test
import time

load_dotenv()

# Configuration
SUBJECTS_FILE = 'subjects_data.json'
DETAILS_DIR = 'subject_details'
STATIC_DIR = 'static'
PROGRESS_DIR = 'progress_records'

# Default subjects to use if file doesn't exist
DEFAULT_SUBJECTS = ['Math', 'Science', 'History', 'English']

def ensure_file_structure():
    """Ensure all required directories exist and create them if they don't"""
    # Required directories
    dirs = [
        DETAILS_DIR,     # subject_details
        STATIC_DIR,      # static
        PROGRESS_DIR,    # progress_records
    ]
    
    # Create directories if they don't exist
    for directory in dirs:
        if not os.path.exists(directory):
            os.makedirs(directory)
            print(f"Created directory: {directory}")
    
    # Check if subjects file exists, create it if not
    if not os.path.exists(SUBJECTS_FILE):
        save_subjects(DEFAULT_SUBJECTS)
        print(f"Created subjects file with default subjects: {SUBJECTS_FILE}")
        
        # Also create empty subject details files for each default subject
        for subject in DEFAULT_SUBJECTS:
            if not os.path.exists(get_subject_details_file(subject)):
                save_subject_details(subject, {"resources": [], "tests": [], "study_materials": []})
                print(f"Created empty details file for subject: {subject}")
    
    return True

# Initialize the app
app = Flask(__name__, static_folder='static')
app.secret_key = 'your_secret_key'  # Required for session

# Add custom strptime filter
def strptime_filter(date_str, format_str):
    try:
        return datetime.strptime(date_str, format_str)
    except (ValueError, TypeError):
        return None

# Register the strptime filter
app.jinja_env.filters['strptime'] = strptime_filter

# Make timedelta available in templates
app.jinja_env.globals['timedelta'] = timedelta

# Email configuration
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = os.getenv('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD')
app.config['MAIL_DEFAULT_SENDER'] = os.getenv('MAIL_USERNAME')
app.config['MAIL_MAX_EMAILS'] = 100  # Limit number of emails sent in a single connection
app.config['MAIL_SUPPRESS_SEND'] = False  # Set to True in testing environment
app.config['MAIL_ASCII_ATTACHMENTS'] = False  # Allow UTF-8 attachments

# Initialize Mail with error handling
try:
    mail = Mail(app)
except Exception as e:
    print(f"Error initializing email configuration: {str(e)}")
    mail = None

def validate_email_config():
    """Validate email configuration and return status"""
    if not app.config['MAIL_USERNAME'] or not app.config['MAIL_PASSWORD']:
        return False, "Email configuration is incomplete. Please check MAIL_USERNAME and MAIL_PASSWORD in .env file."
    
    try:
        with mail.connect() as conn:
            return True, "Email configuration is valid and connection successful."
    except Exception as e:
        return False, f"Email configuration error: {str(e)}"

def send_email_with_retry(subject, recipients, html_body, max_retries=3, retry_delay=1):
    """Send an email with retry mechanism"""
    if not mail:
        flash("Email service is not configured properly.", "error")
        return False

    for attempt in range(max_retries):
        try:
            msg = Message(
                subject=subject,
                recipients=recipients,
                html=html_body,
                sender=app.config['MAIL_USERNAME']
            )
            mail.send(msg)
            return True
        except Exception as e:
            print(f"Email send attempt {attempt + 1} failed: {str(e)}")
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
            else:
                flash(f"Failed to send email after {max_retries} attempts: {str(e)}", "error")
                return False

# ===== Email Functions =====

def send_test_reminder_email(subject_name, test_name, test_date, progress):
    """Send a reminder email for an upcoming test"""
    recipient = app.config['MAIL_USERNAME']

    # Calculate days until test
    test_date_obj = datetime.strptime(test_date, '%Y-%m-%d').date()
    today = date.today()
    days_remaining = (test_date_obj - today).days

    subject = f"📚 Test Reminder: {test_name} - {subject_name}"
    
    body = f"""
    <html>
    <body style="font-family: Arial, sans-serif; padding: 20px; background-color: #f9f9f9;">
        <div style="max-width: 600px; margin: 0 auto; background-color: white; padding: 20px; border-radius: 10px; border-top: 5px solid #6b58cd; box-shadow: 0 2px 10px rgba(0, 0, 0, 0.1);">
            <h1 style="color: #6b58cd;">Test Reminder</h1>
            <p>Hello! This is a reminder about your upcoming test:</p>
            <div style="background-color: #f0f0f0; padding: 15px; border-radius: 8px; margin: 15px 0;">
                <h2 style="margin-top: 0; color: #ff5f8f;">{test_name}</h2>
                <p><strong>Subject:</strong> {subject_name}</p>
                <p><strong>Date:</strong> {test_date}</p>
                <p><strong>Days Remaining:</strong> {days_remaining}</p>
                <div style="background-color: white; border-radius: 5px; padding: 10px; margin-top: 10px;">
                    <h3 style="color: #66bb6a;">Current Progress: {progress}%</h3>
                    <div style="background-color: #f5f5f5; border-radius: 10px; height: 20px; overflow: hidden;">
                        <div style="width: {progress}%; height: 100%; background-color: #66bb6a;"></div>
                    </div>
                </div>
            </div>
            <p>Keep up the great work! Remember to:</p>
            <ul style="color: #555;">
                <li>Review your study materials</li>
                <li>Take practice tests</li>
                <li>Get enough rest before the test</li>
            </ul>
            <p>Nya~ 😺</p>
            <div style="margin-top: 20px; padding-top: 20px; border-top: 1px solid #eee; font-size: 12px; color: #999;">
                <p>This is an automated reminder from your Neko Study Quest app.</p>
            </div>
        </div>
    </body>
    </html>
    """

    if send_email_with_retry(subject, [recipient], body):
        flash(f"Test reminder email sent for {test_name}!", "success")
        return True
    return False

def send_daily_progress_email(subject_name, test_name, resources_completed):
    """Send a daily progress summary email"""
    recipient = app.config['MAIL_USERNAME']

    subject = f"📊 Daily Progress: {test_name} - {subject_name}"

    body = f"""
    <html>
    <body style="font-family: Arial, sans-serif; padding: 20px; background-color: #f9f9f9;">
        <div style="max-width: 600px; margin: 0 auto; background-color: white; padding: 20px; border-radius: 10px; border-top: 5px solid #6b58cd; box-shadow: 0 2px 10px rgba(0, 0, 0, 0.1);">
            <h1 style="color: #6b58cd;">Daily Progress Summary</h1>
            <p>Hello! Here's your daily progress update:</p>
            <div style="background-color: #f0f0f0; padding: 15px; border-radius: 8px; margin: 15px 0;">
                <h2 style="margin-top: 0; color: #ff5f8f;">{test_name}</h2>
                <p><strong>Subject:</strong> {subject_name}</p>
                <p><strong>Date:</strong> {date.today().strftime('%Y-%m-%d')}</p>
                <h3 style="color: #66bb6a;">Resources Completed Today: {len(resources_completed)}</h3>
                <ul style="padding-left: 20px;">
                    {''.join(['<li><strong>' + r['topic_name'] + ':</strong> ' + r['resource_name'] + '</li>' for r in resources_completed])}
                </ul>
            </div>
            <p>Great job on your progress today!</p>
            <p>Nya~ 😺</p>
            <div style="margin-top: 20px; padding-top: 20px; border-top: 1px solid #eee; font-size: 12px; color: #999;">
                <p>This is an automated message from your Neko Study Quest app.</p>
            </div>
        </div>
    </body>
    </html>
    """

    if send_email_with_retry(subject, [recipient], body):
        flash(f"Daily progress email sent for {test_name}!", "success")
        return True
    return False

def send_test_complete_email(subject_name, test_name, progress, completed_resources, total_resources):
    """Send an email when a test is completed"""
    recipient = app.config['MAIL_USERNAME']

    subject = f"🎉 Test Complete: {test_name} - {subject_name}"
    
    completion_percentage = (completed_resources / total_resources) * 100 if total_resources > 0 else 0
    
    body = f"""
    <html>
    <body style="font-family: Arial, sans-serif; padding: 20px; background-color: #f9f9f9;">
        <div style="max-width: 600px; margin: 0 auto; background-color: white; padding: 20px; border-radius: 10px; border-top: 5px solid #6b58cd; box-shadow: 0 2px 10px rgba(0, 0, 0, 0.1);">
            <h1 style="color: #6b58cd;">Test Preparation Complete! 🎊</h1>
            <p>Congratulations! You've completed your preparation for:</p>
            <div style="background-color: #f0f0f0; padding: 15px; border-radius: 8px; margin: 15px 0;">
                <h2 style="margin-top: 0; color: #ff5f8f;">{test_name}</h2>
                <p><strong>Subject:</strong> {subject_name}</p>
                <p><strong>Date:</strong> {date.today().strftime('%Y-%m-%d')}</p>
                <div style="background-color: white; border-radius: 5px; padding: 10px; margin-top: 10px;">
                    <h3 style="color: #66bb6a;">Final Progress: {progress}%</h3>
                    <div style="background-color: #f5f5f5; border-radius: 10px; height: 20px; overflow: hidden;">
                        <div style="width: {progress}%; height: 100%; background-color: #66bb6a;"></div>
                    </div>
                </div>
                <div style="margin-top: 15px;">
                    <h3 style="color: #66bb6a;">Resources Completed: {completed_resources}/{total_resources} ({completion_percentage:.1f}%)</h3>
                </div>
            </div>
            <p>You're well prepared for your test! Remember to:</p>
            <ul style="color: #555;">
                <li>Review any challenging topics</li>
                <li>Get a good night's sleep</li>
                <li>Arrive early to your test location</li>
                <li>Stay calm and confident!</li>
            </ul>
            <p>Best of luck on your test! 🍀</p>
            <p>Nya~ 😺</p>
            <div style="margin-top: 20px; padding-top: 20px; border-top: 1px solid #eee; font-size: 12px; color: #999;">
                <p>This is an automated message from your Neko Study Quest app.</p>
            </div>
        </div>
    </body>
    </html>
    """

    if send_email_with_retry(subject, [recipient], body):
        flash(f"Test completion email sent for {test_name}!", "success")
        return True
    return False

def send_upcoming_tests_summary_email(upcoming_tests):
    """Send a summary email for all upcoming tests"""
    recipient = app.config['MAIL_USERNAME']
    
    subject = f"📅 Upcoming Tests Summary ({len(upcoming_tests)} tests)"
    
    # Sort tests by date
    upcoming_tests.sort(key=lambda x: datetime.strptime(x['date'], '%Y-%m-%d'))
    
    # Generate test list HTML
    test_list_html = ""
    for test in upcoming_tests:
        days_until = (datetime.strptime(test['date'], '%Y-%m-%d').date() - date.today()).days
        test_list_html += f"""
        <div style="background-color: #f0f0f0; padding: 15px; border-radius: 8px; margin: 15px 0;">
            <h3 style="margin-top: 0; color: #ff5f8f;">{test['name']}</h3>
            <p><strong>Subject:</strong> {test['subject']}</p>
            <p><strong>Date:</strong> {test['date']} ({days_until} days away)</p>
            <div style="background-color: white; border-radius: 5px; padding: 10px;">
                <h4 style="color: #66bb6a; margin: 0;">Progress: {test['progress']}%</h4>
                <div style="background-color: #f5f5f5; border-radius: 10px; height: 20px; overflow: hidden; margin-top: 5px;">
                    <div style="width: {test['progress']}%; height: 100%; background-color: #66bb6a;"></div>
                </div>
            </div>
        </div>
        """
    
    body = f"""
    <html>
    <body style="font-family: Arial, sans-serif; padding: 20px; background-color: #f9f9f9;">
        <div style="max-width: 600px; margin: 0 auto; background-color: white; padding: 20px; border-radius: 10px; border-top: 5px solid #6b58cd; box-shadow: 0 2px 10px rgba(0, 0, 0, 0.1);">
            <h1 style="color: #6b58cd;">Upcoming Tests Summary</h1>
            <p>Hello! Here are your upcoming tests:</p>
            {test_list_html}
            <p>Keep up the great work with your studies!</p>
            <p>Nya~ 😺</p>
            <div style="margin-top: 20px; padding-top: 20px; border-top: 1px solid #eee; font-size: 12px; color: #999;">
                <p>This is an automated summary from your Neko Study Quest app.</p>
            </div>
        </div>
    </body>
    </html>
    """
    
    if send_email_with_retry(subject, [recipient], body):
        flash(f"Summary email sent for {len(upcoming_tests)} upcoming tests!", "success")
        return True
    return False


# ===== Data Model Functions =====

def load_subjects():
    """Load subjects from the JSON file or return defaults if file doesn't exist"""
    if os.path.exists(SUBJECTS_FILE):
        try:
            with open(SUBJECTS_FILE, 'r') as file:
                return json.load(file)
        except (json.JSONDecodeError, IOError):
            # If file is corrupted or can't be read, use defaults
            return DEFAULT_SUBJECTS
    else:
        # If file doesn't exist yet, use defaults and create it
        save_subjects(DEFAULT_SUBJECTS)
        return DEFAULT_SUBJECTS


def save_subjects(subjects):
    """Save subjects to the JSON file"""
    with open(SUBJECTS_FILE, 'w') as file:
        json.dump(subjects, file)


def get_subject_details_file(subject_name):
    """Get the path to the subject details JSON file"""
    safe_name = re.sub(r'[^\w]', '_', subject_name)
    return os.path.join(DETAILS_DIR, f"{safe_name}.json")


def get_progress_records_file(subject_name, test_id):
    """Get the path to the progress records JSON file for a specific test"""
    safe_name = re.sub(r'[^\w]', '_', subject_name)
    return os.path.join(PROGRESS_DIR, f"{safe_name}_{test_id}_progress.json")


def load_subject_details(subject_name):
    """Load details for a specific subject"""
    file_path = get_subject_details_file(subject_name)

    if os.path.exists(file_path):
        try:
            with open(file_path, 'r') as file:
                return json.load(file)
        except (json.JSONDecodeError, IOError):
            # Return empty structure if file is corrupted
            return {"resources": [], "tests": [], "study_materials": []}
    else:
        # Return empty structure if file doesn't exist
        return {"resources": [], "tests": [], "study_materials": []}


def save_subject_details(subject_name, details):
    """Save details for a specific subject"""
    file_path = get_subject_details_file(subject_name)

    with open(file_path, 'w') as file:
        json.dump(details, file)


def load_progress_records(subject_name, test_id):
    """Load progress records for a specific test"""
    file_path = get_progress_records_file(subject_name, test_id)

    if os.path.exists(file_path):
        try:
            with open(file_path, 'r') as file:
                return json.load(file)
        except (json.JSONDecodeError, IOError):
            # Return empty structure if file is corrupted
            return {"records": []}
    else:
        # Return empty structure if file doesn't exist
        return {"records": []}


def save_progress_records(subject_name, test_id, records):
    """Save progress records for a specific test"""
    file_path = get_progress_records_file(subject_name, test_id)

    with open(file_path, 'w') as file:
        json.dump(records, file)


def calculate_progress(test, subject_name):
    """Calculate progress percentage for a specific test"""
    # Make sure test has an id before proceeding
    if 'id' not in test:
        return 0  # Return 0% progress if test has no id

    # Load progress records
    progress_records = load_progress_records(subject_name, test['id'])

    # Count total resources required
    total_required = 0

    # Check if topics is a list of dictionaries or a string
    if isinstance(test.get('topics', []), list):
        for topic in test.get('topics', []):
            # Make sure topic is a dictionary with resources
            if isinstance(topic, dict) and 'resources' in topic:
                for resource in topic.get('resources', []):
                    total_required += resource.get('count', 1)

    # Count completed resources
    completed = len(progress_records.get('records', []))

    # Calculate percentage
    if total_required > 0:
        percentage = (completed / total_required) * 100
        return round(percentage, 1)
    else:
        return 0


def get_date_counts(subject_name, test_id):
    """Get counts of resources completed by date"""
    progress_records = load_progress_records(subject_name, test_id)
    date_counts = {}

    for record in progress_records.get('records', []):
        record_date = record.get('date')
        if record_date in date_counts:
            date_counts[record_date] += 1
        else:
            date_counts[record_date] = 1

    # Sort by date
    sorted_dates = sorted(date_counts.items(), key=lambda x: datetime.strptime(x[0], '%Y-%m-%d'))

    return sorted_dates


def get_topic_counts(subject_name, test_id):
    """Get counts of resources completed by topic"""
    progress_records = load_progress_records(subject_name, test_id)
    topic_counts = {}

    for record in progress_records.get('records', []):
        topic_name = record.get('topic_name')
        if topic_name in topic_counts:
            topic_counts[topic_name] += 1  # Fixed from A1 to 1
        else:
            topic_counts[topic_name] = 1

    return topic_counts


def is_past_test(test_date):
    """Determine if a test is in the past"""
    try:
        test_date_obj = datetime.strptime(test_date, '%Y-%m-%d').date()
        today = date.today()
        return test_date_obj < today
    except (ValueError, TypeError):
        return False


def get_upcoming_tests(days=7):
    """Get all upcoming tests in the next X days"""
    upcoming_tests = []
    subjects = load_subjects()
    today = date.today()
    end_date = today + timedelta(days=days)

    for subject_name in subjects:
        subject_data = load_subject_details(subject_name)

        for test in subject_data.get('tests', []):
            if not isinstance(test, dict) or 'date' not in test:
                continue

            try:
                test_date = datetime.strptime(test['date'], '%Y-%m-%d').date()

                # Check if test is upcoming
                if today <= test_date <= end_date:
                    # Add subject name and progress
                    test['subject_name'] = subject_name
                    test['progress'] = calculate_progress(test, subject_name)
                    upcoming_tests.append(test)
            except (ValueError, TypeError):
                continue

    # Sort by date
    upcoming_tests.sort(key=lambda x: datetime.strptime(x['date'], '%Y-%m-%d'))

    return upcoming_tests


def get_todays_resources(subject_name, test_id):
    """Get resources completed today for a specific test"""
    progress_records = load_progress_records(subject_name, test_id)
    today = date.today().strftime('%Y-%m-%d')

    today_resources = []
    for record in progress_records.get('records', []):
        if record.get('date') == today:
            today_resources.append(record)

    return today_resources


# ===== Routes =====
@app.route('/all-statistics')
def all_statistics():
    """Show statistics for all subjects and tests with detailed analytics"""
    subjects = load_subjects()
    all_tests = []

    # Statistics summary data
    total_resources_completed = 0
    total_resources_required = 0
    total_topics = 0
    total_tests = 0

    # Resource completion by subject
    subject_completion = {}
    for subject_name in subjects:
        subject_completion[subject_name] = {'completed': 0, 'total': 0}

    # Collect progress by date across all tests
    date_progress = {}

    # Subject performance data
    subject_performance = {}
    for subject_name in subjects:
        subject_performance[subject_name] = {'tests': 0, 'avg_progress': 0, 'total_progress': 0}

    for subject_name in subjects:
        # Load details for the subject
        subject_data = load_subject_details(subject_name)

        # Process tests
        for test in subject_data.get('tests', []):
            # Make sure test is a dictionary with an id
            if isinstance(test, dict) and 'id' in test:
                # Count total tests
                total_tests += 1
                subject_performance[subject_name]['tests'] += 1

                # Calculate progress
                test['progress'] = calculate_progress(test, subject_name)
                subject_performance[subject_name]['total_progress'] += test['progress']

                # Add subject name to test
                test['subject_name'] = subject_name

                # Check if test is in the past
                if 'date' in test:
                    test['is_past'] = is_past_test(test['date'])

                # Load progress records for this test
                progress_records = load_progress_records(subject_name, test['id'])
                test['records_count'] = len(progress_records.get('records', []))

                # Count resources completed and gather date data
                for record in progress_records.get('records', []):
                    total_resources_completed += 1
                    subject_completion[subject_name]['completed'] += 1

                    # Add to date progress
                    record_date = record.get('date')
                    if record_date:
                        if record_date in date_progress:
                            date_progress[record_date] += 1
                        else:
                            date_progress[record_date] = 1

                # Count total topics
                if 'topics' in test and isinstance(test.get('topics'), list):
                    test_topics = len(test.get('topics', []))
                    total_topics += test_topics

                    # Count total resources required
                    for topic in test.get('topics', []):
                        if isinstance(topic, dict) and 'resources' in topic:
                            for resource in topic.get('resources', []):
                                resource_count = resource.get('count', 1)
                                total_resources_required += resource_count
                                subject_completion[subject_name]['total'] += resource_count

                # Add test to the list
                all_tests.append(test)

    # Calculate average progress per subject
    for subject_name in subjects:
        if subject_performance[subject_name]['tests'] > 0:
            subject_performance[subject_name]['avg_progress'] = round(
                subject_performance[subject_name]['total_progress'] / subject_performance[subject_name]['tests'], 1)

    # Sort tests by date
    all_tests_with_dates = [t for t in all_tests if 'date' in t]
    all_tests_without_dates = [t for t in all_tests if 'date' not in t]

    if all_tests_with_dates:
        all_tests_with_dates = sorted(all_tests_with_dates,
                                      key=lambda x: datetime.strptime(x['date'], '%Y-%m-%d'))

    all_tests = all_tests_with_dates + all_tests_without_dates

    # Convert date progress to sorted list
    date_progress_list = sorted(date_progress.items(),
                                key=lambda x: datetime.strptime(x[0], '%Y-%m-%d'))

    # Calculate overall completion percentage
    overall_completion = 0
    if total_resources_required > 0:
        overall_completion = round((total_resources_completed / total_resources_required) * 100, 1)

    # Calculate average progress across all tests
    avg_test_progress = 0
    if all_tests:
        total_progress = sum(test.get('progress', 0) for test in all_tests)
        avg_test_progress = round(total_progress / len(all_tests), 1)

    # Get upcoming tests (next 7 days)
    today = date.today()
    upcoming_deadline = today + timedelta(days=7)
    upcoming_tests = []

    for test in all_tests:
        if 'date' in test and not test.get('is_past', False):
            try:
                test_date = datetime.strptime(test['date'], '%Y-%m-%d').date()
                if test_date <= upcoming_deadline:
                    upcoming_tests.append(test)
            except (ValueError, TypeError):
                continue

    # Sort upcoming tests by date
    upcoming_tests.sort(key=lambda x: datetime.strptime(x['date'], '%Y-%m-%d'))

    return render_template('all_statistics.html',
                           all_tests=all_tests,
                           date_progress=date_progress_list,
                           subject_completion=subject_completion,
                           subject_performance=subject_performance,
                           stats_summary={
                               'total_tests': total_tests,
                               'total_topics': total_topics,
                               'total_resources': total_resources_required,
                               'completed_resources': total_resources_completed,
                               'overall_completion': overall_completion,
                               'avg_test_progress': avg_test_progress
                           },
                           upcoming_tests=upcoming_tests)


@app.route('/')
def index():
    """Main page showing all subjects and tests"""
    subjects = load_subjects()
    all_tests = []

    # Daily progress data (resources completed by date)
    daily_progress = {}

    # Subject completion counts
    subject_counts = {}

    # Stats summary
    stats_summary = {
        'completed_resources': 0,
        'upcoming_tests': 0,
        'current_streak': 0,
        'avg_score': 0.0,
        'total_score_count': 0,
        'total_score_sum': 0.0
    }

    for subject_name in subjects:
        subject_counts[subject_name] = 0

        # Load details for the subject
        subject_data = load_subject_details(subject_name)

        # Process tests
        for test in subject_data.get('tests', []):
            # Make sure test is a dictionary with an id
            if isinstance(test, dict) and 'id' in test:
                # Calculate progress
                test['progress'] = calculate_progress(test, subject_name)

                # Add subject name to test
                test['subject_name'] = subject_name

                # Format test data for display
                test_data = {
                    'test_id': test.get('id'),
                    'test_name': test.get('name'),
                    'date': test.get('date'),
                    'subject_name': subject_name,
                    'progress': test['progress'],
                    'is_past': False
                }

                # Check if test is in the past
                if 'date' in test:
                    test_data['is_past'] = is_past_test(test['date'])
                    # Count upcoming tests
                    if not test_data['is_past']:
                        stats_summary['upcoming_tests'] += 1

                all_tests.append(test_data)

                # Load progress records for this test
                progress_records = load_progress_records(subject_name, test['id'])

                # Count completed resources for this subject
                completed_resources = len(progress_records.get('records', []))
                subject_counts[subject_name] += completed_resources
                stats_summary['completed_resources'] += completed_resources

                # Collect daily progress data and sum up scores
                for record in progress_records.get('records', []):
                    record_date = record.get('date')
                    if record_date:
                        if record_date in daily_progress:
                            daily_progress[record_date] += 1
                        else:
                            daily_progress[record_date] = 1

                    # Sum scores for average calculation
                    if record.get('score') is not None:
                        stats_summary['total_score_sum'] += record.get('score')
                        stats_summary['total_score_count'] += 1

    # Sort tests by date
    tests_with_dates = [t for t in all_tests if 'date' in t]
    tests_without_dates = [t for t in all_tests if 'date' not in t]

    if tests_with_dates:
        tests_with_dates = sorted(tests_with_dates,
                                  key=lambda x: datetime.strptime(x['date'], '%Y-%m-%d'))

    all_tests = tests_with_dates + tests_without_dates

    # Convert daily progress to sorted list for charts
    daily_progress_list = sorted(daily_progress.items(),
                                 key=lambda x: datetime.strptime(x[0], '%Y-%m-%d'))

    # Get last 7 days if available, otherwise use what we have
    if len(daily_progress_list) > 7:
        daily_progress_list = daily_progress_list[-7:]

    # Calculate streak
    stats_summary['current_streak'] = calculate_streak(daily_progress_list)

    # Calculate average score
    if stats_summary['total_score_count'] > 0:
        stats_summary['avg_score'] = stats_summary['total_score_sum'] / stats_summary['total_score_count']

    return render_template('index.html',
                           subjects=subjects,
                           all_tests=all_tests,
                           daily_progress=daily_progress_list,
                           subject_counts=subject_counts,
                           stats_summary=stats_summary)


def calculate_streak(daily_progress_list):
    """Calculate the current streak of consecutive days with completed resources"""
    if not daily_progress_list:
        return 0

    # Convert to datetime objects for easier comparison
    date_objects = [(datetime.strptime(date, '%Y-%m-%d'), count) for date, count in daily_progress_list]

    # Sort by date (newest first)
    date_objects.sort(reverse=True)

    # Get today's date
    today = datetime.now().date()

    # Initialize streak count
    streak = 0

    # Check if latest activity was today or yesterday
    if date_objects and (date_objects[0][0].date() == today or
                         date_objects[0][0].date() == today - timedelta(days=1)):
        # Start counting streak
        last_date = date_objects[0][0].date()
        streak = 1

        for i in range(1, len(date_objects)):
            current_date = date_objects[i][0].date()
            # If dates are consecutive
            if last_date - current_date == timedelta(days=1):
                streak += 1
                last_date = current_date
            else:
                break

    return streak


@app.route('/subject/<subject_name>')
def subject_details(subject_name):
    """Show details for a specific subject"""
    # Load details for the subject
    subject_data = load_subject_details(subject_name)

    # Initialize tests if not present
    if 'tests' not in subject_data:
        subject_data['tests'] = []

    # Process each test
    for test in subject_data.get('tests', []):
        # Make sure each test is a dictionary
        if not isinstance(test, dict):
            continue

        # Make sure each test has an id
        if 'id' not in test:
            test['id'] = str(uuid.uuid4())  # Generate an id if missing

        # Calculate progress for each test
        test['progress'] = calculate_progress(test, subject_name)

        # Make sure each topic has resources initialized
        if 'topics' in test and isinstance(test['topics'], list):
            for topic in test['topics']:
                if isinstance(topic, dict) and 'resources' not in topic:
                    topic['resources'] = []

                # Initialize completed count and scores for each resource
                if isinstance(topic, dict) and 'resources' in topic:
                    progress_records = load_progress_records(subject_name, test['id'])
                    for resource in topic['resources']:
                        if isinstance(resource, dict):
                            # Count completed instances in progress records
                            completed_records = [r for r in progress_records.get('records', [])
                                                 if r.get('resource_id') == resource.get('id')]
                            resource['completed'] = len(completed_records)

                            # Add scores if they exist
                            resource['scores'] = []
                            for record in completed_records:
                                if 'score' in record:
                                    resource['scores'].append(record['score'])

    # Save any updates to IDs or initialized structures
    save_subject_details(subject_name, subject_data)

    # Sort tests by date (upcoming first)
    if subject_data.get('tests'):
        # Filter out any non-dictionary tests
        subject_data['tests'] = [t for t in subject_data.get('tests', []) if isinstance(t, dict)]

        # Make sure each test has a date field before sorting
        tests_with_dates = [t for t in subject_data['tests'] if 'date' in t]

        # Sort by date
        if tests_with_dates:
            tests_with_dates = sorted(tests_with_dates,
                                      key=lambda x: datetime.strptime(x['date'], '%Y-%m-%d'))

            # Add back any tests without dates at the end
            tests_without_dates = [t for t in subject_data['tests'] if 'date' not in t]
            subject_data['tests'] = tests_with_dates + tests_without_dates

    # Save sorted tests back to the file
    save_subject_details(subject_name, subject_data)

    return render_template('subject_details.html',
                           subject_name=subject_name,
                           subject_data=subject_data)

@app.route('/edit_test', methods=['POST'])
def edit_test():
    """Edit a test name and date"""
    subject_name = request.form.get('subject_name', '').strip()
    test_id = request.form.get('test_id', '').strip()
    name = request.form.get('test_name', '').strip()
    test_date = request.form.get('test_date', '').strip()

    if name and test_date and subject_name and test_id:
        # Load existing details
        details = load_subject_details(subject_name)

        # Find the test to update
        for test in details.get('tests', []):
            if isinstance(test, dict) and test.get('id') == test_id:
                test['name'] = name
                test['date'] = test_date
                break

        # Save updated details
        save_subject_details(subject_name, details)
        flash('Test updated successfully!', 'success')
    else:
        flash('Please enter a valid test name and date!', 'error')

    return redirect(url_for('subject_details', subject_name=subject_name))

@app.route('/subject/<subject_name>/test/<test_id>/topic/<topic_id>/edit', methods=['POST'])
def edit_test_topic(subject_name, test_id, topic_id):
    """Edit a topic name"""
    topic_name = request.form.get('topic_name', '').strip()

    if topic_name:
        # Load existing details
        details = load_subject_details(subject_name)

        # Find the test and the topic to update
        for test in details.get('tests', []):
            if isinstance(test, dict) and test.get('id') == test_id:
                for topic in test.get('topics', []):
                    if isinstance(topic, dict) and topic.get('id') == topic_id:
                        topic['name'] = topic_name
                        break

        # Save updated details
        save_subject_details(subject_name, details)
        flash(f'Topic "{topic_name}" updated successfully!', 'success')
    else:
        flash('Please enter a valid topic name!', 'error')

    return redirect(url_for('edit_test_topics', subject_name=subject_name, test_id=test_id))

@app.route('/subject/<subject_name>/test/<test_id>/topic/<topic_id>/resource/<resource_id>/edit', methods=['POST'])
def edit_topic_resource(subject_name, test_id, topic_id, resource_id):
    """Edit a resource name and count"""
    resource_name = request.form.get('resource_name', '').strip()
    resource_count = request.form.get('resource_count', '1').strip()

    # Convert count to integer, default to 1 if invalid
    try:
        count = int(resource_count)
        if count < 1:
            count = 1
    except ValueError:
        count = 1

    if resource_name:
        # Load existing details
        details = load_subject_details(subject_name)

        # Find the test, topic and resource to update
        for test in details.get('tests', []):
            if isinstance(test, dict) and test.get('id') == test_id:
                for topic in test.get('topics', []):
                    if isinstance(topic, dict) and topic.get('id') == topic_id:
                        for resource in topic.get('resources', []):
                            if isinstance(resource, dict) and resource.get('id') == resource_id:
                                resource['name'] = resource_name
                                resource['count'] = count
                                break

        # Save updated details
        save_subject_details(subject_name, details)
        flash(f'Resource "{resource_name}" updated successfully!', 'success')
    else:
        flash('Please enter a valid resource name!', 'error')

    return redirect(url_for('edit_test_topics', subject_name=subject_name, test_id=test_id))


@app.route('/subject/<subject_name>/test/<test_id>/topics', methods=['GET'])
def edit_test_topics(subject_name, test_id):
    """Edit topics for a test"""
    # Load details for the subject
    subject_data = load_subject_details(subject_name)

    # Find the test
    test = next((t for t in subject_data.get('tests', []) if isinstance(t, dict) and t.get('id') == test_id), None)

    if test:
        return render_template('edit_test_topics.html',
                               subject_name=subject_name,
                               test=test)

    flash('Test not found!', 'error')
    return redirect(url_for('subject_details', subject_name=subject_name))





@app.route('/subject/<subject_name>/test/<test_id>/topic/<topic_id>/delete_resource/<resource_id>', methods=['POST'])
def delete_topic_resource(subject_name, test_id, topic_id, resource_id):
    """Delete a resource from a topic"""
    # Load existing details
    details = load_subject_details(subject_name)

    # Find the test
    test = next((t for t in details.get('tests', []) if isinstance(t, dict) and t.get('id') == test_id), None)

    if test and isinstance(test.get('topics'), list):
        # Find the topic
        topic = next((t for t in test['topics'] if isinstance(t, dict) and t.get('id') == topic_id), None)

        if topic and isinstance(topic.get('resources'), list):
            # Remove the resource
            topic['resources'] = [r for r in topic['resources'] if r.get('id') != resource_id]

            # Save updated details
            save_subject_details(subject_name, details)
            flash('Resource deleted successfully!', 'success')

    return redirect(url_for('edit_test_topics', subject_name=subject_name, test_id=test_id))


@app.route('/subject/<subject_name>/test/<test_id>/delete_topic/<topic_id>', methods=['POST'])
def delete_test_topic(subject_name, test_id, topic_id):
    """Delete a topic from a test"""
    # Load existing details
    details = load_subject_details(subject_name)

    # Find the test
    test = next((t for t in details.get('tests', []) if isinstance(t, dict) and t.get('id') == test_id), None)

    if test and isinstance(test.get('topics'), list):
        # Remove the topic
        test['topics'] = [t for t in test['topics'] if t.get('id') != topic_id]

        # Save updated details
        save_subject_details(subject_name, details)
        flash('Topic deleted successfully!', 'success')

    return redirect(url_for('edit_test_topics', subject_name=subject_name, test_id=test_id))


@app.route('/track-progress/<subject_name>/<test_id>', methods=['GET'])
def track_progress(subject_name, test_id):
    """Track progress for a test"""
    # Load details for the subject
    subject_data = load_subject_details(subject_name)

    # Find the test
    test = next((t for t in subject_data.get('tests', []) if isinstance(t, dict) and t.get('id') == test_id), None)

    if test:
        # Calculate progress
        progress_percentage = calculate_progress(test, subject_name)
        test['progress'] = progress_percentage

        # Load progress records
        progress_records = load_progress_records(subject_name, test_id)

        # Process resources to include scores
        for topic in test.get('topics', []):
            if isinstance(topic, dict) and 'resources' in topic:
                for resource in topic.get('resources', []):
                    # Count completed resources
                    resource['completed'] = len([r for r in progress_records.get('records', [])
                                                 if r.get('resource_id') == resource.get('id')])

                    # Add scores if they exist
                    resource['scores'] = []
                    for record in progress_records.get('records', []):
                        if record.get('resource_id') == resource.get('id') and 'score' in record:
                            resource['scores'].append(record['score'])

        # Get date counts for chart
        date_counts = get_date_counts(subject_name, test_id)

        # Get topic counts for chart
        topic_counts = get_topic_counts(subject_name, test_id)

        return render_template('track_progress.html',
                               subject_name=subject_name,
                               test=test,
                               progress_records=progress_records,
                               date_counts=date_counts,
                               topic_counts=topic_counts)

    flash('Test not found!', 'error')
    return redirect(url_for('subject_details', subject_name=subject_name))

@app.route('/track-progress/<subject_name>/<test_id>/add_record', methods=['POST'])
def add_progress_record(subject_name, test_id):
    """Add a progress record for a test"""
    topic_id = request.form.get('topic_id', '').strip()
    resource_id = request.form.get('resource_id', '').strip()
    notes = request.form.get('notes', '').strip()

    if topic_id and resource_id:
        # Load subject details and progress records
        subject_data = load_subject_details(subject_name)
        progress_data = load_progress_records(subject_name, test_id)

        # Find the test
        test = next((t for t in subject_data.get('tests', []) if isinstance(t, dict) and t.get('id') == test_id), None)

        if test and isinstance(test.get('topics'), list):
            # Find the topic
            topic = next((t for t in test['topics'] if isinstance(t, dict) and t.get('id') == topic_id), None)

            if topic and isinstance(topic.get('resources'), list):
                # Find the resource
                resource = next((r for r in topic['resources'] if isinstance(r, dict) and r.get('id') == resource_id),
                                None)

                if resource:
                    # Initialize records list if not exists
                    if 'records' not in progress_data:
                        progress_data['records'] = []

                    # Add record with timestamp
                    now = datetime.now()
                    record = {
                        'id': str(uuid.uuid4()),
                        'topic_id': topic_id,
                        'topic_name': topic['name'],
                        'resource_id': resource_id,
                        'resource_name': resource['name'],
                        'notes': notes,
                        'date': now.strftime('%Y-%m-%d'),
                        'timestamp': now.strftime('%Y-%m-%d %H:%M:%S')
                    }

                    progress_data['records'].append(record)

                    # Save progress records
                    save_progress_records(subject_name, test_id, progress_data)

                    # Get today's completed resources for this test
                    todays_resources = get_todays_resources(subject_name, test_id)

                    # If this is the first record today, send a daily progress email
                    if len(todays_resources) == 1:
                        send_daily_progress_email(subject_name, test['name'], [record])

                    # Check if test progress is complete (100%)
                    progress_percentage = calculate_progress(test, subject_name)
                    if progress_percentage == 100:
                        # Count total resources
                        total_resources = 0
                        for topic in test.get('topics', []):
                            for resource in topic.get('resources', []):
                                total_resources += resource.get('count', 1)

                        # Send completion email
                        send_test_complete_email(subject_name, test['name'], progress_percentage,
                                                 len(progress_data['records']), total_resources)

                    flash('Progress recorded successfully!', 'success')
                    return redirect(url_for('track_progress', subject_name=subject_name, test_id=test_id))

                flash('Resource not found!', 'error')
            else:
                flash('Topic not found!', 'error')
        else:
            flash('Test not found!', 'error')
    else:
        flash('Please select a topic and resource!', 'error')

    return redirect(url_for('track_progress', subject_name=subject_name, test_id=test_id))


@app.route('/test-statistics/<subject_name>/<test_id>')
def test_statistics(subject_name, test_id):
    """Show statistics for a test"""
    # Load details for the subject
    subject_data = load_subject_details(subject_name)

    # Find the test
    test = next((t for t in subject_data.get('tests', []) if isinstance(t, dict) and t.get('id') == test_id), None)

    if test:
        # Calculate progress
        test['progress'] = calculate_progress(test, subject_name)

        # Load progress records
        progress_records = load_progress_records(subject_name, test_id)
        records = progress_records.get('records', [])
        
        # Get date counts for chart (already sorted by date)
        date_counts = get_date_counts(subject_name, test_id)

        # Get topic counts for chart
        topic_counts = get_topic_counts(subject_name, test_id)
        
        # Process resources to include completion data
        for topic in test.get('topics', []):
            if isinstance(topic, dict) and 'resources' in topic:
                for resource in topic.get('resources', []):
                    # Count completed resources
                    resource['completed'] = len([r for r in records
                                               if r.get('resource_id') == resource.get('id')])
                    
                    # Add scores if they exist
                    resource['scores'] = []
                    for record in records:
                        if record.get('resource_id') == resource.get('id') and 'score' in record:
                            resource['scores'].append(record.get('score'))
        
        # Collect all scores for score analysis
        all_scores = []
        for record in records:
            if 'score' in record and record.get('score') is not None:
                all_scores.append(record.get('score'))
                
        # Calculate average score
        avg_score = sum(all_scores) / len(all_scores) if all_scores else 0
        
        # Get unique dates from records
        unique_dates = set()
        for record in records:
            record_date = record.get('date')
            if record_date:
                unique_dates.add(record_date)
        
        sorted_dates = sorted(list(unique_dates))

        # Calculate days remaining if test has a date
        if 'date' in test:
            try:
                test_date = datetime.strptime(test['date'], '%Y-%m-%d').date()
                today = date.today()
                test['days_remaining'] = (test_date - today).days
            except (ValueError, TypeError):
                test['days_remaining'] = 0

        return render_template('test_statistics.html',
                           subject_name=subject_name,
                           test=test,
                           date_counts=date_counts,
                           topic_counts=topic_counts,
                           all_scores=all_scores,
                           avg_score=avg_score,
                           sorted_dates=sorted_dates,
                           records=records)

    flash('Test not found!', 'error')
    return redirect(url_for('subject_details', subject_name=subject_name))


@app.route('/subject/<subject_name>/add_test', methods=['POST'])
def add_test(subject_name):
    """Add a new test for a subject"""
    name = request.form.get('test_name', '').strip()
    test_date = request.form.get('test_date', '').strip()

    if name and test_date:
        # Load existing details
        details = load_subject_details(subject_name)

        # Initialize tests list if not exists
        if 'tests' not in details:
            details['tests'] = []

        # Generate a unique ID for the test
        test_id = str(uuid.uuid4())

        # Add new test
        new_test = {
            'id': test_id,
            'name': name,
            'date': test_date,
            'topics': [],  # Will be populated with topic resources later
            'progress': 0  # Initialize progress at 0%
        }

        details['tests'].append(new_test)

        # Save updated details
        save_subject_details(subject_name, details)

        # Return JSON response instead of redirect for AJAX
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({
                'success': True,
                'message': 'Test added successfully!',
                'test': new_test
            })

        flash('Test added successfully!', 'success')
        return redirect(url_for('subject_details', subject_name=subject_name))

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({
            'success': False,
            'message': 'Please enter a valid test name and date!'
        }), 400

    flash('Please enter a valid test name and date!', 'error')
    return redirect(url_for('subject_details', subject_name=subject_name))


@app.route('/subject/<subject_name>/test/<test_id>/add_topic', methods=['POST'])
def add_test_topic(subject_name, test_id):
    """Add a new topic to a test"""
    topic_name = request.form.get('topic_name', '').strip()

    if topic_name:
        # Load existing details
        details = load_subject_details(subject_name)

        # Find the test
        test = next((t for t in details.get('tests', []) if isinstance(t, dict) and t.get('id') == test_id), None)

        if test:
            # Initialize topics list if not exists or is not a list
            if not isinstance(test.get('topics'), list):
                test['topics'] = []

            # Check if topic already exists
            existing_topic = next((t for t in test['topics'] if isinstance(t, dict) and t.get('name') == topic_name),
                                  None)

            if existing_topic:
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return jsonify({
                        'success': False,
                        'message': f'Topic "{topic_name}" already exists!'
                    }), 400
                flash(f'Topic "{topic_name}" already exists!', 'error')
            else:
                # Add new topic
                topic_id = str(uuid.uuid4())  # Generate a unique ID for the topic
                new_topic = {
                    'id': topic_id,
                    'name': topic_name,
                    'resources': []
                }
                test['topics'].append(new_topic)

                # Save updated details
                save_subject_details(subject_name, details)

                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return jsonify({
                        'success': True,
                        'message': f'Topic "{topic_name}" added successfully!',
                        'topic': new_topic,
                        'test_id': test_id
                    })

                flash(f'Topic "{topic_name}" added successfully!', 'success')

            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({'redirect': url_for('edit_test_topics', subject_name=subject_name, test_id=test_id)})

            return redirect(url_for('edit_test_topics', subject_name=subject_name, test_id=test_id))

        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({
                'success': False,
                'message': 'Test not found!'
            }), 404

        flash('Test not found!', 'error')
    else:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({
                'success': False,
                'message': 'Please enter a valid topic name!'
            }), 400

        flash('Please enter a valid topic name!', 'error')

    return redirect(url_for('subject_details', subject_name=subject_name))


@app.route('/subject/<subject_name>/test/<test_id>/topic/<topic_id>/add_resource', methods=['POST'])
def add_topic_resource(subject_name, test_id, topic_id):
    """Add a new resource to a topic"""
    resource_name = request.form.get('resource_name', '').strip()
    resource_count = request.form.get('resource_count', '1').strip()

    # Convert count to integer, default to 1 if invalid
    try:
        count = int(resource_count)
        if count < 1:
            count = 1
    except ValueError:
        count = 1

    if resource_name:
        # Load existing details
        details = load_subject_details(subject_name)

        # Find the test
        test = next((t for t in details.get('tests', []) if isinstance(t, dict) and t.get('id') == test_id), None)

        if test and isinstance(test.get('topics'), list):
            # Find the topic
            topic = next((t for t in test['topics'] if isinstance(t, dict) and t.get('id') == topic_id), None)

            if topic:
                # Initialize resources list if not exists
                if 'resources' not in topic:
                    topic['resources'] = []

                # Add new resource with a unique ID
                resource_id = str(uuid.uuid4())
                new_resource = {
                    'id': resource_id,
                    'name': resource_name,
                    'count': count,
                    'completed': 0  # Initialize completed at 0
                }
                topic['resources'].append(new_resource)

                # Save updated details
                save_subject_details(subject_name, details)

                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return jsonify({
                        'success': True,
                        'message': f'Resource "{resource_name}" added successfully!',
                        'resource': new_resource,
                        'topic_id': topic_id,
                        'test_id': test_id
                    })

                flash(f'Resource "{resource_name}" added successfully!', 'success')
                return redirect(url_for('edit_test_topics', subject_name=subject_name, test_id=test_id))

            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({
                    'success': False,
                    'message': 'Topic not found!'
                }), 404

            flash('Topic not found!', 'error')
        else:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({
                    'success': False,
                    'message': 'Test not found!'
                }), 404

            flash('Test not found!', 'error')
    else:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({
                'success': False,
                'message': 'Please enter a valid resource name!'
            }), 400

        flash('Please enter a valid resource name!', 'error')

    return redirect(url_for('edit_test_topics', subject_name=subject_name, test_id=test_id))




@app.route('/subject/<subject_name>/delete_topic/<topic_id>', methods=['POST'])
def delete_subject_topic(subject_name, topic_id):
    """Delete a topic from a subject"""
    # Load existing details
    details = load_subject_details(subject_name)

    # Remove the topic
    details['topics'] = [
        topic for topic in details.get('topics', []) 
        if topic.get('id') != topic_id
    ]

    # Save updated details
    save_subject_details(subject_name, details)
    
    flash('Topic deleted successfully!', 'success')
    return redirect(url_for('subject_details', subject_name=subject_name))

@app.route('/subject/<subject_name>/topic/<topic_id>/delete_resource/<resource_id>', methods=['POST'])
def delete_subject_topic_resource(subject_name, topic_id, resource_id):
    """Delete a resource from a subject's topic"""
    # Load existing details
    details = load_subject_details(subject_name)

    # Find the topic
    for topic in details.get('topics', []):
        if topic.get('id') == topic_id:
            # Remove the resource
            topic['resources'] = [
                resource for resource in topic.get('resources', [])
                if resource.get('id') != resource_id
            ]
            break

    # Save updated details
    save_subject_details(subject_name, details)
    
    flash('Resource deleted successfully!', 'success')
    return redirect(url_for('subject_details', subject_name=subject_name))














@app.route('/edit-subject-name', methods=['POST'])
def edit_subject_name():
    """
    Edit a subject's name.
    This function handles both regular form submissions and AJAX requests.
    For AJAX requests, it returns JSON responses.
    For regular form submissions, it redirects to the index page.
    """
    original_subject_name = request.form.get('original_subject_name', '').strip()
    new_subject_name = request.form.get('new_subject_name', '').strip()

    if not original_subject_name or not new_subject_name:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': False, 'message': 'Both original and new subject names are required!'})
        else:
            flash('Both original and new subject names are required!', 'error')
            return redirect(url_for('index'))

    # Load subjects
    subjects = load_subjects()

    # Check if original subject exists
    if original_subject_name not in subjects:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': False, 'message': f'Subject "{original_subject_name}" not found!'})
        else:
            flash(f'Subject "{original_subject_name}" not found!', 'error')
            return redirect(url_for('index'))

    # Check if new subject name already exists
    if new_subject_name in subjects and new_subject_name != original_subject_name:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': False, 'message': f'Subject "{new_subject_name}" already exists!'})
        else:
            flash(f'Subject "{new_subject_name}" already exists!', 'error')
            return redirect(url_for('index'))

    try:
        # Update the subject name in the subjects list
        subjects[subjects.index(original_subject_name)] = new_subject_name
        save_subjects(subjects)

        # Update the subject details file
        original_file_path = get_subject_details_file(original_subject_name)
        if os.path.exists(original_file_path):
            # Load original subject details
            subject_details = load_subject_details(original_subject_name)
            
            # Save with new name
            save_subject_details(new_subject_name, subject_details)
            
            # Remove original file
            os.remove(original_file_path)

        # Update any progress records
        safe_original = re.sub(r'[^\w]', '_', original_subject_name)
        safe_new = re.sub(r'[^\w]', '_', new_subject_name)
        
        for filename in os.listdir(PROGRESS_DIR):
            if filename.startswith(f"{safe_original}_"):
                # Get the test_id part
                test_id = filename.replace(f"{safe_original}_", "").split("_")[0]
                
                # Load progress data
                progress_file = os.path.join(PROGRESS_DIR, filename)
                with open(progress_file, 'r') as file:
                    progress_data = json.load(file)
                
                # Save to new file
                new_progress_file = os.path.join(PROGRESS_DIR, f"{safe_new}_{test_id}_progress.json")
                with open(new_progress_file, 'w') as file:
                    json.dump(progress_data, file)
                
                # Remove original file
                os.remove(progress_file)

        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({
                'success': True, 
                'message': f'Subject renamed from "{original_subject_name}" to "{new_subject_name}" successfully!',
                'subject': new_subject_name
            })
        else:
            flash(f'Subject renamed from "{original_subject_name}" to "{new_subject_name}" successfully!', 'success')

    except Exception as e:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': False, 'message': f'Error updating subject: {str(e)}'})
        else:
            flash(f'Error updating subject: {str(e)}', 'error')

    return redirect(url_for('index'))

@app.route('/edit-subjects')
def edit_subjects():
    """Edit subjects"""
    subjects = load_subjects()
    
    # Get the count of tests and resources for each subject
    subject_stats = {}
    for subject_name in subjects:
        subject_data = load_subject_details(subject_name)
        
        # Count tests
        test_count = len(subject_data.get('tests', []))
        
        # Count resources across all tests
        resource_count = 0
        for test in subject_data.get('tests', []):
            if isinstance(test, dict) and 'topics' in test:
                for topic in test.get('topics', []):
                    if isinstance(topic, dict) and 'resources' in topic:
                        resource_count += len(topic.get('resources', []))
        
        subject_stats[subject_name] = {
            'tests': test_count,
            'resources': resource_count
        }
    
    return render_template('edit_subjects.html', subjects=subjects, subject_stats=subject_stats)


@app.route('/add-subject', methods=['POST'])
def add_subject():
    """
    Add a new subject.
    This function handles both regular form submissions and AJAX requests.
    For AJAX requests, it returns JSON responses.
    For regular form submissions, it redirects to the index page.
    """
    subject_name = request.form.get('subject_name', '').strip()

    if subject_name:
        # Load existing subjects
        subjects = load_subjects()

        # Check if subject already exists
        if subject_name in subjects:
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({'success': False, 'message': f'Subject "{subject_name}" already exists!'})
            else:
                flash(f'Subject "{subject_name}" already exists!', 'error')
        else:
            # Add new subject
            subjects.append(subject_name)

            # Save updated subjects
            save_subjects(subjects)

            # Create empty details file
            save_subject_details(subject_name, {"resources": [], "tests": [], "study_materials": []})

            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({'success': True, 'message': f'Subject "{subject_name}" added successfully!', 'subject': subject_name})
            else:
                flash(f'Subject "{subject_name}" added successfully!', 'success')
    else:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': False, 'message': 'Please enter a valid subject name!'})
        else:
            flash('Please enter a valid subject name!', 'error')

    # Redirect to index page instead of edit_subjects
    return redirect(url_for('index'))

@app.route('/delete_subject', methods=['POST'])
def delete_subject():
    """
    Delete a subject and all its associated data.
    This route handles POST requests from the delete button on subject cards.
    No confirmation page is shown - deletion happens immediately.
    """
    # Get the subject name from the form submission
    subject_to_delete = request.form.get('subject_name', '')

    # Load the current list of subjects
    subjects = load_subjects()
    
    # Check if the subject exists before trying to delete it
    if subject_to_delete in subjects:
        # Remove the subject from the list
        subjects.remove(subject_to_delete)
        
        # Save the updated subjects list
        save_subjects(subjects)

        # Clean up: Delete the subject details file
        file_path = get_subject_details_file(subject_to_delete)
        if os.path.exists(file_path):
            os.remove(file_path)
            
        # Clean up: Delete all related progress files
        # First create a safe version of the subject name for filename matching
        safe_name = re.sub(r'[^\w]', '_', subject_to_delete)
        
        # Loop through all files in the progress directory
        for filename in os.listdir(PROGRESS_DIR):
            # If the file belongs to this subject, delete it
            if filename.startswith(f"{safe_name}_"):
                os.remove(os.path.join(PROGRESS_DIR, filename))
                
        # Show a success message
        flash(f'Subject "{subject_to_delete}" deleted successfully!', 'success')
    else:
        # Subject not found, show an error message
        flash(f'Subject "{subject_to_delete}" not found!', 'error')

    # Redirect back to the index page
    return redirect(url_for('index'))



@app.template_filter('today')
def today():
    """Return today's date as a datetime object for use in templates"""
    return datetime.now().date()

# Make today() available as a function in templates
app.jinja_env.globals['today'] = today

@app.route('/past-tests')
def past_tests():
    """Show statistics for past tests"""
    subjects = load_subjects()
    past_tests = []
    
    for subject_name in subjects:
        # Load details for the subject
        subject_data = load_subject_details(subject_name)
        
        # Process tests
        for test in subject_data.get('tests', []):
            # Make sure test is a dictionary with an id and date
            if isinstance(test, dict) and 'id' in test and 'date' in test:
                # Check if test is in the past
                if is_past_test(test['date']):
                    # Calculate progress
                    test['progress'] = calculate_progress(test, subject_name)
                    
                    # Add subject name to test
                    test['subject_name'] = subject_name
                    
                    # Load records for the test
                    progress_records = load_progress_records(subject_name, test['id'])
                    test['records'] = progress_records.get('records', [])
                    
                    # Get topic counts for the test explicitly
                    topic_counts = get_topic_counts(subject_name, test['id'])
                    test['topic_counts'] = topic_counts
                    
                    # Process each topic to include completion data
                    if isinstance(test.get('topics'), list):
                        for topic in test.get('topics', []):
                            if isinstance(topic, dict) and 'resources' in topic:
                                for resource in topic.get('resources', []):
                                    # Count completed resources
                                    resource['completed'] = len([r for r in test['records'] 
                                                                if r.get('resource_id') == resource.get('id')])

                    # Compute date statistics - Sort dates and get unique dates
                    unique_dates = set()
                    for record in test['records']:
                        record_date = record.get('date')
                        if record_date:
                            unique_dates.add(record_date)
                    
                    test['unique_dates'] = sorted(list(unique_dates))
                    
                    # Create date_counts dictionary for the timeline
                    date_counts = {}
                    for record in test['records']:
                        record_date = record.get('date')
                        if record_date:
                            if record_date in date_counts:
                                date_counts[record_date] += 1
                            else:
                                date_counts[record_date] = 1
                    
                    test['date_counts'] = date_counts
                    
                    # Calculate scores statistics if available
                    scores = []
                    for record in test['records']:
                        if 'score' in record and record['score'] is not None:
                            scores.append(record['score'])
                    
                    test['scores'] = scores
                    test['avg_score'] = sum(scores) / len(scores) if scores else 0
                    
                    past_tests.append(test)
    
    # Sort tests by date (most recent first)
    if past_tests:
        past_tests = sorted(past_tests,
                            key=lambda x: datetime.strptime(x['date'], '%Y-%m-%d'),
                            reverse=True)
    
    return render_template('past_tests.html', past_tests=past_tests)


# === Email Notification Routes ===

@app.route('/send-test-reminder/<subject_name>/<test_id>', methods=['POST'])
def send_test_reminder(subject_name, test_id):
    """Send a test reminder email"""
    # Load subject details
    subject_data = load_subject_details(subject_name)

    # Find the test
    test = next((t for t in subject_data.get('tests', []) if isinstance(t, dict) and t.get('id') == test_id), None)

    if test:
        # Calculate progress
        progress = calculate_progress(test, subject_name)

        # Send reminder email
        send_test_reminder_email(subject_name, test['name'], test['date'], progress)

        return redirect(url_for('track_progress', subject_name=subject_name, test_id=test_id))

    flash('Test not found!', 'error')
    return redirect(url_for('subject_details', subject_name=subject_name))


@app.route('/send-progress-summary/<subject_name>/<test_id>', methods=['POST'])
def send_progress_summary(subject_name, test_id):
    """Send a progress summary email"""
    # Load subject details
    subject_data = load_subject_details(subject_name)

    # Find the test
    test = next((t for t in subject_data.get('tests', []) if isinstance(t, dict) and t.get('id') == test_id), None)

    if test:
        # Get today's resources
        todays_resources = get_todays_resources(subject_name, test_id)

        # Send progress email
        if todays_resources:
            send_daily_progress_email(subject_name, test['name'], todays_resources)
            flash('Progress summary email sent!', 'success')
        else:
            flash('No progress recorded today!', 'error')

        return redirect(url_for('track_progress', subject_name=subject_name, test_id=test_id))

    flash('Test not found!', 'error')
    return redirect(url_for('subject_details', subject_name=subject_name))


@app.route('/check-upcoming-tests')
def check_upcoming_tests():
    """Check for upcoming tests and send reminders"""
    upcoming_tests = get_upcoming_tests(days=7)

    for test in upcoming_tests:
        subject_name = test['subject_name']
        test_date_obj = datetime.strptime(test['date'], '%Y-%m-%d').date()
        today = date.today()
        days_remaining = (test_date_obj - today).days

        # Send reminder for tests that are 7, 3, or 1 day away
        if days_remaining in [7, 3, 1]:
            send_test_reminder_email(subject_name, test['name'], test['date'], test['progress'])

    flash('Checked for upcoming tests and sent reminders!', 'success')
    return redirect(url_for('index'))


@app.route('/static/<path:filename>')
def serve_static(filename):
    """Serve static files"""
    return send_from_directory(app.static_folder, filename)


@app.route('/update-progress', methods=['POST'])
def update_progress():
    """Update progress for a resource (increment or decrement) with optional score"""
    try:
        data = request.get_json()
        resource_id = data.get('resource_id')
        change = data.get('change', 0)  # 1 for increment, -1 for decrement
        score = data.get('score')  # Optional score (percentage)

        # We need to find which subject and test this resource belongs to
        subjects = load_subjects()
        for subject_name in subjects:
            subject_data = load_subject_details(subject_name)
            for test in subject_data.get('tests', []):
                if isinstance(test, dict) and 'topics' in test and 'id' in test:
                    for topic in test.get('topics', []):
                        if isinstance(topic, dict) and 'resources' in topic:
                            for resource in topic.get('resources', []):
                                if isinstance(resource, dict) and resource.get('id') == resource_id:
                                    # Found the resource - now update progress
                                    progress_data = load_progress_records(subject_name, test['id'])

                                    # Get current completed count
                                    completed = 0
                                    for record in progress_data.get('records', []):
                                        if record.get('resource_id') == resource_id:
                                            completed += 1

                                    # Calculate new completion count
                                    total = resource.get('count', 1)
                                    new_completed = completed + change

                                    # Ensure completed count is within bounds
                                    if new_completed < 0:
                                        new_completed = 0
                                    if new_completed > total:
                                        new_completed = total

                                    # If incrementing, add a new record
                                    if change > 0 and new_completed > completed:
                                        # Initialize records list if not exists
                                        if 'records' not in progress_data:
                                            progress_data['records'] = []

                                        # Add record with timestamp
                                        now = datetime.now()
                                        record = {
                                            'id': str(uuid.uuid4()),
                                            'topic_id': topic['id'],
                                            'topic_name': topic['name'],
                                            'resource_id': resource_id,
                                            'resource_name': resource['name'],
                                            'notes': '',
                                            'date': now.strftime('%Y-%m-%d'),
                                            'timestamp': now.strftime('%Y-%m-%d %H:%M:%S')
                                        }

                                        # Add score if provided
                                        if score is not None:
                                            record['score'] = float(score)

                                        progress_data['records'].append(record)

                                    # If decrementing, remove the latest record
                                    elif change < 0 and new_completed < completed:
                                        # Find and remove the last record for this resource
                                        for i in range(len(progress_data.get('records', [])) - 1, -1, -1):
                                            if progress_data['records'][i].get('resource_id') == resource_id:
                                                del progress_data['records'][i]
                                                break

                                    # Save progress records
                                    save_progress_records(subject_name, test['id'], progress_data)

                                    # Calculate new progress percentage
                                    progress_percentage = calculate_progress(test, subject_name)

                                    return jsonify({
                                        'success': True,
                                        'completed': new_completed,
                                        'total': total,
                                        'progress': progress_percentage
                                    })

        return jsonify({'success': False, 'message': 'Resource not found'}), 404
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/send-reminder', methods=['POST'])
def send_reminder():
    """Send a study reminder email"""
    try:
        data = request.get_json()
        subject = data.get('subject')
        message = data.get('message')
        recipient = data.get('recipient')

        msg = Message(
            subject=f'Study Reminder: {subject}',
            sender=app.config['MAIL_USERNAME'],
            recipients=[recipient]
        )
        msg.body = message
        mail.send(msg)
        
        return jsonify({'success': True, 'message': 'Reminder sent successfully!'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/add-todo', methods=['POST'])
def add_todo():
    """Add a new task to the To-Do List."""
    task_text = request.form.get('task_text', '').strip()
    subject = request.form.get('subject', '').strip()

    if not task_text or not subject:
        return jsonify({'success': False, 'message': 'Task text and subject are required.'}), 400

    # Initialize session data if not present
    if 'todo_data' not in session:
        session['todo_data'] = {'tasks': []}

    # Add the new task
    task_id = str(uuid.uuid4())
    session['todo_data']['tasks'].append({
        'id': task_id,
        'text': task_text,
        'subject': subject,
        'completed': False
    })
    session.modified = True

    return jsonify({'success': True, 'task_id': task_id, 'message': 'Task added successfully.'})

@app.route('/toggle-todo/<task_id>', methods=['POST'])
def toggle_todo(task_id):
    """Toggle the completion status of a task."""
    if 'todo_data' not in session:
        return jsonify({'success': False, 'message': 'No tasks found.'}), 400

    for task in session['todo_data']['tasks']:
        if task['id'] == task_id:
            task['completed'] = not task['completed']
            session.modified = True
            return jsonify({'success': True, 'completed': task['completed'], 'message': 'Task updated successfully.'})

    return jsonify({'success': False, 'message': 'Task not found.'}), 404

@app.context_processor
def inject_todo_data():
    """Inject To-Do List data into templates."""
    return {'todo_data': session.get('todo_data', {'tasks': []})}

@app.route('/subject/<subject_name>/delete_test/<test_id>', methods=['POST'])
def delete_subject_test(subject_name, test_id):
    """Delete a test from a subject"""
    # Load existing details
    details = load_subject_details(subject_name)

    # Find and remove the test
    if 'tests' in details:
        details['tests'] = [test for test in details['tests'] if test.get('id') != test_id]

    # Save updated details
    save_subject_details(subject_name, details)

    flash('Test deleted successfully!', 'success')
    return redirect(url_for('subject_details', subject_name=subject_name))



@app.route('/email-config')
def email_config():
    """Show email configuration page"""
    status, message = validate_email_config()
    email_settings = {
        'server': app.config['MAIL_SERVER'],
        'port': app.config['MAIL_PORT'],
        'use_tls': app.config['MAIL_USE_TLS'],
        'username': app.config['MAIL_USERNAME'],
        'sender': app.config['MAIL_DEFAULT_SENDER'],
        'status': status,
        'message': message
    }
    return render_template('email_config.html', email_settings=email_settings)

@app.route('/validate-email-config')
def validate_email_configuration():
    """Validate email configuration and return status"""
    status, message = validate_email_config()
    return jsonify({
        'success': status,
        'message': message
    })

@app.route('/send-test-email', methods=['POST'])
def send_test_email():
    """Send a test email to verify configuration"""
    recipient = app.config['MAIL_USERNAME']
    subject = "🐱 Test Email from Neko Study Quest"
    
    body = """
    <html>
    <body style="font-family: Arial, sans-serif; padding: 20px; background-color: #f9f9f9;">
        <div style="max-width: 600px; margin: 0 auto; background-color: white; padding: 20px; border-radius: 10px; border-top: 5px solid #6b58cd; box-shadow: 0 2px 10px rgba(0, 0, 0, 0.1);">
            <h1 style="color: #6b58cd;">Email Configuration Test</h1>
            <p>Hello! This is a test email from your Neko Study Quest app.</p>
            <div style="background-color: #f0f0f0; padding: 15px; border-radius: 8px; margin: 15px 0;">
                <h3 style="color: #66bb6a;">✅ Email configuration is working!</h3>
                <p>If you're seeing this email, it means your email settings are configured correctly.</p>
            </div>
            <p>You can now receive:</p>
            <ul style="color: #555;">
                <li>Test reminders</li>
                <li>Daily progress updates</li>
                <li>Test completion notifications</li>
                <li>Upcoming tests summaries</li>
            </ul>
            <p>Nya~ 😺</p>
            <div style="margin-top: 20px; padding-top: 20px; border-top: 1px solid #eee; font-size: 12px; color: #999;">
                <p>This is a test message from your Neko Study Quest app.</p>
            </div>
        </div>
    </body>
    </html>
    """
    
    try:
        if send_email_with_retry(subject, [recipient], body):
            return jsonify({
                'success': True,
                'message': 'Test email sent successfully! Please check your inbox.'
            })
        else:
            return jsonify({
                'success': False,
                'message': 'Failed to send test email. Please check your email configuration.'
            })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error sending test email: {str(e)}'
        }), 500

@app.route('/email-test')
def email_test_page():
    """Show email test page"""
    return render_template('email_test.html')

@app.route('/email-dashboard')
def email_dashboard():
    """Show email dashboard"""
    return render_template('email_dashboard.html')

@app.route('/send-upcoming-summary', methods=['POST'])
def send_upcoming_summary():
    """Send a summary email for all upcoming tests"""
    days = int(request.form.get('days', 7))
    upcoming_tests = get_upcoming_tests(days=days)
    
    if upcoming_tests:
        send_upcoming_tests_summary_email(upcoming_tests)
    else:
        flash(f"No upcoming tests in the next {days} days!", "warning")
    
    # Redirect back to email dashboard
    return redirect(url_for('email_dashboard'))

def validate_subject_name(subject_name):
    """Validate and clean a subject name for storage"""
    # Trim whitespace
    cleaned_name = subject_name.strip()
    
    # Check if the name is empty after cleaning
    if not cleaned_name:
        return None, "Subject name cannot be empty"
    
    # Check if the name is too long
    if len(cleaned_name) > 50:
        return None, "Subject name is too long (max 50 characters)"
    
    # Check for invalid characters that might cause file system issues
    invalid_chars = ['/', '\\', ':', '*', '?', '"', '<', '>', '|']
    for char in invalid_chars:
        if char in cleaned_name:
            return None, f"Subject name contains invalid character: {char}"
    
    return cleaned_name, None

def ensure_file_structure():
    """Ensure all required directories exist and create them if they don't"""
    # Required directories
    dirs = [
        DETAILS_DIR,     # subject_details
        STATIC_DIR,      # static
        PROGRESS_DIR,    # progress_records
    ]
    
    # Create directories if they don't exist
    for directory in dirs:
        if not os.path.exists(directory):
            os.makedirs(directory)
            print(f"Created directory: {directory}")
    
    # Check if subjects file exists, create it if not
    if not os.path.exists(SUBJECTS_FILE):
        save_subjects(DEFAULT_SUBJECTS)
        print(f"Created subjects file with default subjects: {SUBJECTS_FILE}")
        
        # Also create empty subject details files for each default subject
        for subject in DEFAULT_SUBJECTS:
            if not os.path.exists(get_subject_details_file(subject)):
                save_subject_details(subject, {"resources": [], "tests": [], "study_materials": []})
                print(f"Created empty details file for subject: {subject}")
    
    return True

@app.route('/send-test-reminder-sample', methods=['POST'])
def send_test_reminder_sample():
    """Send a sample test reminder email"""
    subject_name = request.form.get('subject_name')
    test_name = request.form.get('test_name')
    test_date = request.form.get('test_date')
    progress = float(request.form.get('progress', 50))
    
    # Send reminder email
    send_test_reminder_email(subject_name, test_name, test_date, progress)
    
    flash('Test reminder email sent successfully!', 'success')
    return redirect(url_for('email_test_page'))

@app.route('/send-daily-progress-sample', methods=['POST'])
def send_daily_progress_sample():
    """Send a sample daily progress email"""
    subject_name = request.form.get('subject_name')
    test_name = request.form.get('test_name')
    resources_count = int(request.form.get('resources', 3))
    
    # Create sample resources
    resources = []
    for i in range(resources_count):
        resources.append({
            'topic_name': f'Sample Topic {i+1}',
            'resource_name': f'Sample Resource {i+1}'
        })
    
    # Send progress email
    send_daily_progress_email(subject_name, test_name, resources)
    
    flash('Daily progress email sent successfully!', 'success')
    return redirect(url_for('email_test_page'))

@app.route('/send-test-complete-sample', methods=['POST'])
def send_test_complete_sample():
    """Send a sample test completion email"""
    subject_name = request.form.get('subject_name')
    test_name = request.form.get('test_name')
    progress = float(request.form.get('progress', 100))
    completed = int(request.form.get('completed', 10))
    total = int(request.form.get('total', 10))
    
    # Send completion email
    send_test_complete_email(subject_name, test_name, progress, completed, total)
    
    flash('Test completion email sent successfully!', 'success')
    return redirect(url_for('email_test_page'))

@app.route('/send-custom-email', methods=['POST'])
def send_custom_email():
    """Send a custom email to test email functionality"""
    try:
        subject = request.form.get('subject', 'Test Email')
        body = request.form.get('body', 'This is a test email.')
        send_email_with_retry(subject, [app.config['EMAIL_USERNAME']], body)
        flash('Custom email sent successfully!', 'success')
    except Exception as e:
        flash(f'Failed to send custom email: {str(e)}', 'error')
    return redirect(url_for('email_dashboard'))

@app.template_filter('today')
def today():
    """Return today's date as a datetime object for use in templates"""
    return datetime.now().date()

if __name__ == '__main__':
    try:
        ensure_file_structure()
        print("Starting Neko Study Quest...")
        print("Ensuring file structure... Success")
        
        # Configure email
        if app.config['MAIL_USERNAME']:
            print(f"Email configured for: {app.config['MAIL_USERNAME']}")
        
        print("Starting server...")
        app.run(debug=True)
    except Exception as e:
        print(f"Error starting application: {str(e)}")

