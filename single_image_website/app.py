#!/usr/bin/env python3
import os
import json
from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, Response
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from datetime import datetime
from functools import wraps

from models import db, User, Image, Assignment, Annotation

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')

database_url = os.environ.get('DATABASE_URL', 'sqlite:///single_image_annotations.db')
if database_url.startswith('postgres://'):
    database_url = database_url.replace('postgres://', 'postgresql+psycopg://', 1)
elif database_url.startswith('postgresql://') and '+' not in database_url:
    database_url = database_url.replace('postgresql://', 'postgresql+psycopg://', 1)
app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(user_id)

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin():
            flash('Admin access required')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        
        if user and user.check_password(password):
            login_user(user)
            return redirect(url_for('index'))
        flash('Invalid username or password')
    
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/')
@login_required
def index():
    if current_user.is_admin():
        return redirect(url_for('admin_dashboard'))
    return render_template('index.html')

@app.route('/api/stats')
@login_required
def get_stats():
    if current_user.is_admin():
        total_images = Image.query.count()
        total_annotations = Annotation.query.filter_by(is_approved=True).count()
        total_rejected = Annotation.query.filter_by(is_approved=False, is_reported=False).count()
        total_reported = Annotation.query.filter_by(is_reported=True).count()
        return jsonify({
            'total_images': total_images,
            'approved_images': total_annotations,
            'rejected_images': total_rejected,
            'reported_images': total_reported,
            'progress_percentage': round((total_annotations + total_rejected + total_reported) / total_images * 100, 1) if total_images > 0 else 0
        })
    
    total_assigned = Assignment.query.filter_by(user_id=current_user.id).count()
    completed = Assignment.query.filter_by(user_id=current_user.id, status='completed').count()
    pending = total_assigned - completed
    
    return jsonify({
        'total_images': total_assigned,
        'approved_images': completed,
        'rejected_images': 0,
        'reported_images': 0,
        'progress_percentage': round(completed / total_assigned * 100, 1) if total_assigned > 0 else 0
    })

@app.route('/api/next_image')
@login_required
def get_next_image():
    assignment = Assignment.query.filter_by(
        user_id=current_user.id,
        status='pending'
    ).first()
    
    if not assignment:
        return jsonify({'all_complete': True, 'message': 'All assigned images have been annotated!'})
    
    image = assignment.image
    
    return jsonify({
        'id': image.id,
        'assignment_id': assignment.id,
        'source': image.source,
        'image': image.image_url if image.image_url else image.image_path,
        'image_url': image.image_url,
        'metadata': json.loads(image.original_meta) if image.original_meta else {},
        'annotation': None
    })

@app.route('/api/image/<image_id>')
@login_required
def get_specific_image(image_id):
    assignment = Assignment.query.filter_by(
        user_id=current_user.id,
        image_id=image_id
    ).first()
    
    if not assignment:
        return jsonify({'error': 'Image not assigned to you'}), 403
    
    image = assignment.image
    annotation = Annotation.query.filter_by(assignment_id=assignment.id).first()
    
    result = {
        'id': image.id,
        'assignment_id': assignment.id,
        'source': image.source,
        'image': image.image_url if image.image_url else image.image_path,
        'image_url': image.image_url,
        'metadata': json.loads(image.original_meta) if image.original_meta else {},
        'annotation': None
    }
    
    if annotation:
        result['annotation'] = {
            'is_approved': annotation.is_approved,
            'is_reported': annotation.is_reported,
            'question': annotation.question,
            'answer': annotation.answer,
            'annotated_at': annotation.annotated_at.isoformat() if annotation.annotated_at else None
        }
    
    return jsonify(result)

@app.route('/api/annotate', methods=['POST'])
@login_required
def save_annotation():
    data = request.get_json()
    
    if not data or 'image_id' not in data or 'assignment_id' not in data:
        return jsonify({'error': 'Missing required fields'}), 400
    
    assignment = Assignment.query.filter_by(
        id=data['assignment_id'],
        user_id=current_user.id
    ).first()
    
    if not assignment:
        return jsonify({'error': 'Assignment not found'}), 404
    
    question = data.get('question', '').strip()
    answer = data.get('answer', '').strip()
    is_rejected = data.get('is_rejected', False)
    
    if question and answer:
        is_approved = True
    elif is_rejected:
        is_approved = False
    else:
        return jsonify({'error': 'Either provide Q&A or mark as rejected'}), 400
    
    existing = Annotation.query.filter_by(assignment_id=assignment.id).first()
    if existing:
        existing.question = question if question else None
        existing.answer = answer if answer else None
        existing.is_approved = is_approved
        existing.is_reported = False
        existing.annotated_at = datetime.utcnow()
    else:
        image = assignment.image
        annotation = Annotation(
            image_id=assignment.image_id,
            user_id=current_user.id,
            assignment_id=assignment.id,
            question=question if question else None,
            answer=answer if answer else None,
            is_approved=is_approved,
            is_reported=False,
            annotation_pass=image.annotation_count + 1
        )
        db.session.add(annotation)
        image.annotation_count += 1
    
    assignment.status = 'completed'
    assignment.completed_at = datetime.utcnow()
    db.session.commit()
    
    return jsonify({'success': True})

