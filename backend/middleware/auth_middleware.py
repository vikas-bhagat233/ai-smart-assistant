from functools import wraps
from flask import request, jsonify
from services.auth_service import AuthService
from models.user import UserModel
from datetime import datetime

auth_service = AuthService()
user_model = UserModel()

def token_required(f):
    """Decorator to protect routes that require authentication"""
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        
        # Get token from Authorization header
        auth_header = request.headers.get('Authorization')
        if auth_header and auth_header.startswith('Bearer '):
            token = auth_header.split(' ')[1]
        
        if not token:
            return jsonify({'error': 'Token is missing'}), 401
        
        # Verify token
        payload = auth_service.verify_token(token)
        if not payload:
            return jsonify({'error': 'Invalid or expired token'}), 401

        session_id = payload.get('session_id')
        if session_id:
            session = user_model.get_refresh_session(payload['user_id'], session_id)
            if not session:
                return jsonify({'error': 'Session not found'}), 401

            if session.get('revoked_at'):
                return jsonify({'error': 'Session has been revoked'}), 401

            expires_at = session.get('expires_at')
            if expires_at and expires_at <= datetime.utcnow():
                return jsonify({'error': 'Session has expired'}), 401
        
        # Add user info to request context
        request.user = payload
        
        return f(*args, **kwargs)
    
    return decorated