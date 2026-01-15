#!/usr/bin/env python3
"""
Single Image Annotation Website
A Flask web application for annotating individual images with Q&A.
"""

import os
import json
import sqlite3
from flask import Flask, render_template, request, jsonify, g
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'your-secret-key-change-this'

# Configuration
DATABASE = 'single_image_annotations.db'
IMAGES_BASE_PATH = '.'

def get_db():
    """Get database connection."""
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DATABASE)
        db.row_factory = sqlite3.Row
    return db

@app.teardown_appcontext
def close_connection(exception):
    """Close database connection."""
    db = getattr(g, '_database', None)
    if db is not None:
        db.close()

def init_db():
    """Initialize the database with required tables."""
    with app.app_context():
        db = get_db()
        db.executescript('''
            CREATE TABLE IF NOT EXISTS images (
                id TEXT PRIMARY KEY,
                source TEXT NOT NULL,
                image_path TEXT NOT NULL,
                image_url TEXT,
                original_meta TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            
            CREATE TABLE IF NOT EXISTS annotations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                image_id TEXT NOT NULL,
                question TEXT,
                answer TEXT,
                is_approved BOOLEAN,
                is_reported BOOLEAN DEFAULT 0,
                annotated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (image_id) REFERENCES images (id)
            );
            
            CREATE INDEX IF NOT EXISTS idx_image_id ON annotations(image_id);
            CREATE INDEX IF NOT EXISTS idx_approved ON annotations(is_approved);
        ''')
        
        # Check if is_reported column exists, if not add it
        cursor = db.execute("PRAGMA table_info(annotations)")
        columns = [column[1] for column in cursor.fetchall()]
        
        if 'is_reported' not in columns:
            print("Adding is_reported column to annotations table...")
            db.execute('ALTER TABLE annotations ADD COLUMN is_reported BOOLEAN DEFAULT 0')
        
        db.commit()
        print("Database initialized successfully")

def load_images():
    """Load images from JSONL files into the database (extracting first image from pairs)."""
    db = get_db()
    
    # Check if data already loaded
    count = db.execute('SELECT COUNT(*) as count FROM images').fetchone()
    if count['count'] > 0:
        print(f"Database already contains {count['count']} images.")
        return
    
    print("Loading images into database...")
    
    # Load from pairs.jsonl and extract first image only
    pairs_file = os.path.join(IMAGES_BASE_PATH, 'images.json')
    print(f"Loading images from {pairs_file}")
    if os.path.exists(pairs_file):
        with open(pairs_file, 'r') as f:
            data = json.load(f)
            for line_num, line in enumerate(data['images']):

                try:
                    
                    # Generate a unique ID for this image
                    image_id = f"{line_num:06d}"
                    
                    # Extract first image URL
                    image_url = line.get('image_url', '')

                    # Store the image
                    db.execute('''
                        INSERT OR IGNORE INTO images 
                        (id, source, image_path, image_url, original_meta)
                        VALUES (?, ?, ?, ?, ?)
                    ''', (
                        image_id,
                        data.get('flickr_url', 'unknown'),
                        image_url,  # Store URL as path
                        image_url,
                        json.dumps({
                            'is_url': data.get('is_url', True),
                            'id_a': data.get('id_a'),
                            'cap_a': data.get('cap_a'),
                            'sim_text': data.get('sim_text'),
                            'sim_img': data.get('sim_img'),
                            'source': data.get('source', {})
                        })
                    ))
                except json.JSONDecodeError as e:
                    print(f"Error parsing line {line_num}: {e}")
                    continue
    else:
        print(f"File not found: {pairs_file}")

    db.commit()
    
    # Print summary
    count = db.execute('SELECT COUNT(*) as count FROM images').fetchone()
    print(f"Loaded {count['count']} images into database.")

@app.route('/')
def index():
    """Main annotation interface."""
    return render_template('index.html')

@app.route('/api/random_image')
def get_random_image():
    """Get a random image for annotation."""
    db = get_db()
    
    # Get a random image that hasn't been annotated yet
    image = db.execute('''
        SELECT i.* FROM images i
        LEFT JOIN annotations a ON i.id = a.image_id
        WHERE a.image_id IS NULL
        ORDER BY RANDOM()
        LIMIT 1
    ''').fetchone()
    
    # If all images have been annotated, return completion status
    if not image:
        return jsonify({'all_complete': True, 'message': 'All images have been annotated!'}), 200
    
    # Get existing annotation if any
    annotation = db.execute('''
        SELECT * FROM annotations
        WHERE image_id = ?
        ORDER BY annotated_at DESC
        LIMIT 1
    ''', (image['id'],)).fetchone()
    
    # Format image source
    if image['image_path'].startswith('http'):
        image_src = image['image_path']
    else:
        image_src = f"/api/image/{image['image_path']}"
    
    result = {
        'id': image['id'],
        'source': image['source'],
        'image': image_src,
        'image_url': image['image_url'],
        'metadata': json.loads(image['original_meta']) if image['original_meta'] else {},
        'annotation': None
    }
    
    if annotation:
        result['annotation'] = {
            'is_approved': bool(annotation['is_approved']) if annotation['is_approved'] is not None else None,
            'is_reported': bool(annotation['is_reported']) if annotation['is_reported'] is not None else None,
            'question': annotation['question'],
            'answer': annotation['answer'],
            'annotated_at': annotation['annotated_at']
        }
    
    return jsonify(result)