@app.route('/api/report', methods=['POST'])
@login_required
def report_image():
    data = request.get_json()
    
    if not data or 'image_id' not in data or 'assignment_id' not in data:
        return jsonify({'error': 'Missing required fields'}), 400
    
    assignment = Assignment.query.filter_by(
        id=data['assignment_id'],
        user_id=current_user.id
    ).first()
    
    if not assignment:
        return jsonify({'error': 'Assignment not found'}), 404
    
    existing = Annotation.query.filter_by(assignment_id=assignment.id).first()
    if existing:
        existing.is_reported = True
        existing.is_approved = False
        existing.annotated_at = datetime.utcnow()
    else:
        image = assignment.image
        annotation = Annotation(
            image_id=assignment.image_id,
            user_id=current_user.id,
            assignment_id=assignment.id,
            is_approved=False,
            is_reported=True,
            annotation_pass=image.annotation_count + 1
        )
        db.session.add(annotation)
        image.annotation_count += 1
    
    assignment.status = 'completed'
    assignment.completed_at = datetime.utcnow()
    db.session.commit()
    
    return jsonify({'success': True})

@app.route('/api/annotated_images')
@login_required
def get_annotated_images():
    assignments = Assignment.query.filter_by(
        user_id=current_user.id,
        status='completed'
    ).order_by(Assignment.completed_at.desc()).limit(50).all()
    
    images = []
    for assignment in assignments:
        image = assignment.image
        annotation = Annotation.query.filter_by(assignment_id=assignment.id).first()
        
        images.append({
            'id': image.id,
            'assignment_id': assignment.id,
            'source': image.source,
            'image': image.image_url if image.image_url else image.image_path,
            'annotation': {
                'is_approved': annotation.is_approved if annotation else None,
                'is_reported': annotation.is_reported if annotation else None,
                'question': annotation.question if annotation else None,
                'answer': annotation.answer if annotation else None,
                'annotated_at': annotation.annotated_at.isoformat() if annotation and annotation.annotated_at else None
            } if annotation else None
        })
    
    return jsonify(images)

@app.route('/api/leaderboard')
@login_required
def get_leaderboard():
    users = User.query.filter_by(role='annotator').all()
    leaderboard = []
    for user in users:
        approved_count = Annotation.query.filter_by(user_id=user.id, is_approved=True).count()
        leaderboard.append({
            'username': user.username,
            'approved_count': approved_count
        })
    leaderboard.sort(key=lambda x: x['approved_count'], reverse=True)
    for i, entry in enumerate(leaderboard):
        entry['rank'] = i + 1
    return jsonify(leaderboard)

@app.route('/api/my_stats')
@login_required
def get_my_stats():
    approved_count = Annotation.query.filter_by(user_id=current_user.id, is_approved=True).count()
    return jsonify({'approved_count': approved_count})

@app.route('/leaderboard')
@login_required
def leaderboard():
    return render_template('leaderboard.html')

@app.route('/admin')
@login_required
@admin_required
def admin_dashboard():
    total_images = Image.query.count()
    total_users = User.query.filter_by(role='annotator').count()
    total_assignments = Assignment.query.count()
    completed_assignments = Assignment.query.filter_by(status='completed').count()
    total_approved = Annotation.query.filter_by(is_approved=True).count()
    unassigned_images = Image.query.filter(~Image.id.in_(
        db.session.query(Assignment.image_id)
    )).count()
    
    users = User.query.filter_by(role='annotator').all()
    user_stats = []
    for user in users:
        assigned = Assignment.query.filter_by(user_id=user.id).count()
        completed = Assignment.query.filter_by(user_id=user.id, status='completed').count()
        
        submitted = Annotation.query.filter_by(user_id=user.id, is_approved=True).count()
        rejected = Annotation.query.filter_by(user_id=user.id, is_approved=False, is_reported=False).count()
        reported = Annotation.query.filter_by(user_id=user.id, is_reported=True).count()
        
        user_stats.append({
            'id': user.id,
            'username': user.username,
            'assigned': assigned,
            'completed': completed,
            'pending': assigned - completed,
            'submitted': submitted,
            'rejected': rejected,
            'reported': reported
        })
    
    return render_template('admin/dashboard.html',
        total_images=total_images,
        total_users=total_users,
        total_assignments=total_assignments,
        completed_assignments=completed_assignments,
        unassigned_images=unassigned_images,
        total_approved=total_approved,
        user_stats=user_stats
    )

