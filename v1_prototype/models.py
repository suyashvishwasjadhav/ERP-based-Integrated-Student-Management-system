from app import db
from datetime import datetime

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # 'admin' or 'student'
    email = db.Column(db.String(120), unique=True, nullable=False)

class Student(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.String(20), unique=True, nullable=False)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    department = db.Column(db.String(50))
    admission_date = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    fees = db.relationship('Fee', backref='student', lazy=True)
    hostel = db.relationship('HostelAllocation', backref='student', lazy=True)
    exams = db.relationship('Examination', backref='student', lazy=True)
    attendance = db.relationship('Attendance', backref='student', lazy=True)

class Fee(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    payment_date = db.Column(db.DateTime, default=datetime.utcnow)
    payment_type = db.Column(db.String(50))
    receipt_number = db.Column(db.String(50), unique=True)

class HostelAllocation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=False)
    room_number = db.Column(db.String(10), nullable=False)
    block = db.Column(db.String(10))
    allocation_date = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(20))  # 'occupied' or 'vacant'

class Examination(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=False)
    subject = db.Column(db.String(50))
    marks = db.Column(db.Float)
    exam_date = db.Column(db.DateTime)
    semester = db.Column(db.Integer)

class Attendance(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=False)
    date = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(20))  # 'present' or 'absent'
    subject = db.Column(db.String(50))