@app.route('/api/image/<image_id>')
def get_specific_image(image_id):
    """Get a specific image by ID."""
    try:
        db = get_db()
        
        # Get the image
        image = db.execute('''
            SELECT * FROM images WHERE id = ?
        ''', (image_id,)).fetchone()
        
        if not image:
            return jsonify({'error': 'Image not found'}), 404
        
        # Get existing annotation if any
        annotation = db.execute('''
            SELECT * FROM annotations WHERE image_id = ? 
            ORDER BY annotated_at DESC LIMIT 1
        ''', (image_id,)).fetchone()
        
        # Format image source
        if image['image_path'].startswith('http'):
            image_src = image['image_path']
        else:
            image_src = f"/api/image/{image['image_path']}"
        
        result = {
            'id': image['id'],
            'source': image['source'],
            'image': image_src,
            'image_url': image['image_url'],
            'metadata': json.loads(image['original_meta']) if image['original_meta'] else {},
            'annotation': None
        }
        
        if annotation:
            result['annotation'] = {
                'is_approved': bool(annotation['is_approved']) if annotation['is_approved'] is not None else None,
                'is_reported': bool(annotation['is_reported']) if annotation['is_reported'] is not None else None,
                'question': annotation['question'],
                'answer': annotation['answer'],
                'annotated_at': annotation['annotated_at']
            }
        
        return jsonify(result)
        
    except Exception as e:
        print(f"Error getting specific image: {e}")
        return jsonify({'error': 'Failed to get image'}), 500

@app.route('/api/annotate', methods=['POST'])
def save_annotation():
    """Save an annotation for an image."""
    data = request.get_json()
    
    if not data or 'image_id' not in data:
        return jsonify({'error': 'Missing image_id'}), 400
    
    image_id = data['image_id']
    question = data.get('question', '').strip()
    answer = data.get('answer', '').strip()
    is_rejected = data.get('is_rejected', False)
    
    # Auto-approve if Q&A is provided, otherwise reject if explicitly rejected
    if question and answer:
        is_approved = True
    elif is_rejected:
        is_approved = False
    else:
        return jsonify({'error': 'Either provide Q&A or mark as rejected'}), 400
    
    db = get_db()
    
    # Check if image exists
    image = db.execute('SELECT id FROM images WHERE id = ?', (image_id,)).fetchone()
    if not image:
        return jsonify({'error': 'Image not found'}), 404
    
    # Delete any existing annotations for this image_id to ensure uniqueness
    db.execute('DELETE FROM annotations WHERE image_id = ?', (image_id,))
    
    # Insert new annotation
    db.execute('''
        INSERT INTO annotations (image_id, is_approved, is_reported, question, answer)
        VALUES (?, ?, ?, ?, ?)
    ''', (image_id, is_approved, False, question if question else None, answer if answer else None))
    
    db.commit()
    
    return jsonify({'success': True})

@app.route('/api/report', methods=['POST'])
def report_image():
    """Report an image that won't load or has issues."""
    data = request.get_json()
    
    if not data or 'image_id' not in data:
        return jsonify({'error': 'Missing image_id'}), 400
    
    image_id = data['image_id']
    
    db = get_db()
    
    # Check if image exists
    image = db.execute('SELECT id FROM images WHERE id = ?', (image_id,)).fetchone()
    if not image:
        return jsonify({'error': 'Image not found'}), 404
    
    # Delete any existing annotations for this image_id to ensure uniqueness
    db.execute('DELETE FROM annotations WHERE image_id = ?', (image_id,))
    
    # Insert report annotation
    db.execute('''
        INSERT INTO annotations (image_id, is_approved, is_reported, question, answer)
        VALUES (?, ?, ?, ?, ?)
    ''', (image_id, False, True, None, None))
    
    db.commit()
    
    return jsonify({'success': True, 'message': 'Image reported successfully'})

