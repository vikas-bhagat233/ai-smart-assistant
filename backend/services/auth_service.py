import bcrypt
import jwt
import os
import hashlib
import secrets
from datetime import datetime, timedelta
from models.user import UserModel


class AuthService:
    """Authentication service for user management"""

    SECURITY_QUESTIONS = [
        {'key': 'mother_maiden_name', 'text': "What is your mother's maiden name?"},
        {'key': 'first_school', 'text': 'What was the name of your first school?'},
        {'key': 'childhood_nickname', 'text': 'What was your childhood nickname?'},
        {'key': 'best_friend_name', 'text': 'What is your best friend name from school?'}
    ]

    ACCESS_TOKEN_LIFETIME_MINUTES = 45
    REFRESH_TOKEN_LIFETIME_DAYS = 30

    def __init__(self):
        self.user_model = UserModel()
        self.jwt_secret = os.getenv('JWT_SECRET_KEY')

        if not self.jwt_secret:
            raise ValueError('JWT_SECRET_KEY not found in environment variables')

    def hash_password(self, password):
        """Hash password using bcrypt"""
        salt = bcrypt.gensalt()
        return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')

    def verify_password(self, plain_password, hashed_password):
        """Verify password against hash"""
        return bcrypt.checkpw(
            plain_password.encode('utf-8'),
            hashed_password.encode('utf-8')
        )

    def _hash_refresh_token(self, refresh_token):
        return hashlib.sha256(refresh_token.encode('utf-8')).hexdigest()

    def _normalize_security_answer(self, answer):
        """Normalize security answer for case-insensitive matching"""
        return (answer or '').strip().lower()

    def get_security_questions(self):
        """Return available security questions for signup"""
        return self.SECURITY_QUESTIONS

    def get_security_question_text(self, question_key):
        """Map security question key to display text"""
        for question in self.SECURITY_QUESTIONS:
            if question['key'] == question_key:
                return question['text']
        return None

    def generate_access_token(self, user_id, username, email, session_id=None):
        """Generate short-lived JWT access token"""
        payload = {
            'user_id': str(user_id),
            'username': username,
            'email': email,
            'session_id': session_id,
            'type': 'access',
            'exp': datetime.utcnow() + timedelta(minutes=self.ACCESS_TOKEN_LIFETIME_MINUTES),
            'iat': datetime.utcnow()
        }

        return jwt.encode(payload, self.jwt_secret, algorithm='HS256')

    def generate_refresh_token(self, user_id, session_id):
        """Generate long-lived JWT refresh token"""
        payload = {
            'user_id': str(user_id),
            'session_id': session_id,
            'type': 'refresh',
            'nonce': secrets.token_hex(8),
            'exp': datetime.utcnow() + timedelta(days=self.REFRESH_TOKEN_LIFETIME_DAYS),
            'iat': datetime.utcnow()
        }

        return jwt.encode(payload, self.jwt_secret, algorithm='HS256')

    def verify_token(self, token):
        """Verify and decode access token"""
        try:
            payload = jwt.decode(token, self.jwt_secret, algorithms=['HS256'])
            if payload.get('type') != 'access':
                return None
            return payload
        except jwt.ExpiredSignatureError:
            return None
        except jwt.InvalidTokenError:
            return None

    def verify_refresh_token(self, refresh_token):
        """Verify and decode refresh token"""
        try:
            payload = jwt.decode(refresh_token, self.jwt_secret, algorithms=['HS256'])
            if payload.get('type') != 'refresh':
                return None
            return payload
        except jwt.ExpiredSignatureError:
            return None
        except jwt.InvalidTokenError:
            return None

    def _create_session(self, user, user_agent=None, ip_address=None):
        session_id = secrets.token_urlsafe(16)
        refresh_token = self.generate_refresh_token(user['_id'], session_id)

        now = datetime.utcnow()
        session_doc = {
            'session_id': session_id,
            'refresh_token_hash': self._hash_refresh_token(refresh_token),
            'user_agent': (user_agent or '')[:512],
            'ip_address': (ip_address or '')[:128],
            'created_at': now,
            'last_used_at': now,
            'expires_at': now + timedelta(days=self.REFRESH_TOKEN_LIFETIME_DAYS),
            'revoked_at': None
        }
        self.user_model.create_refresh_session(user['_id'], session_doc)

        access_token = self.generate_access_token(
            user['_id'],
            user['username'],
            user['email'],
            session_id=session_id
        )

        return {
            'token': access_token,
            'refresh_token': refresh_token,
            'session_id': session_id,
            'user': {
                'id': str(user['_id']),
                'username': user['username'],
                'email': user['email']
            }
        }

    def register_user(self, username, email, password, security_question_key=None, security_answer=None, user_agent=None, ip_address=None):
        """Register a new user"""
        existing_user = self.user_model.find_by_email(email)
        if existing_user:
            raise ValueError('User with this email already exists')

        question_text = self.get_security_question_text(security_question_key)
        if not question_text:
            raise ValueError('Please select a valid security question')

        normalized_answer = self._normalize_security_answer(security_answer)
        if len(normalized_answer) < 2:
            raise ValueError('Security answer must be at least 2 characters')

        hashed_password = self.hash_password(password)
        user_id = self.user_model.create_user(username, email, hashed_password)

        answer_hash = self.hash_password(normalized_answer)
        self.user_model.set_security_question(
            user_id,
            security_question_key,
            question_text,
            answer_hash
        )

        user = self.user_model.find_by_id(str(user_id))
        return self._create_session(user, user_agent=user_agent, ip_address=ip_address)

    def login_user(self, email, password, user_agent=None, ip_address=None):
        """Authenticate and login user"""
        user = self.user_model.find_by_email(email)

        if not user:
            raise ValueError('Invalid email or password')

        if not self.verify_password(password, user['password']):
            raise ValueError('Invalid email or password')

        self.user_model.update_last_login(user['_id'])
        return self._create_session(user, user_agent=user_agent, ip_address=ip_address)

    def refresh_access(self, refresh_token, user_agent=None, ip_address=None):
        """Rotate refresh token and issue a new access token"""
        payload = self.verify_refresh_token(refresh_token)
        if not payload:
            raise ValueError('Invalid or expired refresh token')

        user_id = payload['user_id']
        session_id = payload['session_id']

        user = self.user_model.find_by_id(user_id)
        if not user:
            raise ValueError('User not found')

        session = self.user_model.get_refresh_session(user_id, session_id)
        if not session:
            raise ValueError('Session not found')

        if session.get('revoked_at'):
            raise ValueError('Session has been revoked')

        if session.get('expires_at') and session['expires_at'] <= datetime.utcnow():
            raise ValueError('Session has expired')

        stored_hash = session.get('refresh_token_hash')
        if stored_hash != self._hash_refresh_token(refresh_token):
            raise ValueError('Refresh token mismatch')

        new_refresh_token = self.generate_refresh_token(user_id, session_id)
        now = datetime.utcnow()
        self.user_model.update_refresh_session(
            user_id,
            session_id,
            {
                'refresh_token_hash': self._hash_refresh_token(new_refresh_token),
                'last_used_at': now,
                'expires_at': now + timedelta(days=self.REFRESH_TOKEN_LIFETIME_DAYS),
                'user_agent': (user_agent or session.get('user_agent', ''))[:512],
                'ip_address': (ip_address or session.get('ip_address', ''))[:128]
            }
        )

        access_token = self.generate_access_token(
            user['_id'],
            user['username'],
            user['email'],
            session_id=session_id
        )

        return {
            'token': access_token,
            'refresh_token': new_refresh_token,
            'session_id': session_id,
            'user': {
                'id': str(user['_id']),
                'username': user['username'],
                'email': user['email']
            }
        }

    def logout_by_refresh_token(self, refresh_token):
        """Revoke session identified by refresh token"""
        payload = self.verify_refresh_token(refresh_token)
        if not payload:
            return False

        user_id = payload['user_id']
        session_id = payload['session_id']
        return self.user_model.revoke_refresh_session(user_id, session_id)

    def list_user_sessions(self, user_id):
        return self.user_model.list_refresh_sessions(user_id)

    def revoke_user_session(self, user_id, session_id):
        return self.user_model.revoke_refresh_session(user_id, session_id)

    def revoke_all_user_sessions(self, user_id):
        return self.user_model.revoke_all_refresh_sessions(user_id)

    def get_user_security_question(self, email):
        """Get configured security question for a user by email"""
        return self.user_model.get_security_question_by_email(email)

    def reset_password_with_security_answer(self, email, question_key, answer, new_password):
        """Reset password after validating security question answer"""
        user = self.user_model.find_by_email(email)
        if not user:
            raise ValueError('User not found')

        stored_question_key = user.get('security_question_key')
        stored_answer_hash = user.get('security_answer_hash')

        if not stored_question_key or not stored_answer_hash:
            raise ValueError('Security question is not configured for this account')

        if stored_question_key != question_key:
            raise ValueError('Security question does not match')

        normalized_answer = self._normalize_security_answer(answer)
        if not self.verify_password(normalized_answer, stored_answer_hash):
            raise ValueError('Security answer is incorrect')

        hashed_password = self.hash_password(new_password)
        self.user_model.update_password_by_email(email, hashed_password)

        if user.get('_id'):
            self.user_model.revoke_all_refresh_sessions(str(user['_id']))

        return True
