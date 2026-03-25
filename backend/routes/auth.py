from flask import Blueprint, request, jsonify
from datetime import datetime
from services.auth_service import AuthService
from utils.validators import validate_email, validate_password, validate_username
from middleware.auth_middleware import token_required
from models.user import UserModel

auth_bp = Blueprint('auth', __name__)
auth_service = AuthService()
user_model = UserModel()

@auth_bp.route('/register', methods=['POST'])
def register():
    """Register a new user"""
    try:
        data = request.get_json()
        
        # Validate input
        username = data.get('username')
        email = data.get('email')
        password = data.get('password')
        security_question_key = data.get('security_question_key')
        security_answer = data.get('security_answer')
        
        if not username or not email or not password or not security_question_key or not security_answer:
            return jsonify({'error': 'Missing required fields'}), 400
        
        if not validate_username(username):
            return jsonify({'error': 'Username must be at least 3 characters'}), 400
        
        if not validate_email(email):
            return jsonify({'error': 'Invalid email format'}), 400
        
        if not validate_password(password):
            return jsonify({'error': 'Password must be at least 6 characters'}), 400
        
        # Register user
        user_agent = request.headers.get('User-Agent', '')
        ip_address = request.headers.get('X-Forwarded-For', request.remote_addr)

        result = auth_service.register_user(
            username,
            email,
            password,
            security_question_key=security_question_key,
            security_answer=security_answer,
            user_agent=user_agent,
            ip_address=ip_address
        )
        
        return jsonify({
            'message': 'Registration successful',
            'token': result['token'],
            'refresh_token': result['refresh_token'],
            'session_id': result['session_id'],
            'user': result['user']
        }), 201
        
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        print(f"Registration error: {e}")
        return jsonify({'error': 'Internal server error'}), 500


@auth_bp.route('/security-questions', methods=['GET'])
def get_security_questions():
    """Return available security questions"""
    return jsonify({'questions': auth_service.get_security_questions()}), 200

@auth_bp.route('/login', methods=['POST'])
def login():
    """Login user"""
    try:
        data = request.get_json()
        
        email = data.get('email')
        password = data.get('password')
        
        if not email or not password:
            return jsonify({'error': 'Email and password required'}), 400
        
        # Login user
        user_agent = request.headers.get('User-Agent', '')
        ip_address = request.headers.get('X-Forwarded-For', request.remote_addr)

        result = auth_service.login_user(
            email,
            password,
            user_agent=user_agent,
            ip_address=ip_address
        )
        
        return jsonify({
            'message': 'Login successful',
            'token': result['token'],
            'refresh_token': result['refresh_token'],
            'session_id': result['session_id'],
            'user': result['user']
        }), 200
        
    except ValueError as e:
        return jsonify({'error': str(e)}), 401
    except Exception as e:
        print(f"Login error: {e}")
        return jsonify({'error': 'Internal server error'}), 500


@auth_bp.route('/refresh', methods=['POST'])
def refresh_access_token():
    """Refresh access token using valid refresh token"""
    try:
        data = request.get_json() or {}
        refresh_token = data.get('refresh_token')

        if not refresh_token:
            return jsonify({'error': 'refresh_token is required'}), 400

        user_agent = request.headers.get('User-Agent', '')
        ip_address = request.headers.get('X-Forwarded-For', request.remote_addr)

        result = auth_service.refresh_access(
            refresh_token,
            user_agent=user_agent,
            ip_address=ip_address
        )

        return jsonify({
            'message': 'Token refreshed',
            'token': result['token'],
            'refresh_token': result['refresh_token'],
            'session_id': result['session_id'],
            'user': result['user']
        }), 200
    except ValueError as e:
        return jsonify({'error': str(e)}), 401
    except Exception as e:
        print(f"Refresh token error: {e}")
        return jsonify({'error': 'Internal server error'}), 500


@auth_bp.route('/logout', methods=['POST'])
def logout():
    """Logout current device session by refresh token"""
    try:
        data = request.get_json() or {}
        refresh_token = data.get('refresh_token')

        if not refresh_token:
            return jsonify({'error': 'refresh_token is required'}), 400

        revoked = auth_service.logout_by_refresh_token(refresh_token)
        if not revoked:
            return jsonify({'error': 'Invalid session'}), 400

        return jsonify({'message': 'Logged out successfully'}), 200
    except Exception as e:
        print(f"Logout error: {e}")
        return jsonify({'error': 'Internal server error'}), 500


@auth_bp.route('/sessions', methods=['GET'])
@token_required
def list_sessions():
    """List active and historical device sessions"""
    try:
        user_id = request.user['user_id']
        sessions = auth_service.list_user_sessions(user_id)
        return jsonify({'sessions': sessions}), 200
    except Exception as e:
        print(f"List sessions error: {e}")
        return jsonify({'error': 'Internal server error'}), 500


