from datetime import datetime
from config.database import DatabaseConfig

class UserModel:
    """User model for database operations"""
    
    def __init__(self):
        self.db = DatabaseConfig().get_db()
        self.collection = self.db.users
    
    def create_user(self, username, email, hashed_password):
        """Create a new user"""
        user = {
            'username': username,
            'email': email.lower(),
            'password': hashed_password,
            'security_question_key': None,
            'security_question_text': None,
            'security_answer_hash': None,
            'refresh_sessions': [],
            'avatar': '',
            'timezone': 'UTC',
            'chat_history': [],
            'created_at': datetime.utcnow(),
            'last_login': None
        }
        
        result = self.collection.insert_one(user)
        return result.inserted_id

    def set_security_question(self, user_id, question_key, question_text, answer_hash):
        """Persist security question and hashed answer for password recovery"""
        from bson import ObjectId

        result = self.collection.update_one(
            {'_id': ObjectId(user_id)},
            {
                '$set': {
                    'security_question_key': question_key,
                    'security_question_text': question_text,
                    'security_answer_hash': answer_hash,
                    'updated_at': datetime.utcnow()
                }
            }
        )

        return result.modified_count > 0

    def _build_chat_id_variants(self, chat_id):
        """Build candidate id values for legacy and current chat id formats."""
        variants = [str(chat_id)]
        try:
            variants.append(float(chat_id))
        except (ValueError, TypeError):
            pass
        return variants
    
    def find_by_email(self, email):
        """Find user by email"""
        return self.collection.find_one({'email': email.lower()})

    def get_security_question_by_email(self, email):
        """Return security question metadata for a user email"""
        user = self.collection.find_one(
            {'email': (email or '').lower()},
            {'security_question_key': 1, 'security_question_text': 1}
        )

        if not user:
            return None

        if not user.get('security_question_key') or not user.get('security_question_text'):
            return None

        return {
            'question_key': user.get('security_question_key'),
            'question_text': user.get('security_question_text')
        }

    def update_password_by_email(self, email, hashed_password):
        """Update user password by email"""
        result = self.collection.update_one(
            {'email': (email or '').lower()},
            {
                '$set': {
                    'password': hashed_password,
                    'updated_at': datetime.utcnow()
                }
            }
        )

        return result.modified_count > 0

    def create_refresh_session(self, user_id, session_doc):
        """Append a new refresh token session entry for a user"""
        from bson import ObjectId

        result = self.collection.update_one(
            {'_id': ObjectId(user_id)},
            {
                '$push': {'refresh_sessions': session_doc},
                '$set': {'updated_at': datetime.utcnow()}
            }
        )

        return result.modified_count > 0

    def get_refresh_session(self, user_id, session_id):
        """Return one refresh session object by session id"""
        from bson import ObjectId

        user = self.collection.find_one(
            {'_id': ObjectId(user_id)},
            {'refresh_sessions': 1}
        )

        if not user:
            return None

        for session in user.get('refresh_sessions', []):
            if session.get('session_id') == session_id:
                return session

        return None

    def update_refresh_session(self, user_id, session_id, updates):
        """Update refresh session fields for a specific session id"""
        from bson import ObjectId

        set_payload = {
            f'refresh_sessions.$.{key}': value
            for key, value in updates.items()
        }
        set_payload['updated_at'] = datetime.utcnow()

        result = self.collection.update_one(
            {
                '_id': ObjectId(user_id),
                'refresh_sessions.session_id': session_id
            },
            {'$set': set_payload}
        )

        return result.modified_count > 0

    def revoke_refresh_session(self, user_id, session_id):
        """Revoke a single refresh session"""
        return self.update_refresh_session(
            user_id,
            session_id,
            {'revoked_at': datetime.utcnow()}
        )

    def revoke_all_refresh_sessions(self, user_id):
        """Revoke all active refresh sessions for user"""
        from bson import ObjectId

        now = datetime.utcnow()
        user = self.collection.find_one({'_id': ObjectId(user_id)}, {'refresh_sessions': 1})
        if not user:
            return False

        sessions = user.get('refresh_sessions', [])
        updated_sessions = []
        for session in sessions:
            if not session.get('revoked_at'):
                session['revoked_at'] = now
            updated_sessions.append(session)

        result = self.collection.update_one(
            {'_id': ObjectId(user_id)},
            {
                '$set': {
                    'refresh_sessions': updated_sessions,
                    'updated_at': now
                }
            }
        )

        return result.modified_count > 0

    def list_refresh_sessions(self, user_id):
        """List refresh sessions metadata for user"""
        from bson import ObjectId

        user = self.collection.find_one(
            {'_id': ObjectId(user_id)},
            {'refresh_sessions': 1}
        )

        if not user:
            return []

        sessions = user.get('refresh_sessions', [])
        formatted = []
        for session in sessions:
            formatted.append({
                'session_id': session.get('session_id'),
                'user_agent': session.get('user_agent', ''),
                'ip_address': session.get('ip_address', ''),
                'created_at': session.get('created_at'),
                'last_used_at': session.get('last_used_at'),
                'expires_at': session.get('expires_at'),
                'revoked_at': session.get('revoked_at')
            })

        return formatted
    
    def find_by_id(self, user_id):
        """Find user by ID"""
        from bson import ObjectId
        return self.collection.find_one({'_id': ObjectId(user_id)})
    
    def update_chat_history(self, user_id, chat_data):
        """Update user's chat history"""
        from bson import ObjectId
        
        chat_id = str(chat_data.get('id') or datetime.utcnow().timestamp())
        chat_entry = {
            'id': chat_id,
            'title': chat_data.get('title', 'New Chat'),
            'messages': chat_data.get('messages', []),
            'is_pinned': bool(chat_data.get('is_pinned', False)),
            'is_deleted': False,
            'created_at': datetime.utcnow(),
            'updated_at': datetime.utcnow()
        }
        
        self.collection.update_one(
            {'_id': ObjectId(user_id)},
            {'$push': {'chat_history': chat_entry}}
        )
        
        return chat_entry

    def replace_chat(self, user_id, chat_id, chat_data):
        """Replace an existing chat's content and metadata"""
        from bson import ObjectId

        update_data = {
            'chat_history.$.title': chat_data.get('title', 'New Chat'),
            'chat_history.$.messages': chat_data.get('messages', []),
            'chat_history.$.updated_at': datetime.utcnow()
        }

        if 'is_pinned' in chat_data:
            update_data['chat_history.$.is_pinned'] = bool(chat_data.get('is_pinned'))

        result = self.collection.update_one(
            {
                '_id': ObjectId(user_id),
                'chat_history.id': {'$in': self._build_chat_id_variants(chat_id)}
            },
            {'$set': update_data}
        )

        return result.matched_count > 0
    
    def get_chat_history(self, user_id):
        """Get user's chat history"""
        from bson import ObjectId
        
        user = self.collection.find_one(
            {'_id': ObjectId(user_id)},
            {'chat_history': 1}
        )
        
        history = user.get('chat_history', []) if user else []
        return [chat for chat in history if not chat.get('is_deleted', False)]

    def search_chat_history(self, user_id, query):
        """Search user's chat history by title and message content"""
        query_lower = (query or '').lower().strip()
        history = self.get_chat_history(user_id)

        if not query_lower:
            return history

        filtered = []
        for chat in history:
            title = str(chat.get('title', '')).lower()
            messages = chat.get('messages', [])
            has_match = query_lower in title or any(
                query_lower in str(msg.get('content', '')).lower()
                for msg in messages
            )

            if has_match:
                filtered.append(chat)

        return filtered
    
    def update_last_login(self, user_id):
        """Update user's last login time"""
        from bson import ObjectId
        
        self.collection.update_one(
            {'_id': ObjectId(user_id)},
            {'$set': {'last_login': datetime.utcnow()}}
        )
    
    def delete_chat(self, user_id, chat_id):
        """Soft delete a specific chat from history"""
        from bson import ObjectId

        result = self.collection.update_one(
            {
                '_id': ObjectId(user_id),
                'chat_history.id': {'$in': self._build_chat_id_variants(chat_id)}
            },
            {
                '$set': {
                    'chat_history.$.is_deleted': True,
                    'chat_history.$.updated_at': datetime.utcnow()
                }
            }
        )

        return result.matched_count > 0

    def update_chat_metadata(self, user_id, chat_id, title=None, is_pinned=None):
        """Update chat title and/or favorite status"""
        from bson import ObjectId

        updates = {'chat_history.$.updated_at': datetime.utcnow()}
        if title is not None:
            updates['chat_history.$.title'] = title
        if is_pinned is not None:
            updates['chat_history.$.is_pinned'] = bool(is_pinned)

        result = self.collection.update_one(
            {
                '_id': ObjectId(user_id),
                'chat_history.id': {'$in': self._build_chat_id_variants(chat_id)}
            },
            {'$set': updates}
        )

        return result.matched_count > 0

    def get_profile(self, user_id):
        """Get user profile fields"""
        from bson import ObjectId

        user = self.collection.find_one(
            {'_id': ObjectId(user_id)},
            {'username': 1, 'email': 1, 'avatar': 1, 'timezone': 1}
        )

        if not user:
            return None

        return {
            'id': str(user.get('_id')),
            'username': user.get('username', ''),
            'email': user.get('email', ''),
            'avatar': user.get('avatar', ''),
            'timezone': user.get('timezone', 'UTC')
        }

    def update_profile(self, user_id, profile_data):
        """Update editable profile fields"""
        from bson import ObjectId

        updates = {
            'updated_at': datetime.utcnow()
        }

        if 'username' in profile_data:
            updates['username'] = profile_data.get('username')
        if 'avatar' in profile_data:
            updates['avatar'] = profile_data.get('avatar')
        if 'timezone' in profile_data:
            updates['timezone'] = profile_data.get('timezone')

        result = self.collection.update_one(
            {'_id': ObjectId(user_id)},
            {'$set': updates}
        )

        return result.modified_count > 0