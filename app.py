from flask import Flask, render_template, request, jsonify, session, redirect, url_for, flash, g
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
import json
import random
import logging
import traceback
from logging.handlers import RotatingFileHandler

# Configure logging
logging.basicConfig(level=logging.DEBUG)
handler = RotatingFileHandler('app.log', maxBytes=10000, backupCount=3)
handler.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
import functools
import requests
from oauthlib.oauth2 import WebApplicationClient
from werkzeug.utils import secure_filename
# Optional OpenCV import for face detection
OPENCV_AVAILABLE = False
try:
    import cv2
    import numpy as np
    OPENCV_AVAILABLE = True
except ImportError:
    pass

import base64

# Google OAuth Configuration
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_OAUTH_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET")
GOOGLE_DISCOVERY_URL = "https://accounts.google.com/.well-known/openid-configuration"

# Local development only: allow OAuth over HTTP
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

def get_google_provider_cfg():
    return requests.get(GOOGLE_DISCOVERY_URL).json()

client = WebApplicationClient(GOOGLE_CLIENT_ID)

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-here'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///college_erp.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# Create upload directory if it doesn't exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

db = SQLAlchemy(app)

# Database Models
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(120), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # admin, staff, student
    created_at = db.Column(db.DateTime, default=datetime.now)

class Application(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    organization = db.Column(db.String(100), nullable=False)
    first_name = db.Column(db.String(100), nullable=False)
    last_name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(15), nullable=False)
    date_of_birth = db.Column(db.Date, nullable=False)
    gender = db.Column(db.String(10), nullable=False)
    address = db.Column(db.Text, nullable=False)
    course = db.Column(db.String(100), nullable=False)
    qualification = db.Column(db.String(100), nullable=False)
    previous_institution = db.Column(db.String(200), nullable=False)
    marks = db.Column(db.Float, nullable=False)
    passing_year = db.Column(db.Integer, nullable=False)
    entrance_score = db.Column(db.Float, nullable=True)
    status = db.Column(db.String(20), default='pending')  # pending, approved, rejected
    submitted_at = db.Column(db.DateTime, default=datetime.utcnow)
    reviewed_at = db.Column(db.DateTime)
    reviewed_by = db.Column(db.Integer, db.ForeignKey('user.id'))
    
    # Relationships
    documents = db.relationship('Document', backref='application', lazy=True)
    user = db.relationship('User', foreign_keys=[user_id], backref='applications')
    reviewer = db.relationship('User', foreign_keys=[reviewed_by], backref='reviewed_applications')

class Student(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.String(20), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(15), nullable=False)
    course = db.Column(db.String(50), nullable=False)
    year = db.Column(db.Integer, nullable=False)
    admission_date = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(20), default='active')  # active, graduated, dropped_out
    gpa = db.Column(db.Float, default=0.0)
    attendance_percentage = db.Column(db.Float, default=100.0)
    risk_score = db.Column(db.Float, default=0.0)

class Fee(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.String(20), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    fee_type = db.Column(db.String(50), nullable=False)
    payment_date = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(20), default='paid')
    receipt_number = db.Column(db.String(50), unique=True, nullable=False)