@auth_bp.route('/sessions/<session_id>', methods=['DELETE'])
@token_required
def revoke_session(session_id):
    """Revoke a specific device session"""
    try:
        user_id = request.user['user_id']
        revoked = auth_service.revoke_user_session(user_id, session_id)

        if not revoked:
            return jsonify({'error': 'Session not found'}), 404

        return jsonify({'message': 'Session revoked successfully'}), 200
    except Exception as e:
        print(f"Revoke session error: {e}")
        return jsonify({'error': 'Internal server error'}), 500


@auth_bp.route('/sessions/revoke-all', methods=['POST'])
@token_required
def revoke_all_sessions():
    """Revoke all sessions for current user"""
    try:
        user_id = request.user['user_id']
        auth_service.revoke_all_user_sessions(user_id)
        return jsonify({'message': 'All sessions revoked successfully'}), 200
    except Exception as e:
        print(f"Revoke all sessions error: {e}")
        return jsonify({'error': 'Internal server error'}), 500


@auth_bp.route('/security-question', methods=['POST'])
def get_user_security_question():
    """Get security question for an account by email"""
    try:
        data = request.get_json() or {}
        email = (data.get('email') or '').strip()

        if not email:
            return jsonify({'error': 'Email is required'}), 400

        if not validate_email(email):
            return jsonify({'error': 'Invalid email format'}), 400

        question = auth_service.get_user_security_question(email)
        if not question:
            return jsonify({'error': 'Security question not found for this account'}), 404

        return jsonify({'question': question}), 200
    except Exception as e:
        print(f"Get security question error: {e}")
        return jsonify({'error': 'Internal server error'}), 500


@auth_bp.route('/reset-password/security', methods=['POST'])
def reset_password_with_security_answer():
    """Reset password by validating security question answer"""
    try:
        data = request.get_json() or {}

        email = (data.get('email') or '').strip()
        question_key = (data.get('question_key') or '').strip()
        answer = data.get('answer')
        new_password = data.get('new_password')

        if not email or not question_key or not answer or not new_password:
            return jsonify({'error': 'Missing required fields'}), 400

        if not validate_email(email):
            return jsonify({'error': 'Invalid email format'}), 400

        if not validate_password(new_password):
            return jsonify({'error': 'Password must be at least 6 characters'}), 400

        auth_service.reset_password_with_security_answer(
            email,
            question_key,
            answer,
            new_password
        )

        return jsonify({'message': 'Password reset successful'}), 200
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        print(f"Security reset password error: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@auth_bp.route('/verify', methods=['GET'])
def verify_token():
    """Verify JWT token"""
    try:
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            return jsonify({'error': 'Invalid token format'}), 401
        
        token = auth_header.split(' ')[1]
        payload = auth_service.verify_token(token)
        
        if not payload:
            return jsonify({'error': 'Invalid or expired token'}), 401

        session_id = payload.get('session_id')
        if session_id:
            session = user_model.get_refresh_session(payload['user_id'], session_id)
            if not session or session.get('revoked_at'):
                return jsonify({'error': 'Session has been revoked'}), 401

            expires_at = session.get('expires_at')
            if expires_at and expires_at <= datetime.utcnow():
                return jsonify({'error': 'Session has expired'}), 401
        
        return jsonify({
            'valid': True,
            'user': {
                'id': payload['user_id'],
                'username': payload['username'],
                'email': payload['email']
            },
            'session_id': payload.get('session_id')
        }), 200
        
    except Exception as e:
        print(f"Token verification error: {e}")
        return jsonify({'error': 'Internal server error'}), 500


@auth_bp.route('/profile', methods=['GET'])
@token_required
def get_profile():
    """Get authenticated user's profile"""
    try:
        user_id = request.user['user_id']
        profile = user_model.get_profile(user_id)

        if not profile:
            return jsonify({'error': 'User not found'}), 404

        return jsonify({'profile': profile}), 200
    except Exception as e:
        print(f"Get profile error: {e}")
        return jsonify({'error': 'Internal server error'}), 500


@auth_bp.route('/profile', methods=['PUT'])
@token_required
def update_profile():
    """Update authenticated user's profile"""
    try:
        data = request.get_json() or {}
        user_id = request.user['user_id']

        username = data.get('username')
        avatar = data.get('avatar', '')
        timezone = data.get('timezone', 'UTC')

        if username is not None and not validate_username(username):
            return jsonify({'error': 'Username must be at least 3 chars and alphanumeric'}), 400

        user_model.update_profile(user_id, {
            'username': username,
            'avatar': avatar,
            'timezone': timezone
        })

        profile = user_model.get_profile(user_id)
        return jsonify({'message': 'Profile updated successfully', 'profile': profile}), 200
    except Exception as e:
        print(f"Update profile error: {e}")
        return jsonify({'error': 'Internal server error'}), 500