@app.route('/admin/users')
@login_required
@admin_required
def admin_users():
    users = User.query.all()
    return render_template('admin/users.html', users=users)

@app.route('/admin/users/create', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_create_user():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        role = request.form.get('role', 'annotator')
        
        if User.query.filter_by(username=username).first():
            flash('Username already exists')
            return render_template('admin/create_user.html')
        
        user = User(username=username, role=role)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        
        flash(f'User {username} created successfully')
        return redirect(url_for('admin_users'))
    
    return render_template('admin/create_user.html')

@app.route('/admin/users/<user_id>/reset-password', methods=['POST'])
@login_required
@admin_required
def admin_reset_password(user_id):
    user = User.query.get(user_id)
    if not user:
        return jsonify({'error': 'User not found'}), 404
    
    new_password = request.form.get('new_password')
    if not new_password:
        flash('Password is required')
        return redirect(url_for('admin_users'))
    
    user.set_password(new_password)
    db.session.commit()
    
    flash(f'Password reset for {user.username}')
    return redirect(url_for('admin_users'))

@app.route('/admin/assignments')
@login_required
@admin_required
def admin_assignments():
    users = User.query.filter_by(role='annotator').all()
    unassigned_count = Image.query.filter(~Image.id.in_(
        db.session.query(Assignment.image_id)
    )).count()
    return render_template('admin/assignments.html', users=users, unassigned_count=unassigned_count)

@app.route('/admin/assignments/create', methods=['POST'])
@login_required
@admin_required
def admin_create_assignments():
    user_id = request.form.get('user_id')
    count = int(request.form.get('count', 100))
    
    user = User.query.get(user_id)
    if not user:
        flash('User not found')
        return redirect(url_for('admin_assignments'))
    
    unassigned_images = Image.query.filter(~Image.id.in_(
        db.session.query(Assignment.image_id)
    )).limit(count).all()
    
    created = 0
    for image in unassigned_images:
        assignment = Assignment(user_id=user_id, image_id=image.id)
        db.session.add(assignment)
        created += 1
    
    db.session.commit()
    flash(f'Assigned {created} images to {user.username}')
    return redirect(url_for('admin_assignments'))

@app.route('/admin/download')
@login_required
@admin_required
def admin_download_annotations():
    status_filter = request.args.get('status', 'approved')
    user_filter = request.args.get('user_id', 'all')
    
    query = db.session.query(Annotation, Image, User).join(
        Image, Annotation.image_id == Image.id
    ).join(User, Annotation.user_id == User.id)
    
    if status_filter == 'approved':
        query = query.filter(Annotation.is_approved == True)
    elif status_filter == 'rejected':
        query = query.filter(Annotation.is_approved == False, Annotation.is_reported == False)
    elif status_filter == 'reported':
        query = query.filter(Annotation.is_reported == True)
    
    if user_filter != 'all':
        query = query.filter(Annotation.user_id == user_filter)
    
    results = query.all()
    data = []
    for ann, img, user in results:
        data.append({
            'image_id': img.id,
            'image_url': img.image_url,
            'image_path': img.image_path,
            'source': img.source,
            'question': ann.question,
            'answer': ann.answer,
            'is_approved': ann.is_approved,
            'is_reported': ann.is_reported,
            'annotated_at': ann.annotated_at.isoformat() if ann.annotated_at else None,
            'username': user.username,
            'annotation_pass': ann.annotation_pass
        })
    
    response = Response(
        json.dumps(data, indent=2),
        mimetype='application/json',
        headers={'Content-Disposition': f'attachment;filename=annotations_{status_filter}.json'}
    )
    return response

def init_db():
    db.create_all()
    print("Database tables created")

def load_images_from_json():
    images_file = 'images.json'
    if not os.path.exists(images_file):
        print(f"No {images_file} found, skipping image load")
        return
    
    existing_count = Image.query.count()
    if existing_count > 0:
        print(f"Database already contains {existing_count} images")
        return
    
    print(f"Loading images from {images_file}...")
    with open(images_file, 'r') as f:
        data = json.load(f)
        for idx, img in enumerate(data.get('images', [])):
            image_id = f"{idx:06d}"
            image_url = img.get('image_url', '')
            
            image = Image(
                id=image_id,
                source=data.get('flickr_url', 'unknown'),
                image_path=image_url,
                image_url=image_url,
                original_meta=json.dumps({
                    'is_url': data.get('is_url', True),
                    'id_a': data.get('id_a'),
                    'cap_a': data.get('cap_a'),
                })
            )
            db.session.add(image)
    
    db.session.commit()
    print(f"Loaded {Image.query.count()} images")

if __name__ == '__main__':
    with app.app_context():
        init_db()
        load_images_from_json()
    
    app.run(debug=False, host='0.0.0.0', port=8080)