class Hostel(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    room_number = db.Column(db.String(10), unique=True, nullable=False)
    floor = db.Column(db.Integer, nullable=False)
    capacity = db.Column(db.Integer, default=2)
    occupied = db.Column(db.Integer, default=0)
    student_ids = db.Column(db.Text)  # JSON string of student IDs
    status = db.Column(db.String(20), default='available')  # available, occupied, maintenance

class Exam(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.String(20), nullable=False)
    subject = db.Column(db.String(100), nullable=False)
    exam_date = db.Column(db.DateTime, nullable=False)
    marks = db.Column(db.Integer)
    grade = db.Column(db.String(2))
    semester = db.Column(db.Integer, nullable=False)

class Attendance(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.String(20), nullable=False)
    date = db.Column(db.Date, nullable=False)
    status = db.Column(db.String(10), nullable=False)  # present, absent
    subject = db.Column(db.String(100), nullable=False)

class Timetable(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    day = db.Column(db.String(10), nullable=False)
    time_slot = db.Column(db.String(20), nullable=False)
    subject = db.Column(db.String(100), nullable=False)
    teacher = db.Column(db.String(100), nullable=False)
    room = db.Column(db.String(20), nullable=False)
    year = db.Column(db.Integer, nullable=False)

class Organization(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    code = db.Column(db.String(20), unique=True, nullable=False)
    admin_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    description = db.Column(db.Text)
    location = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, default=datetime.now)
    is_active = db.Column(db.Boolean, default=True)

class StudentWallet(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.String(20), nullable=False)
    balance = db.Column(db.Float, default=0.0)
    created_at = db.Column(db.DateTime, default=datetime.now)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class WalletTransaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.String(20), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    transaction_type = db.Column(db.String(20), nullable=False)  # credit, debit
    description = db.Column(db.String(200), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.now)

class LibraryBook(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    author = db.Column(db.String(100), nullable=False)
    isbn = db.Column(db.String(20), unique=True)
    price = db.Column(db.Float, nullable=False)
    category = db.Column(db.String(50), nullable=False)
    stock = db.Column(db.Integer, default=1)
    description = db.Column(db.Text)
    image_url = db.Column(db.String(500))

class LibraryPurchase(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.String(20), nullable=False)
    book_id = db.Column(db.Integer, db.ForeignKey('library_book.id'), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    purchase_date = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(20), default='completed')

class Reward(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.String(20), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    reason = db.Column(db.String(200), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.now)
    is_redeemed = db.Column(db.Boolean, default=False)

class Document(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    application_id = db.Column(db.Integer, db.ForeignKey('application.id', ondelete='CASCADE'), nullable=False)
    filename = db.Column(db.String(255), nullable=False)
    original_filename = db.Column(db.String(255), nullable=False)
    file_path = db.Column(db.String(500), nullable=False)
    file_type = db.Column(db.String(50), nullable=False)
    file_size = db.Column(db.Integer, nullable=False)
    document_type = db.Column(db.String(50), nullable=False)  # photo, marksheet, id_proof, additional_docs
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(20), default='active')  # active, deleted
    
    __table_args__ = (
        db.Index('idx_application_document_type', 'application_id', 'document_type'),
    )

class Test(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.now)
    start_time = db.Column(db.DateTime, nullable=False)
    end_time = db.Column(db.DateTime, nullable=False)
    duration_minutes = db.Column(db.Integer, nullable=False)
    max_attempts = db.Column(db.Integer, default=1)
    is_active = db.Column(db.Boolean, default=True)

class Question(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    test_id = db.Column(db.Integer, db.ForeignKey('test.id'), nullable=False)
    question_text = db.Column(db.Text, nullable=False)
    question_type = db.Column(db.String(20), nullable=False)  # multiple_choice, true_false, essay
    options = db.Column(db.Text)  # JSON string for multiple choice options
    correct_answer = db.Column(db.Text, nullable=False)
    points = db.Column(db.Integer, default=1)
    order = db.Column(db.Integer, default=0)

class TestAttempt(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    test_id = db.Column(db.Integer, db.ForeignKey('test.id'), nullable=False)
    student_id = db.Column(db.String(20), nullable=False)
    started_at = db.Column(db.DateTime, default=datetime.utcnow)
    submitted_at = db.Column(db.DateTime)
    score = db.Column(db.Float, default=0.0)
    total_points = db.Column(db.Float, default=0.0)
    is_submitted = db.Column(db.Boolean, default=False)

class Answer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    attempt_id = db.Column(db.Integer, db.ForeignKey('test_attempt.id'), nullable=False)
    question_id = db.Column(db.Integer, db.ForeignKey('question.id'), nullable=False)
    answer_text = db.Column(db.Text)
    is_correct = db.Column(db.Boolean, default=False)
    points_earned = db.Column(db.Float, default=0.0)

class FaceDetection(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.String(20), nullable=False)
    coordinates = db.Column(db.Text)  # JSON string for coordinates
    detected_at = db.Column(db.DateTime, default=datetime.utcnow)
    confidence = db.Column(db.Float, default=0.0)
    image_path = db.Column(db.String(500))

# Role-based access control decorators
def admin_required(f):
    @functools.wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        if session.get('role') != 'admin':
            flash('Access denied. Admin privileges required.')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def student_required(f):
    @functools.wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to continue')
            return redirect(url_for('login'))

        user = User.query.get(session['user_id'])
        if not user:
            session.clear()
            flash('Session expired. Please log in again')
            return redirect(url_for('login'))

        if user.role != 'student':
            flash('Access denied. Student privileges required.')
            return redirect(url_for('login'))

        # Store user in g for access in the view
        g.user = user
        return f(*args, **kwargs)
    return decorated_function

def login_required(f):
    @functools.wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def get_dropout_recommendations(risk_score, attendance, gpa):
    """Generate personalized recommendations based on risk factors"""
    recommendations = []
    
    if attendance < 75:
        recommendations.append("Improve attendance - attend classes regularly")
    if gpa < 6.0:
        recommendations.append("Focus on academics - seek tutoring or study groups")
    if risk_score > 0.8:
        recommendations.append("Schedule counseling session")
        recommendations.append("Consider academic support programs")
    
    return recommendations

# Routes
@app.route('/')
def index():
    return render_template('home.html')

@app.route('/home')
def home():
    return render_template('home.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        user = User.query.filter_by(email=email).first()
        
        if user and check_password_hash(user.password_hash, password):
            session['user_id'] = user.id
            session['username'] = user.username
            session['role'] = user.role
            if user.role == 'student':
                return redirect(url_for('organization_selection'))
            else:
                return redirect(url_for('dashboard'))
        else:
            flash('Invalid email or password')
    
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        role = request.form['role']
        
        if User.query.filter_by(username=username).first():
            flash('Username already exists')
            return render_template('register.html')
        
        user = User(
            username=username,
            email=email,
            password_hash=generate_password_hash(password),
            role=role
        )
        db.session.add(user)
        db.session.flush()  # Get the user ID
        
        # If admin, create organization automatically
        if role == 'admin':
            org_name = request.form.get('organization_name', f"{username}'s Institution")
            org_code = request.form.get('organization_code', f"{username.upper()}001")
            org_description = request.form.get('organization_description', 'Educational Institution')
            org_location = request.form.get('organization_location', 'Location not specified')
            
            organization = Organization(
                name=org_name,
                code=org_code,
                admin_id=user.id,
                description=org_description,
                location=org_location
            )
            db.session.add(organization)
        
        db.session.commit()
        
        flash('Registration successful')
        return redirect(url_for('login'))
    
    return render_template('register.html')

@app.route('/dashboard')
@admin_required
def dashboard():
    # Get real-time dashboard statistics
    total_students = Student.query.count()
    active_students = Student.query.filter_by(status='active').count()
    total_applications = Application.query.count()
    pending_applications = Application.query.filter_by(status='pending').count()
    approved_applications = Application.query.filter_by(status='approved').count()
    
    # Revenue data
    total_revenue = db.session.query(db.func.sum(Fee.amount)).scalar() or 0
    monthly_revenue = db.session.query(db.func.sum(Fee.amount)).filter(
        Fee.payment_date >= datetime.now().replace(day=1)
    ).scalar() or 0
    
    # Hostel data
    hostel_occupancy = db.session.query(db.func.sum(Hostel.occupied)).scalar() or 0
    total_capacity = db.session.query(db.func.sum(Hostel.capacity)).scalar() or 1
    occupancy_rate = (hostel_occupancy / total_capacity) * 100 if total_capacity > 0 else 0
    
    # Recent activities
    recent_fees = Fee.query.order_by(Fee.payment_date.desc()).limit(5).all()
    recent_admissions = Student.query.order_by(Student.admission_date.desc()).limit(5).all()
    recent_applications = Application.query.order_by(Application.submitted_at.desc()).limit(5).all()
    
    # Risk analysis - calculate dropout risk for students
    students = Student.query.all()
    high_risk_students = 0
    dropout_predictions = []
    
    for student in students:
        # Calculate risk score based on attendance, GPA, and payment history
        attendance_risk = max(0, (75 - student.attendance_percentage) / 75) if student.attendance_percentage < 75 else 0
        gpa_risk = max(0, (6.0 - student.gpa) / 6.0) if student.gpa < 6.0 else 0
        
        # Check payment history
        recent_fees_count = Fee.query.filter_by(student_id=student.student_id).count()
        payment_risk = 0.3 if recent_fees_count == 0 else 0
        
        risk_score = (attendance_risk * 0.4 + gpa_risk * 0.4 + payment_risk * 0.2)
        student.risk_score = risk_score
        
        if risk_score > 0.7:
            high_risk_students += 1
            dropout_predictions.append({
                'student_id': student.student_id,
                'name': student.name,
                'risk_score': risk_score,
                'attendance': student.attendance_percentage,
                'gpa': student.gpa,
                'recommendations': get_dropout_recommendations(risk_score, student.attendance_percentage, student.gpa)
            })
    
    # Course-wise statistics
    course_stats = db.session.query(
        Student.course, 
        db.func.count(Student.id).label('count'),
        db.func.avg(Student.gpa).label('avg_gpa')
    ).group_by(Student.course).all()
    
    return render_template('dashboard.html',
                         total_students=total_students,
                         active_students=active_students,
                         total_applications=total_applications,
                         pending_applications=pending_applications,
                         approved_applications=approved_applications,
                         total_revenue=total_revenue,
                         monthly_revenue=monthly_revenue,
                         occupancy_rate=occupancy_rate,
                         recent_fees=recent_fees,
                         recent_admissions=recent_admissions,
                         recent_applications=recent_applications,
                         high_risk_students=high_risk_students,
                         dropout_predictions=dropout_predictions,
                         course_stats=course_stats)

@app.route('/admissions')
@admin_required
def admissions():
    students = Student.query.all()
    return render_template('admissions.html', students=students)

@app.route('/admissions/new', methods=['GET', 'POST'])
@admin_required
def new_admission():
    
    if request.method == 'POST':
        # Generate unique student ID
        student_id = f"STU{datetime.now().strftime('%Y%m%d')}{random.randint(1000, 9999)}"
        
        student = Student(
            student_id=student_id,
            name=request.form['name'],
            email=request.form['email'],
            phone=request.form['phone'],
            course=request.form['course'],
            year=int(request.form['year'])
        )
        
        db.session.add(student)
        db.session.commit()
        
        flash(f'Student {student_id} admitted successfully!')
        return redirect(url_for('admissions'))
    
    return render_template('new_admission.html')

@app.route('/fees')
@admin_required
def fees():
    fees = Fee.query.order_by(Fee.payment_date.desc()).all()
    return render_template('fees.html', fees=fees)

@app.route('/fees/pay', methods=['GET', 'POST'])
@admin_required
def pay_fee():
    
    if request.method == 'POST':
        student_id = request.form['student_id']
        amount = float(request.form['amount'])
        fee_type = request.form['fee_type']
        
        # Generate receipt number
        receipt_number = f"RCP{datetime.now().strftime('%Y%m%d%H%M%S')}"
        
        fee = Fee(
            student_id=student_id,
            amount=amount,
            fee_type=fee_type,
            receipt_number=receipt_number
        )
        
        db.session.add(fee)
        db.session.commit()
        
        flash(f'Fee payment recorded! Receipt: {receipt_number}')
        return redirect(url_for('fees'))
    
    students = Student.query.filter_by(status='active').all()
    return render_template('pay_fee.html', students=students)

@app.route('/hostel')
@admin_required
def hostel():
    rooms = Hostel.query.all()
    return render_template('hostel.html', rooms=rooms)

@app.route('/hostel/allocate', methods=['GET', 'POST'])
@admin_required
def allocate_hostel():
    
    if request.method == 'POST':
        student_id = request.form['student_id']
        room_number = request.form['room_number']
        
        room = Hostel.query.filter_by(room_number=room_number).first()
        student = Student.query.filter_by(student_id=student_id).first()
        
        if room and room.occupied < room.capacity:
            # Update room occupancy
            current_occupants = json.loads(room.student_ids) if room.student_ids else []
            current_occupants.append(student_id)
            room.student_ids = json.dumps(current_occupants)
            room.occupied = len(current_occupants)
            
            if room.occupied >= room.capacity:
                room.status = 'occupied'
            
            db.session.commit()
            flash(f'Student {student_id} allocated to room {room_number}')
        else:
            flash('Room is full or does not exist')
        
        return redirect(url_for('hostel'))
    
    students = Student.query.filter_by(status='active').all()
    available_rooms = Hostel.query.filter(Hostel.occupied < Hostel.capacity).all()
    
    return render_template('allocate_hostel.html', students=students, rooms=available_rooms)

@app.route('/exams')
@admin_required
def exams():
    exams = Exam.query.all()
    return render_template('exams.html', exams=exams)

@app.route('/attendance')
@login_required
def attendance():
    # Admin view - show all attendance records
    if session.get('role') == 'admin':
        attendance_records = Attendance.query.order_by(Attendance.date.desc()).limit(100).all()
        return render_template('attendance.html', attendance=attendance_records, admin_view=True)
    else:
        # Student view - show only their attendance
        student_id = 'STU2024001'  # In real app, get from session
        attendance_records = Attendance.query.filter_by(student_id=student_id).order_by(Attendance.date.desc()).all()
        return render_template('attendance.html', attendance=attendance_records, student_view=True)

@app.route('/timetable')
@login_required
def timetable():
    timetable = Timetable.query.order_by(Timetable.day, Timetable.time_slot).all()
    return render_template('timetable.html', timetable=timetable)

@app.route('/analytics')
@admin_required
def analytics():
    # Risk analysis data
    students = Student.query.all()
    risk_data = []
    for student in students:
        risk_data.append({
            'student_id': student.student_id,
            'name': student.name,
            'risk_score': student.risk_score,
            'attendance': student.attendance_percentage,
            'gpa': student.gpa
        })
    
    return render_template('analytics.html', risk_data=risk_data)

@app.route('/chatbot')
@login_required
def chatbot():
    return render_template('chatbot.html')

@app.route('/api/chat', methods=['POST'])
def chat_api():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    message = request.json.get('message', '').lower()
    user_role = session.get('role', 'student')
    user_id = session['user_id']
    
    # Get user-specific data for personalized responses
    user = User.query.get(user_id)
    student = None
    if user_role == 'student':
        student = Student.query.filter_by(email=user.email).first()
    
    # Enhanced chatbot responses based on role and context
    if user_role == 'admin':
        # Get real-time data for admin
        total_students = Student.query.count()
        pending_applications = Application.query.filter_by(status='pending').count()
        total_revenue = db.session.query(db.func.sum(Fee.amount)).filter_by(status='paid').scalar() or 0
        
        responses = {
            'dashboard': f'Your admin dashboard shows real-time statistics: {total_students} students, {pending_applications} pending applications, and ₹{total_revenue:,.2f} total revenue.',
            'students': f'You can view all {total_students} student details, attendance records, and academic performance in the Students section.',
            'applications': f'There are {pending_applications} pending applications waiting for your review in the Applications section.',
            'revenue': f'Total revenue collected: ₹{total_revenue:,.2f}. Revenue data is displayed in the dashboard with monthly and total revenue figures.',
            'attendance': 'Student attendance is tracked in real-time. You can view detailed reports and analytics in the Attendance section.',
            'analytics': 'Analytics section provides insights into student performance, dropout predictions, and system health metrics.',
            'hostel': 'Hostel management allows you to allocate rooms, track occupancy rates, and manage hostel applications.',
            'fees': 'Fee collection and payment tracking is available in the Fees section with real-time payment status.',
            'exams': 'Exam management includes creating test schedules, uploading questions, and tracking student performance.',
            'help': 'I can help you with student management, applications, analytics, revenue tracking, and system administration.'
        }
    else:
        # Get student-specific data
        student_data = {}
        if student:
            student_data = {
                'attendance': student.attendance,
                'gpa': student.gpa,
                'fees_paid': student.total_fees_paid,
                'course': student.course,
                'name': student.name
            }
        
        responses = {
            'fee': f'You can pay your fees online through the payment gateway. Your current balance: ₹{student_data.get("fees_paid", 0):,.2f}',
            'hostel': 'Hostel allocation is done on a first-come, first-served basis. Use the interactive map to select your preferred hostel.',
            'exam': 'Exam schedules are available in the timetable section. You can also take online tests assigned by your admin.',
            'attendance': f'Your current attendance: {student_data.get("attendance", 0)}%. Minimum 75% is required to appear for exams.',
            'admission': 'New admissions are processed through the admissions portal. Upload your documents for faster processing.',
            'wallet': 'Your digital wallet allows you to pay fees and purchase books from the library. Check your balance in the wallet section.',
            'library': 'The digital library has books available for purchase using your wallet balance. Browse the catalog in the library section.',
            'profile': 'Update your profile information in the Profile section. Keep your contact details updated.',
            'gpa': f'Your current GPA: {student_data.get("gpa", 0)}. Focus on improving your academic performance.',
            'help': 'I can help you with fees, hostel, exams, attendance, wallet, library, and general queries.'
        }
    
    # Check for specific keywords and provide contextual responses
    response = "I'm here to help! Please ask me about any of the available features."
    
    for keyword, answer in responses.items():
        if keyword in message:
            response = answer
            break
    
    # Add dynamic responses based on context
    if 'time' in message or 'date' in message:
        response = f"Current time is {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    elif 'weather' in message:
        response = "I don't have access to weather information, but I can help you with academic matters!"
    elif 'hello' in message or 'hi' in message:
        if user_role == 'admin':
            response = f"Hello! Welcome to the College ERP admin panel. How can I assist you with system management today?"
        else:
            response = f"Hello {student_data.get('name', 'there')}! Welcome to your student portal. How can I help you today?"
    elif 'how are you' in message:
        response = "I'm doing great! I'm here to help you with all your academic and administrative needs. What can I assist you with?"
    elif 'thank' in message:
        response = "You're welcome! I'm always here to help. Is there anything else you'd like to know?"
    elif 'goodbye' in message or 'bye' in message:
        response = "Goodbye! Have a great day and feel free to come back anytime you need help!"
    elif 'status' in message:
        if user_role == 'admin':
            response = f"System status: All systems operational. {total_students} students, {pending_applications} pending applications."
        else:
            response = f"Your status: {student_data.get('attendance', 0)}% attendance, {student_data.get('gpa', 0)} GPA, ₹{student_data.get('fees_paid', 0):,.2f} fees paid."
    elif 'problem' in message or 'issue' in message:
        response = "I understand you're facing an issue. Please describe the problem in detail, and I'll help you resolve it or direct you to the right resources."
    elif 'contact' in message:
        response = "For technical support, contact the IT department. For academic queries, contact your course coordinator. For administrative issues, contact the admin office."
    elif 'deadline' in message:
        response = "Check the important dates section in your dashboard for upcoming deadlines. You can also view exam schedules and fee payment deadlines there."
    elif 'library' in message and 'book' in message:
        response = "You can search for books in the digital library, check availability, and purchase them using your wallet balance. Some books may also be available for free download."
    elif 'payment' in message:
        response = "You can make payments through the secure payment gateway. All major credit cards, debit cards, and UPI are accepted. Your payment history is available in the wallet section."
    elif 'grade' in message or 'result' in message:
        response = "Your grades and results are available in the academic section. You can view your GPA, individual subject marks, and overall performance there."
    elif 'schedule' in message:
        response = "Your class schedule, exam timetable, and important dates are available in the timetable section. You can also set reminders for important events."
    elif 'notification' in message:
        response = "You'll receive notifications for important updates, exam schedules, fee reminders, and system announcements. Check your notification center regularly."
    elif 'password' in message or 'login' in message:
        response = "For password reset or login issues, contact the IT support team. They can help you regain access to your account securely."
    elif 'emergency' in message:
        response = "For emergencies, contact the campus security at +91-XXX-XXXX-XXXX or visit the admin office immediately. Your safety is our priority."
    
    # Add some personality and helpful suggestions
    if response == "I'm here to help! Please ask me about any of the available features.":
        if user_role == 'admin':
            response = "I'm here to help! You can ask me about student management, applications, analytics, revenue tracking, or any other administrative tasks."
        else:
            response = "I'm here to help! You can ask me about fees, hostel, exams, attendance, your wallet, library, or any other student-related queries."
    
    return jsonify({'response': response})

@app.route('/api/dashboard_data')
def dashboard_data():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    
    # Real-time data for dashboard
    data = {
        'total_students': Student.query.count(),
        'active_students': Student.query.filter_by(status='active').count(),
        'total_revenue': db.session.query(db.func.sum(Fee.amount)).scalar() or 0,
        'hostel_occupancy': db.session.query(db.func.sum(Hostel.occupied)).scalar() or 0,
        'total_capacity': db.session.query(db.func.sum(Hostel.capacity)).scalar() or 1,
        'high_risk_students': Student.query.filter(Student.risk_score > 0.7).count()
    }
    
    return jsonify(data)

# Organization Selection Route
@app.route('/organization_selection')
def organization_selection():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    # Get real organizations from database
    organizations = Organization.query.filter_by(is_active=True).all()
    
    # Format organizations for template
    formatted_orgs = []
    for org in organizations:
        formatted_orgs.append({
            'id': org.id,
            'name': org.name,
            'code': org.code,
            'description': org.description,
            'location': org.location,
            'students': random.randint(5000, 20000),  # Simulated student count
            'courses': random.randint(10, 50)  # Simulated course count
        })
    
    return render_template('organization_selection.html', organizations=formatted_orgs)

# Student Portal Routes
@app.route('/student_portal')
@student_required
def student_portal():
    try:
        # g.user is set by student_required decorator
        user = g.user
        
        # Get or create student record
        student = Student.query.filter_by(email=user.email).first()
        if not student:
            try:
                # Create a default student record if none exists
                student = Student(
                    student_id=f"STU{datetime.now().strftime('%Y%m%d')}{random.randint(1000, 9999)}",
                    name=user.username,
                    email=user.email,
                    phone="+91 98765 43210",
                    course="Computer Science Engineering",
                    year=1,
                    gpa=8.5,
                    attendance_percentage=95.0
                )
                db.session.add(student)
                db.session.commit()
                app.logger.info(f'Created new student record for user {user.email}')
            except Exception as e:
                db.session.rollback()
                app.logger.error(f'Error creating student record: {str(e)}\n{traceback.format_exc()}')
                flash('Error creating student profile. Please contact support.')
                return redirect(url_for('login'))
        
        # Initialize statistics
        total_fees_paid = 0
        recent_payments = []
        current_attendance = 0
        current_gpa = 0
        achievements = 0
        points = 0
        stats_errors = []
        
        # Get total fees and recent payments
        try:
            total_fees_paid = db.session.query(db.func.sum(Fee.amount)).filter_by(student_id=student.student_id).scalar() or 0
            recent_payments = Fee.query.filter_by(student_id=student.student_id).order_by(Fee.payment_date.desc()).limit(3).all()
        except Exception as e:
            app.logger.error(f'Error calculating fees: {str(e)}')
            stats_errors.append('fees')
            # Initialize default values
            current_attendance = 0
            current_gpa = 0
            achievements = 0
            points = 0
            stats_errors = []

        # Calculate attendance
        try:
            attendance_records = Attendance.query.filter_by(student_id=student.student_id).all()
            if attendance_records:
                total_classes = len(attendance_records)
                present_classes = len([r for r in attendance_records if r.status == 'present'])
                current_attendance = (present_classes / total_classes * 100) if total_classes > 0 else 0
            else:
                current_attendance = 100  # Default for new students
        except Exception as e:
            app.logger.error(f'Error calculating attendance: {str(e)}')
            stats_errors.append('attendance')
            current_attendance = 0

        # Calculate GPA
        try:
            exam_records = Exam.query.filter_by(student_id=student.student_id).all()
            if exam_records:
                valid_marks = [e.marks for e in exam_records if e.marks is not None]
                current_gpa = sum(valid_marks) / len(valid_marks) if valid_marks else 0
            else:
                current_gpa = 0
        except Exception as e:
            app.logger.error(f'Error calculating GPA: {str(e)}')
            stats_errors.append('GPA')
            current_gpa = 0

        # Calculate achievements
        try:
            achievements = 0
            if current_attendance >= 95:
                achievements += 1
            if current_gpa >= 8.0:
                achievements += 1
            if total_fees_paid > 50000:
                achievements += 1
            if exam_records and len(exam_records) >= 5:
                achievements += 1
        except Exception as e:
            app.logger.error(f'Error calculating achievements: {str(e)}')
            stats_errors.append('achievements')
            achievements = 0

        # Calculate points
        try:
            points = int(current_attendance * 10 + current_gpa * 100 + total_fees_paid / 100)
        except Exception as e:
            app.logger.error(f'Error calculating points: {str(e)}')
            stats_errors.append('points')
            points = 0

        # If there were any errors, inform the user but don't block the page
        if stats_errors:
            flash(f'Some statistics are temporarily unavailable: {", ".join(stats_errors)}')
        
        # Prepare student data
        student_data = {
            'name': student.name,
            'student_id': student.student_id,
            'course': student.course,
            'year': student.year,
            'gpa': round(current_gpa, 2),
            'attendance': round(current_attendance, 1),
            'points': points,
            'achievements': achievements,
            'recent_payments': recent_payments,
            'total_fees_paid': total_fees_paid
        }
        
        return render_template('student_portal.html', student=student_data)

    except Exception as e:
        app.logger.error(f'Error calculating student statistics: {str(e)}\n{traceback.format_exc()}')
        # Return basic student data if statistics calculation fails
        student_data = {
            'name': student.name,
            'student_id': student.student_id,
            'course': student.course,
            'year': student.year,
            'gpa': 0.0,
            'attendance': 0.0,
            'points': 0,
            'achievements': 0,
            'recent_payments': [],
            'total_fees_paid': 0
        }
        flash('Some student statistics are temporarily unavailable')
        return render_template('student_portal.html', student=student_data)    except Exception as e:
        app.logger.error(f'Error in student portal: {str(e)}\n{traceback.format_exc()}')
        flash('An error occurred while loading the student portal. Please try again.')
        return redirect(url_for('login'))
    
    # Calculate real-time statistics
    total_fees_paid = db.session.query(db.func.sum(Fee.amount)).filter_by(student_id=student.student_id).scalar() or 0
    recent_payments = Fee.query.filter_by(student_id=student.student_id).order_by(Fee.payment_date.desc()).limit(3).all()
    
    # Get attendance records
    attendance_records = Attendance.query.filter_by(student_id=student.student_id).all()
    total_classes = len(attendance_records)
    present_classes = len([r for r in attendance_records if r.status == 'present'])
    current_attendance = (present_classes / total_classes * 100) if total_classes > 0 else 100
    
    # Get exam records
    exam_records = Exam.query.filter_by(student_id=student.student_id).all()
    current_gpa = sum([e.marks for e in exam_records]) / len(exam_records) if exam_records else 0
    
    # Calculate gamification points
    points = int(current_attendance * 10 + current_gpa * 100 + total_fees_paid / 100)
    
    # Calculate achievements
    achievements = 0
    if current_attendance >= 95:
        achievements += 1
    if current_gpa >= 8.0:
        achievements += 1
    if total_fees_paid > 50000:
        achievements += 1
    if len(exam_records) >= 5:
        achievements += 1
    
    # Get dropout risk prediction
    attendance_risk = max(0, (75 - current_attendance) / 75) if current_attendance < 75 else 0
    gpa_risk = max(0, (6.0 - current_gpa) / 6.0) if current_gpa < 6.0 else 0
    payment_risk = 0.3 if total_fees_paid == 0 else 0
    risk_score = (attendance_risk * 0.4 + gpa_risk * 0.4 + payment_risk * 0.2)
    
    student_data = {
        'name': student.name,
        'student_id': student.student_id,
        'course': student.course,
        'year': student.year,
        'gpa': round(current_gpa, 2),
        'attendance': round(current_attendance, 1),
        'points': points,
        'achievements': achievements,
        'risk_score': round(risk_score, 2),
        'recommendations': get_dropout_recommendations(risk_score, current_attendance, current_gpa),
        'recent_payments': recent_payments,
        'total_fees_paid': total_fees_paid
    }
    
    return render_template('student_portal.html', student=student_data)

def allowed_file(filename, allowed_extensions):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_extensions

def send_confirmation_email(application):
    """Send confirmation email to applicant"""
    try:
        subject = f"Application Received - {application.organization}"
        
        # Create email body
        body = f"""
        Dear {application.first_name} {application.last_name},

        Thank you for submitting your application to {application.organization}. 

        Application Details:
        - Application ID: {application.id}
        - Course: {application.course}
        - Submitted on: {application.submitted_at.strftime('%Y-%m-%d %H:%M:%S')}

        We have received your application and all required documents. Our team will review your application and get back to you shortly.

        Please keep this email for your records. If you have any questions, please contact our admissions office.

        Best regards,
        Admissions Team
        {application.organization}
        """
        
        msg = MIMEMultipart()
        msg['Subject'] = subject
        msg['From'] = "noreply@collegeerp.com"  # Replace with your email
        msg['To'] = application.email
        
        msg.attach(MIMEText(body, 'plain'))
        
        # Configure this in production with actual SMTP settings
        return True
    except Exception as e:
        app.logger.error(f"Error sending confirmation email: {str(e)}")
        return False

@app.route('/student/apply', methods=['GET', 'POST'])
@student_required
def student_application():
    if request.method == 'POST':
        app.logger.info('Starting application submission process')
        app.logger.debug(f'Form data: {request.form}')
        app.logger.debug(f'Files: {request.files}')
        try:
            # Validate file sizes before processing
            max_file_size = 5 * 1024 * 1024  # 5MB max per file
            required_fields = ['photo', 'marksheet', 'id_proof']
            allowed_extensions = {
                'photo': {'jpg', 'jpeg', 'png'},
                'marksheet': {'pdf', 'jpg', 'jpeg', 'png'},
                'id_proof': {'pdf', 'jpg', 'jpeg', 'png'},
                'additional_docs': {'pdf', 'jpg', 'jpeg', 'png'}
            }

            # Validate required files are present and have correct extensions
            for field in required_fields:
                if field not in request.files:
                    return jsonify({
                        'success': False,
                        'message': f'{field.replace("_", " ").title()} is required.'
                    }), 400
                
                file = request.files[field]
                if file.filename == '':
                    return jsonify({
                        'success': False,
                        'message': f'{field.replace("_", " ").title()} is required.'
                    }), 400
                
                if not file or not allowed_file(file.filename, allowed_extensions[field]):
                    return jsonify({
                        'success': False,
                        'message': f'Invalid file type for {field.replace("_", " ")}. Allowed types: {", ".join(allowed_extensions[field])}'
                    }), 400

            # Get selected organization from session
            selected_org = session.get('selectedOrganization', {})
            org_code = selected_org.get('code', 'TU')
            organization = selected_org.get('name', 'Tech University')
            
            # Get organization from database
            org = Organization.query.filter_by(code=org_code).first()
            if org:
                organization = org.name
            
            # Validate required form fields
            required_form_fields = ['first_name', 'last_name', 'email', 'phone', 
                                  'course', 'qualification', 'marks', 'date_of_birth', 
                                  'gender', 'address', 'previous_institution', 'passing_year']
            
            for field in required_form_fields:
                if field not in request.form or not request.form[field].strip():
                    return jsonify({
                        'success': False,
                        'message': f'{field.replace("_", " ").title()} is required.'
                    }), 400

            try:
                marks = float(request.form['marks'])
                if not (0 <= marks <= 100):
                    return jsonify({
                        'success': False,
                        'message': 'Marks must be between 0 and 100'
                    }), 400
            except ValueError:
                return jsonify({
                    'success': False,
                    'message': 'Invalid marks value'
                }), 400

            try:
                passing_year = int(request.form['passing_year'])
                current_year = datetime.now().year
                if not (2010 <= passing_year <= current_year):
                    return jsonify({
                        'success': False,
                        'message': f'Passing year must be between 2010 and {current_year}'
                    }), 400
            except ValueError:
                return jsonify({
                    'success': False,
                    'message': 'Invalid passing year'
                }), 400

            # Create application record with full error checking
            try:
                app.logger.debug('Creating application record with data:')
                app.logger.debug(f'User ID: {session.get("user_id")}')
                app.logger.debug(f'Organization: {organization}')
                app.logger.debug('Form data validation started')
                
                # Validate and convert date of birth
                try:
                    dob = datetime.strptime(request.form['date_of_birth'], '%Y-%m-%d').date()
                    app.logger.debug(f'Parsed DOB: {dob}')
                except (ValueError, KeyError) as e:
                    app.logger.error(f'DOB parsing error: {str(e)}')
                    return jsonify({
                        'success': False,
                        'message': 'Invalid date of birth format. Please use YYYY-MM-DD format.',
                        'error_type': 'validation_error'
                    }), 400

                application = Application(
                    user_id=session['user_id'],
                    organization=organization,
                    first_name=request.form['first_name'].strip(),
                    last_name=request.form['last_name'].strip(),
                    email=request.form['email'].strip(),
                    phone=request.form['phone'].strip(),
                    date_of_birth=dob,
                    gender=request.form['gender'].strip(),
                    address=request.form['address'].strip(),
                    course=request.form['course'],
                    qualification=request.form['qualification'],
                    marks=marks,
                    previous_institution=request.form['previous_institution'].strip(),
                    passing_year=int(request.form['passing_year']),
                    entrance_score=float(request.form.get('entrance_score', 0)),
                    status='pending',
                    submitted_at=datetime.utcnow()
                )
                
                app.logger.info('Application record created successfully')
                app.logger.debug(f'Application data: {application.__dict__}')
                
            except KeyError as ke:
                app.logger.error(f'Missing form field: {str(ke)}')
                return jsonify({
                    'success': False,
                    'message': f'Missing required field: {str(ke)}',
                    'error_type': 'validation_error'
                }), 400
            except (ValueError, TypeError) as ve:
                app.logger.error(f'Data validation error: {str(ve)}')
                return jsonify({
                    'success': False,
                    'message': f'Invalid data format: {str(ve)}',
                    'error_type': 'validation_error'
                }), 400
            except Exception as e:
                app.logger.error(f'Unexpected error creating application: {str(e)}\\n{traceback.format_exc()}')
                return jsonify({
                    'success': False,
                    'message': 'An unexpected error occurred while creating your application.',
                    'error_type': type(e).__name__,
                    'error_details': str(e)
                }), 500
            
            db.session.add(application)
            db.session.flush()  # Get the application ID
            
            # Handle document uploads
            document_fields = ['photo', 'marksheet', 'id_proof', 'additional_docs']
            uploaded_files = 0
            upload_errors = []
            
            # Ensure upload directory exists
            if not os.path.exists(app.config['UPLOAD_FOLDER']):
                os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
            
            for field_name in document_fields:
                if field_name in request.files:
                    files = request.files.getlist(field_name)
                    for file in files:
                        if file and file.filename:
                            try:
                                # Check file size during read
                                file_content = file.read()
                                if len(file_content) > max_file_size:
                                    upload_errors.append(f'File {file.filename} is too large. Maximum size is 5MB.')
                                    continue
                                
                                file.seek(0)  # Reset file pointer after reading
                                
                                filename = secure_filename(file.filename)
                                unique_filename = f"{application.id}_{field_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{filename}"
                                file_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
                                
                                # Ensure directory exists again (in case it was deleted)
                                os.makedirs(os.path.dirname(file_path), exist_ok=True)
                                
                                # Save file with error handling
                                try:
                                    file.save(file_path)
                                except Exception as e:
                                    app.logger.error(f"Error saving file {filename}: {str(e)}")
                                    upload_errors.append(f'Error saving file {filename}')
                                    continue
                                
                                # Verify file was saved
                                if not os.path.exists(file_path):
                                    upload_errors.append(f'Error verifying file {filename}')
                                    continue
                                
                                uploaded_files += 1
                                
                                document = Document(
                                    application_id=application.id,
                                    filename=unique_filename,
                                    original_filename=filename,
                                    file_path=file_path,
                                    file_type=file.content_type or 'application/octet-stream',
                                    file_size=os.path.getsize(file_path),
                                    document_type=field_name
                                )
                                db.session.add(document)
                                
                            except Exception as e:
                                app.logger.error(f"Error processing file {file.filename}: {str(e)}")
                                upload_errors.append(f'Error processing file {file.filename}')
                                continue
            
            if uploaded_files < len(required_fields):
                # Clean up any uploaded files
                for doc in Document.query.filter_by(application_id=application.id).all():
                    try:
                        if os.path.exists(doc.file_path):
                            os.remove(doc.file_path)
                    except Exception as e:
                        app.logger.error(f"Error cleaning up file {doc.file_path}: {str(e)}")
                
                db.session.rollback()
                return jsonify({
                    'success': False,
                    'message': 'Please ensure all required documents are uploaded correctly.',
                    'errors': upload_errors
                }), 400
            
            try:
                # Update application with additional fields
                application.date_of_birth = datetime.strptime(request.form['date_of_birth'], '%Y-%m-%d').date()
                application.gender = request.form['gender']
                application.address = request.form['address'].strip()
                application.previous_institution = request.form['previous_institution'].strip()
                application.passing_year = int(request.form['passing_year'])
                application.entrance_score = float(request.form['entrance_score']) if request.form.get('entrance_score') else None
                
                db.session.commit()
                
                # Send confirmation email (in background)
                try:
                    send_confirmation_email(application)
                except Exception as e:
                    app.logger.error(f"Error sending confirmation email: {str(e)}")
                
                return jsonify({
                    'success': True,
                    'message': 'Application submitted successfully! You will receive a confirmation email shortly.',
                    'application_id': application.id
                })
            except Exception as e:
                # Clean up any uploaded files
                for doc in Document.query.filter_by(application_id=application.id).all():
                    try:
                        if os.path.exists(doc.file_path):
                            os.remove(doc.file_path)
                    except Exception as cleanup_error:
                        app.logger.error(f"Error cleaning up file {doc.file_path}: {str(cleanup_error)}")
                
                db.session.rollback()
                app.logger.error(f"Error committing to database: {str(e)}")
                return jsonify({
                    'success': False,
                    'message': 'Error saving application to database. Please try again.',
                    'error': str(e)
                }), 500
            
        except Exception as e:
            app.logger.error(f"Error in student application: {str(e)}")
            if 'db' in locals():
                db.session.rollback()
            return jsonify({
                'success': False,
                'message': 'An unexpected error occurred. Please try again.',
                'error': str(e)
            }), 500
    
    return render_template('student_application.html')

def allowed_file(filename, allowed_extensions):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_extensions

@app.route('/student/fees')
@student_required
def student_fees():
    # Get student fee data
    student_id = 'STU2024001'  # In real app, get from session
    fees = Fee.query.filter_by(student_id=student_id).all()
    return render_template('pay_fee.html', fees=fees, student_view=True)

@app.route('/payment_gateway')
@login_required
def payment_gateway():
    return render_template('payment_gateway.html')

@app.route('/student/hostel')
@student_required
def student_hostel():
    # Get student hostel allocation
    student_id = 'STU2024001'  # In real app, get from session
    rooms = Hostel.query.all()
    student_room = None
    
    for room in rooms:
        if room.student_ids:
            occupants = json.loads(room.student_ids)
            if student_id in occupants:
                student_room = room
                break
    
    return render_template('hostel.html', rooms=rooms, student_room=student_room, student_view=True)

@app.route('/hostel_selection')
@student_required
def hostel_selection():
    return render_template('hostel_selection.html')

@app.route('/student/exams')
@student_required
def student_exams():
    student_id = 'STU2024001'  # In real app, get from session
    exams = Exam.query.filter_by(student_id=student_id).all()
    return render_template('exams.html', exams=exams, student_view=True)

@app.route('/student/timetable')
@student_required
def student_timetable():
    timetable = Timetable.query.order_by(Timetable.day, Timetable.time_slot).all()
    return render_template('timetable.html', timetable=timetable, student_view=True)

@app.route('/student/attendance')
@student_required
def student_attendance():
    student_id = 'STU2024001'  # In real app, get from session
    attendance_records = Attendance.query.filter_by(student_id=student_id).order_by(Attendance.date.desc()).all()
    return render_template('attendance.html', attendance=attendance_records, student_view=True)

@app.route('/student/chatbot')
@student_required
def student_chatbot():
    return render_template('chatbot.html', student_view=True)

@app.route('/student/profile')
@student_required
def student_profile():
    # Get student profile data
    student_data = {
        'name': 'John Smith',
        'student_id': 'STU2024001',
        'email': 'john.smith@college.edu',
        'phone': '+91 98765 43210',
        'course': 'Computer Science Engineering',
        'year': 3,
        'date_of_birth': '2002-05-15',
        'address': '123 Main Street, City, State',
        'admission_date': '2022-08-01',
        'gpa': 8.5,
        'attendance_percentage': 95.0
    }
    
    return render_template('student_profile.html', student=student_data)

# Admin Routes for Managing Applications
@app.route('/admin/applications')
@admin_required
def admin_applications():
    # Get real applications from database
    applications = Application.query.order_by(Application.submitted_at.desc()).all()
    
    # Format applications for template
    formatted_applications = []
    for app in applications:
        formatted_applications.append({
            'id': app.id,
            'name': f"{app.first_name} {app.last_name}",
            'email': app.email,
            'organization': app.organization,
            'course': app.course,
            'marks': app.marks,
            'status': app.status,
            'submitted_at': app.submitted_at
        })
    
    return render_template('admin_applications.html', applications=formatted_applications)

@app.route('/admin/applications/<int:app_id>/approve')
@admin_required
def approve_application(app_id):
    application = Application.query.get_or_404(app_id)
    
    # Update application status
    application.status = 'approved'
    application.reviewed_at = datetime.utcnow()
    application.reviewed_by = session['user_id']
    
    # Create student record
    student = Student(
        student_id=f"STU{datetime.now().strftime('%Y%m%d')}{random.randint(1000, 9999)}",
        name=f"{application.first_name} {application.last_name}",
        email=application.email,
        phone=application.phone,
        course=application.course,
        year=1,
        admission_date=datetime.utcnow(),
        status='active'
    )
    
    db.session.add(student)
    db.session.commit()
    
    flash(f'Application approved successfully! Student ID: {student.student_id}')
    return redirect(url_for('admin_applications'))

@app.route('/admin/applications/<int:app_id>/reject')
@admin_required
def reject_application(app_id):
    application = Application.query.get_or_404(app_id)
    
    # Update application status
    application.status = 'rejected'
    application.reviewed_at = datetime.utcnow()
    application.reviewed_by = session['user_id']
    
    db.session.commit()
    
    flash(f'Application rejected.')
    return redirect(url_for('admin_applications'))

# Google OAuth Routes
@app.route('/google-login')
def google_login():
    cfg = get_google_provider_cfg()
    authorization_endpoint = cfg["authorization_endpoint"]
    redirect_uri = "http://localhost:5000/auth/google/callback"

    request_uri = client.prepare_request_uri(
        authorization_endpoint,
        redirect_uri=redirect_uri,
        scope=["openid", "email", "profile"],
    )
    return redirect(request_uri)

@app.route('/auth/google/callback')
def google_callback():
    code = request.args.get("code")
    if not code:
        return "Missing authorization code", 400

    cfg = get_google_provider_cfg()
    token_endpoint = cfg["token_endpoint"]

    token_url, headers, body = client.prepare_token_request(
        token_endpoint,
        authorization_response=request.url,
        redirect_url=request.base_url,
        code=code,
    )

    token_response = requests.post(
        token_url,
        headers=headers,
        data=body,
        auth=(GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET),
    )

    try:
        token_response.raise_for_status()
    except Exception as e:
        return f"Token request failed: {e} - {token_response.text}", 502

    client.parse_request_body_response(json.dumps(token_response.json()))

    # Fetch user info
    userinfo_endpoint = cfg["userinfo_endpoint"]
    uri, headers, body = client.add_token(userinfo_endpoint)
    userinfo_response = requests.get(uri, headers=headers, data=body)

    try:
        userinfo_response.raise_for_status()
    except Exception as e:
        return f"Failed to fetch userinfo: {e} - {userinfo_response.text}", 502

    userinfo = userinfo_response.json()
    if not userinfo.get("email_verified"):
        return "Email not verified by Google", 400

    email = userinfo.get("email")
    name = userinfo.get("given_name") or userinfo.get("name")
    google_sub = userinfo.get("sub")
    
    # Check if user exists by email
    user = User.query.filter_by(email=email).first()
    if not user:
        # Determine role based on email domain or specific admin emails
        role = 'student'  # default role
        if email.endswith('@college.edu') or email == 'admin@college.edu':
            role = 'admin'
        
        # Create new user with unique username
        base_username = email.split('@')[0]
        username = base_username
        counter = 1
        while User.query.filter_by(username=username).first():
            username = f"{base_username}{counter}"
            counter += 1
        
        user = User(
            username=username,
            email=email,
            password_hash=generate_password_hash('google_oauth'),
            role=role
        )
        db.session.add(user)
        db.session.commit()
    
    session['user_id'] = user.id
    session['username'] = user.username
    session['role'] = user.role
    session['google_sub'] = google_sub
    session['email'] = email
    session['name'] = name
    
    if user.role == 'student':
        return redirect(url_for('organization_selection'))
    else:
        return redirect(url_for('dashboard'))

# Organization Management Routes
@app.route('/admin/create-organization', methods=['GET', 'POST'])
@admin_required
def create_organization():
    if request.method == 'POST':
        org = Organization(
            name=request.form['name'],
            code=request.form['code'],
            admin_id=session['user_id'],
            description=request.form['description'],
            location=request.form['location']
        )
        db.session.add(org)
        db.session.commit()
        flash('Organization created successfully!')
        return redirect(url_for('admin_organizations'))
    
    return render_template('create_organization.html')

@app.route('/admin/organizations')
@admin_required
def admin_organizations():
    organizations = Organization.query.filter_by(admin_id=session['user_id']).all()
    return render_template('admin_organizations.html', organizations=organizations)

@app.route('/join-organization/<org_code>')
@student_required
def join_organization(org_code):
    org = Organization.query.filter_by(code=org_code).first()
    if org:
        session['selectedOrganization'] = {
            'id': org.id,
            'name': org.name,
            'code': org.code
        }
        flash(f'Joined {org.name}!')
        return redirect(url_for('student_application'))
    else:
        flash('Invalid organization code!')
        return redirect(url_for('organization_selection'))

# Student Wallet Routes
@app.route('/student/wallet')
@student_required
def student_wallet():
    user = User.query.get(session['user_id'])
    student = Student.query.filter_by(email=user.email).first()
    
    if not student:
        flash('Student record not found!')
        return redirect(url_for('student_portal'))
    
    wallet = StudentWallet.query.filter_by(student_id=student.student_id).first()
    if not wallet:
        wallet = StudentWallet(student_id=student.student_id, balance=0.0)
        db.session.add(wallet)
        db.session.commit()
    
    transactions = WalletTransaction.query.filter_by(student_id=student.student_id).order_by(WalletTransaction.created_at.desc()).limit(10).all()
    rewards = Reward.query.filter_by(student_id=student.student_id, is_redeemed=False).all()
    
    return render_template('student_wallet.html', wallet=wallet, transactions=transactions, rewards=rewards)

@app.route('/student/wallet/add-money', methods=['POST'])
@student_required
def add_money_to_wallet():
    amount = float(request.form['amount'])
    user = User.query.get(session['user_id'])
    student = Student.query.filter_by(email=user.email).first()
    
    wallet = StudentWallet.query.filter_by(student_id=student.student_id).first()
    if not wallet:
        wallet = StudentWallet(student_id=student.student_id, balance=0.0)
        db.session.add(wallet)
    
    # Add money to wallet
    wallet.balance += amount
    
    # Create transaction record
    transaction = WalletTransaction(
        student_id=student.student_id,
        amount=amount,
        transaction_type='credit',
        description=f'Added money to wallet via payment gateway'
    )
    db.session.add(transaction)
    db.session.commit()
    
    flash(f'₹{amount} added to wallet successfully!')
    return redirect(url_for('student_wallet'))

# Library Routes
@app.route('/student/library')
@student_required
def student_library():
    books = LibraryBook.query.filter(LibraryBook.stock > 0).all()
    return render_template('student_library.html', books=books)

@app.route('/student/library/purchase/<int:book_id>')
@student_required
def purchase_book(book_id):
    user = User.query.get(session['user_id'])
    student = Student.query.filter_by(email=user.email).first()
    book = LibraryBook.query.get_or_404(book_id)
    
    wallet = StudentWallet.query.filter_by(student_id=student.student_id).first()
    if not wallet:
        wallet = StudentWallet(student_id=student.student_id, balance=0.0)
        db.session.add(wallet)
        db.session.commit()
    
    if wallet.balance >= book.price:
        # Deduct money from wallet
        wallet.balance -= book.price
        
        # Create purchase record
        purchase = LibraryPurchase(
            student_id=student.student_id,
            book_id=book.id,
            amount=book.price
        )
        db.session.add(purchase)
        
        # Update book stock
        book.stock -= 1
        
        # Create transaction record
        transaction = WalletTransaction(
            student_id=student.student_id,
            amount=book.price,
            transaction_type='debit',
            description=f'Purchased book: {book.title}'
        )
        db.session.add(transaction)
        db.session.commit()
        
        flash(f'Book "{book.title}" purchased successfully!')
    else:
        flash('Insufficient wallet balance!')
    
    return redirect(url_for('student_library'))

# Reward System
def check_and_award_cashback(student_id, fee_amount):
    """Award cashback for timely fee payments"""
    if fee_amount >= 10000:  # Minimum amount for cashback
        cashback_amount = fee_amount * 0.05  # 5% cashback
        reward = Reward(
            student_id=student_id,
            amount=cashback_amount,
            reason=f'Cashback for timely fee payment of ₹{fee_amount}'
        )
        db.session.add(reward)
        
        # Add to wallet
        wallet = StudentWallet.query.filter_by(student_id=student_id).first()
        if wallet:
            wallet.balance += cashback_amount
        else:
            wallet = StudentWallet(student_id=student_id, balance=cashback_amount)
            db.session.add(wallet)
        
        db.session.commit()
        return cashback_amount
    return 0


# Face Detection Routes
@app.route('/api/face-detection', methods=['POST'])
@login_required
def face_detection():
    if not OPENCV_AVAILABLE:
        return jsonify({'success': False, 'error': 'Face detection not available. OpenCV not installed.'})
    
    try:
        data = request.get_json()
        image_data = data.get('image')
        coordinates = data.get('coordinates', {})
        confidence = data.get('confidence', 0.0)
        
        # Decode base64 image
        image_bytes = base64.b64decode(image_data.split(',')[1])
        nparr = np.frombuffer(image_bytes, np.uint8)
        image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        # Save image
        image_filename = f"face_detection_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
        image_path = os.path.join(app.config['UPLOAD_FOLDER'], image_filename)
        cv2.imwrite(image_path, image)
        
        # Get student ID from session
        user = User.query.get(session['user_id'])
        student = Student.query.filter_by(email=user.email).first()
        student_id = student.student_id if student else 'UNKNOWN'
        
        # Save detection record
        detection = FaceDetection(
            student_id=student_id,
            coordinates=json.dumps(coordinates),
            confidence=confidence,
            image_path=image_path
        )
        db.session.add(detection)
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'Face detection recorded'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

# Test Management Routes
@app.route('/admin/tests')
@admin_required
def admin_tests():
    tests = Test.query.filter_by(created_by=session['user_id']).order_by(Test.created_at.desc()).all()
    return render_template('admin_tests.html', tests=tests)

@app.route('/admin/tests/create', methods=['GET', 'POST'])
@admin_required
def create_test():
    if request.method == 'POST':
        test = Test(
            title=request.form['title'],
            description=request.form['description'],
            created_by=session['user_id'],
            start_time=datetime.strptime(request.form['start_time'], '%Y-%m-%dT%H:%M'),
            end_time=datetime.strptime(request.form['end_time'], '%Y-%m-%dT%H:%M'),
            duration_minutes=int(request.form['duration_minutes']),
            max_attempts=int(request.form['max_attempts'])
        )
        db.session.add(test)
        db.session.flush()
        
        # Add questions
        question_texts = request.form.getlist('question_text')
        question_types = request.form.getlist('question_type')
        correct_answers = request.form.getlist('correct_answer')
        points = request.form.getlist('points')
        
        for i, (text, q_type, answer, point) in enumerate(zip(question_texts, question_types, correct_answers, points)):
            if text.strip():
                question = Question(
                    test_id=test.id,
                    question_text=text,
                    question_type=q_type,
                    correct_answer=answer,
                    points=int(point) if point else 1,
                    order=i
                )
                db.session.add(question)
        
        db.session.commit()
        flash('Test created successfully!')
        return redirect(url_for('admin_tests'))
    
    return render_template('create_test.html')

@app.route('/student/tests')
@student_required
def student_tests():
    tests = Test.query.filter(Test.is_active == True).all()
    return render_template('student_tests.html', tests=tests)

@app.route('/student/tests/<int:test_id>')
@student_required
def take_test(test_id):
    test = Test.query.get_or_404(test_id)
    questions = Question.query.filter_by(test_id=test_id).order_by(Question.order).all()
    return render_template('take_test.html', test=test, questions=questions)

@app.route('/student/face-detection')
@student_required
def face_detection_page():
    return render_template('face_detection.html')

@app.route('/student/tests/<int:test_id>/submit', methods=['POST'])
@student_required
def submit_test(test_id):
    test = Test.query.get_or_404(test_id)
    user = User.query.get(session['user_id'])
    student = Student.query.filter_by(email=user.email).first()
    
    # Create test attempt
    attempt = TestAttempt(
        test_id=test_id,
        student_id=student.student_id,
        submitted_at=datetime.utcnow(),
        is_submitted=True
    )
    db.session.add(attempt)
    db.session.flush()
    
    # Process answers
    total_points = 0
    earned_points = 0
    
    for question in Question.query.filter_by(test_id=test_id):
        answer_text = request.form.get(f'question_{question.id}', '')
        is_correct = answer_text.lower().strip() == question.correct_answer.lower().strip()
        points_earned = question.points if is_correct else 0
        
        answer = Answer(
            attempt_id=attempt.id,
            question_id=question.id,
            answer_text=answer_text,
            is_correct=is_correct,
            points_earned=points_earned
        )
        db.session.add(answer)
        
        total_points += question.points
        earned_points += points_earned
    
    attempt.total_points = total_points
    attempt.score = earned_points
    db.session.commit()
    
    flash(f'Test submitted! Your score: {earned_points}/{total_points}')
    return redirect(url_for('student_tests'))

# Student Management Routes
@app.route('/admin/students')
@admin_required
def admin_students():
    # Get all students with their details
    students = Student.query.all()
    
    # Format student data for template
    formatted_students = []
    for student in students:
        # Calculate risk score
        risk_score = 0
        if student.attendance < 75:
            risk_score += 0.3
        if student.gpa < 6.0:
            risk_score += 0.2
        if student.total_fees_paid == 0:
            risk_score += 0.3
        
        # Determine risk level
        if risk_score > 0.6:
            risk_level = 'high'
        elif risk_score > 0.3:
            risk_level = 'medium'
        else:
            risk_level = 'low'
        
        formatted_students.append({
            'id': student.id,
            'name': student.name,
            'student_id': student.student_id,
            'email': student.email,
            'course': student.course,
            'attendance': student.attendance,
            'gpa': student.gpa,
            'fees_paid': student.total_fees_paid,
            'status': 'active',
            'risk_level': risk_level,
            'risk_score': risk_score
        })
    
    return render_template('admin_students.html', students=formatted_students)

@app.route('/admin/students/<student_id>')
@admin_required
def student_details(student_id):
    student = Student.query.filter_by(student_id=student_id).first_or_404()
    
    # Calculate risk score and recommendations
    risk_score = 0
    recommendations = []
    
    if student.attendance < 75:
        risk_score += 0.3
        recommendations.append("Improve attendance to maintain academic standing")
    
    if student.gpa < 6.0:
        risk_score += 0.2
        recommendations.append("Focus on improving academic performance")
    
    if student.total_fees_paid == 0:
        risk_score += 0.3
        recommendations.append("Complete pending fee payments")
    
    # Format student data for template
    formatted_student = {
        'id': student.id,
        'name': student.name,
        'student_id': student.student_id,
        'email': student.email,
        'phone': student.phone,
        'course': student.course,
        'year': student.year,
        'attendance': student.attendance,
        'gpa': student.gpa,
        'fees_paid': student.total_fees_paid,
        'status': 'active',
        'dob': student.dob,
        'address': student.address,
        'risk_score': risk_score,
        'recommendations': recommendations
    }
    
    return render_template('admin_student_detail.html', student=formatted_student)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

# Initialize database and sample data
def init_db():
    with app.app_context():
        db.create_all()
        
        # Create admin user if not exists
        if not User.query.filter_by(username='admin').first():
            admin = User(
                username='admin',
                email='admin@college.edu',
                password_hash=generate_password_hash('admin123'),
                role='admin'
            )
            db.session.add(admin)
        
        # Create sample student user if not exists
        if not User.query.filter_by(username='student').first():
            student_user = User(
                username='student',
                email='student@college.edu',
                password_hash=generate_password_hash('student123'),
                role='student'
            )
            db.session.add(student_user)
        
        # Create sample hostel rooms
        if not Hostel.query.first():
            for floor in range(1, 4):
                for room in range(1, 21):
                    room_number = f"{floor}{room:02d}"
                    hostel = Hostel(
                        room_number=room_number,
                        floor=floor,
                        capacity=2,
                        occupied=random.randint(0, 2)
                    )
                    db.session.add(hostel)
        
        # Create sample timetable
        if not Timetable.query.first():
            days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']
            subjects = ['Mathematics', 'Physics', 'Chemistry', 'English', 'Computer Science']
            teachers = ['Dr. Smith', 'Prof. Johnson', 'Dr. Brown', 'Ms. Davis', 'Mr. Wilson']
            time_slots = ['09:00-10:00', '10:00-11:00', '11:00-12:00', '14:00-15:00', '15:00-16:00']
            
            for day in days:
                for i, time_slot in enumerate(time_slots):
                    timetable = Timetable(
                        day=day,
                        time_slot=time_slot,
                        subject=subjects[i % len(subjects)],
                        teacher=teachers[i % len(teachers)],
                        room=f"R{i+1:02d}",
                        year=1
                    )
                    db.session.add(timetable)
        
        # Create real colleges/organizations
        if not Organization.query.first():
            real_colleges = [
                Organization(
                    name='Indian Institute of Technology Delhi',
                    code='IITD001',
                    admin_id=1,
                    description='Premier engineering institute with world-class research facilities',
                    location='New Delhi, India'
                ),
                Organization(
                    name='Delhi University',
                    code='DU001',
                    admin_id=1,
                    description='One of India\'s largest and most prestigious universities',
                    location='New Delhi, India'
                ),
                Organization(
                    name='Jawaharlal Nehru University',
                    code='JNU001',
                    admin_id=1,
                    description='Leading research university known for social sciences and humanities',
                    location='New Delhi, India'
                ),
                Organization(
                    name='All India Institute of Medical Sciences',
                    code='AIIMS001',
                    admin_id=1,
                    description='Premier medical institute and hospital',
                    location='New Delhi, India'
                ),
                Organization(
                    name='National Institute of Technology Delhi',
                    code='NITD001',
                    admin_id=1,
                    description='Leading engineering institute with excellent placement records',
                    location='New Delhi, India'
                )
            ]
            for college in real_colleges:
                db.session.add(college)
        
        # Create sample library books
        if not LibraryBook.query.first():
            sample_books = [
                LibraryBook(
                    title='Introduction to Computer Science',
                    author='Dr. John Smith',
                    isbn='978-0123456789',
                    price=299.0,
                    category='Technology',
                    stock=50,
                    description='Comprehensive guide to computer science fundamentals'
                ),
                LibraryBook(
                    title='Data Structures and Algorithms',
                    author='Prof. Jane Doe',
                    isbn='978-0123456790',
                    price=399.0,
                    category='Technology',
                    stock=30,
                    description='Advanced algorithms and data structures'
                ),
                LibraryBook(
                    title='Machine Learning Fundamentals',
                    author='Dr. AI Researcher',
                    isbn='978-0123456791',
                    price=499.0,
                    category='Technology',
                    stock=25,
                    description='Introduction to machine learning concepts'
                ),
                LibraryBook(
                    title='Web Development Guide',
                    author='Full Stack Developer',
                    isbn='978-0123456792',
                    price=199.0,
                    category='Technology',
                    stock=40,
                    description='Complete guide to modern web development'
                ),
                LibraryBook(
                    title='Database Design Principles',
                    author='Database Expert',
                    isbn='978-0123456793',
                    price=349.0,
                    category='Technology',
                    stock=20,
                    description='Database design and optimization techniques'
                )
            ]
            for book in sample_books:
                db.session.add(book)
        
        db.session.commit()

if __name__ == '__main__':
    init_db()
    app.run(debug=True, host='0.0.0.0', port=5000)