@app.route('/api/stats')
def get_stats():
    """Get annotation statistics."""
    try:
        db = get_db()
        
        # Check if tables exist
        cursor = db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name IN ('images', 'annotations')")
        tables = [row[0] for row in cursor.fetchall()]
        
        if 'images' not in tables:
            return jsonify({
                'total_images': 0,
                'approved_images': 0,
                'rejected_images': 0,
                'reported_images': 0,
                'progress_percentage': 0
            })
        
        total_images = db.execute('SELECT COUNT(*) as count FROM images').fetchone()['count']
        
        if 'annotations' not in tables:
            return jsonify({
                'total_images': total_images,
                'approved_images': 0,
                'rejected_images': 0,
                'reported_images': 0,
                'progress_percentage': 0
            })
        
        approved_images = db.execute('SELECT COUNT(DISTINCT image_id) as count FROM annotations WHERE is_approved = 1').fetchone()['count']
        rejected_images = db.execute('SELECT COUNT(DISTINCT image_id) as count FROM annotations WHERE is_approved = 0 AND (is_reported = 0 OR is_reported IS NULL)').fetchone()['count']
        
        try:
            reported_images = db.execute('SELECT COUNT(DISTINCT image_id) as count FROM annotations WHERE is_reported = 1').fetchone()['count']
        except:
            reported_images = 0
            
        # Calculate total processed images
        total_processed = approved_images + rejected_images + reported_images
            
        return jsonify({
            'total_images': total_images,
            'approved_images': approved_images,
            'rejected_images': rejected_images,
            'reported_images': reported_images,
            'progress_percentage': round((total_processed / total_images) * 100, 1) if total_images > 0 else 0
        })
        
    except Exception as e:
        print(f"Error in get_stats: {e}")
        return jsonify({
            'total_images': 0,
            'approved_images': 0,
            'rejected_images': 0,
            'reported_images': 0,
            'progress_percentage': 0
        })

@app.route('/api/annotated_images')
def get_annotated_images():
    """Get annotated images for carousel display."""
    try:
        db = get_db()
        
        # Check if tables exist
        cursor = db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name IN ('images', 'annotations')")
        tables = [row[0] for row in cursor.fetchall()]
        
        if 'images' not in tables or 'annotations' not in tables:
            return jsonify([])
        
        results = db.execute('''
            SELECT DISTINCT i.id, i.source, i.image_path, i.image_url, i.original_meta,
                   a.is_approved, a.is_reported, a.question, a.answer, a.annotated_at
            FROM images i
            INNER JOIN annotations a ON i.id = a.image_id
            ORDER BY a.annotated_at DESC
            LIMIT 50
        ''').fetchall()
        
        images = []
        for row in results:
            image = {
                'id': row['id'],
                'source': row['source'],
                'image': row['image_path'],
                'meta': json.loads(row['original_meta']) if row['original_meta'] else {},
                'annotation': {
                    'is_approved': bool(row['is_approved']) if row['is_approved'] is not None else None,
                    'is_reported': bool(row['is_reported']) if row['is_reported'] is not None else None,
                    'question': row['question'],
                    'answer': row['answer'],
                    'annotated_at': row['annotated_at']
                }
            }
            images.append(image)
        
        return jsonify(images)
        
    except Exception as e:
        print(f"Error in get_annotated_images: {e}")
        return jsonify([])

@app.route('/api/export/all')
def api_export_all():
    """API endpoint to export all images as JSON data."""
    try:
        db = get_db()
        results = db.execute('''
            SELECT 
                i.*,
                a.is_approved,
                a.is_reported,
                a.question,
                a.answer,
                a.annotated_at
            FROM images i
            LEFT JOIN (
                SELECT a1.*
                FROM annotations a1
                INNER JOIN (
                    SELECT image_id, MAX(annotated_at) AS latest_annotated_at
                    FROM annotations
                    GROUP BY image_id
                ) a2
                ON a1.image_id = a2.image_id AND a1.annotated_at = a2.latest_annotated_at
            ) a ON i.id = a.image_id
            ORDER BY i.id
        ''').fetchall()
        
        all_images = []
        for row in results:
            image_data = {
                'id': row['id'],
                'image_url': row['image_url'],
                'annotation_status': {
                    'is_approved': bool(row['is_approved']) if row['is_approved'] is not None else None,
                    'is_reported': bool(row['is_reported']) if row['is_reported'] is not None else None,
                    'question': row['question'],
                    'answer': row['answer'],
                    'annotated_at': row['annotated_at']
                } if (row['is_approved'] is not None or row['is_reported'] is not None or 
                      row['question'] or row['answer']) else None
            }
            all_images.append(image_data)
        
        return jsonify(all_images)
    
    except Exception as e:
        print(f"Error in api_export_all: {e}")
        return jsonify({'error': str(e)}), 500

def cleanup_duplicates():
    """Remove duplicate annotations, keeping only the most recent one per image_id."""
    with app.app_context():
        db = get_db()
        
        duplicates_count = db.execute('''
            SELECT COUNT(*) - COUNT(DISTINCT image_id) as dup_count
            FROM annotations
        ''').fetchone()[0]
        
        if duplicates_count > 0:
            print(f"Found {duplicates_count} duplicate annotations. Cleaning up...")
            
            db.execute('''
                DELETE FROM annotations
                WHERE id NOT IN (
                    SELECT MAX(id)
                    FROM annotations
                    GROUP BY image_id
                )
            ''')
            
            db.commit()
            print(f"Cleaned up {duplicates_count} duplicate annotations")
        else:
            print("No duplicate annotations found")

if __name__ == '__main__':
    with app.app_context():
        init_db()
        load_images()
        cleanup_duplicates()
    
    app.run(debug=False, host='0.0.0.0', port=5000)
