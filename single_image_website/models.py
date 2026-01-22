from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import uuid

db = SQLAlchemy()

def generate_uuid():
    return str(uuid.uuid4())

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='annotator')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    assignments = db.relationship('Assignment', backref='user', lazy='dynamic')
    annotations = db.relationship('Annotation', backref='user', lazy='dynamic')
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    def is_admin(self):
        return self.role == 'admin'

class Image(db.Model):
    __tablename__ = 'images'
    
    id = db.Column(db.String(50), primary_key=True)
    source = db.Column(db.Text, nullable=False)
    image_path = db.Column(db.Text, nullable=False)
    image_url = db.Column(db.Text)
    original_meta = db.Column(db.Text)
    annotation_count = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    assignments = db.relationship('Assignment', backref='image', lazy='dynamic')
    annotations = db.relationship('Annotation', backref='image', lazy='dynamic')

class Assignment(db.Model):
    __tablename__ = 'assignments'
    
    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    user_id = db.Column(db.String(36), db.ForeignKey('users.id'), nullable=False)
    image_id = db.Column(db.String(50), db.ForeignKey('images.id'), nullable=False)
    assigned_at = db.Column(db.DateTime, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime)
    status = db.Column(db.String(20), default='pending')
    
    __table_args__ = (
        db.UniqueConstraint('user_id', 'image_id', name='unique_user_image_assignment'),
    )

class Annotation(db.Model):
    __tablename__ = 'annotations'
    
    id = db.Column(db.String(36), primary_key=True, default=generate_uuid)
    image_id = db.Column(db.String(50), db.ForeignKey('images.id'), nullable=False)
    user_id = db.Column(db.String(36), db.ForeignKey('users.id'), nullable=False)
    assignment_id = db.Column(db.String(36), db.ForeignKey('assignments.id'), nullable=False)
    question = db.Column(db.Text)
    answer = db.Column(db.Text)
    is_approved = db.Column(db.Boolean)
    is_reported = db.Column(db.Boolean, default=False)
    annotation_pass = db.Column(db.Integer, default=1)
    annotated_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    assignment = db.relationship('Assignment', backref='annotation', uselist=False)
