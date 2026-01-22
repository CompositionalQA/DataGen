#!/usr/bin/env python3
"""
Script to create an admin user.

Usage:
    python create_admin.py <username> <password>
    
Example:
    python create_admin.py admin mysecretpassword
"""

import sys
import os

from app import app, db
from models import User

def create_admin(username, password):
    with app.app_context():
        db.create_all()
        
        existing = User.query.filter_by(username=username).first()
        if existing:
            print(f"User '{username}' already exists.")
            return False
        
        user = User(username=username, role='admin')
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        
        print(f"Admin user '{username}' created successfully.")
        return True

if __name__ == '__main__':
    if len(sys.argv) != 3:
        print("Usage: python create_admin.py <username> <password>")
        sys.exit(1)
    
    username = sys.argv[1]
    password = sys.argv[2]
    
    success = create_admin(username, password)
    sys.exit(0 if success else 1)
