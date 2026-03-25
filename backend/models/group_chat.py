from datetime import datetime, timedelta
import secrets
from bson import ObjectId
from config.database import DatabaseConfig


class GroupChatModel:
    """Model for private group chat operations."""

    MAX_MEMBERS = 6

    def __init__(self):
        self.db = DatabaseConfig().get_db()
        self.collection = self.db.group_chats

    def _to_object_id(self, value):
        return ObjectId(value)

    def _normalize_sender_id(self, sender_id):
        """Use ObjectId for regular users, keep string IDs for system senders."""
        try:
            return ObjectId(sender_id)
        except Exception:
            return str(sender_id)

    def create_group(self, owner_id, name):
        owner_oid = self._to_object_id(owner_id)
        now = datetime.utcnow()
        invite_code = secrets.token_urlsafe(18)

        group_doc = {
            'name': name,
            'owner_id': owner_oid,
            'members': [owner_oid],
            'messages': [],
            'invite_code': invite_code,
            'invite_expires_at': now + timedelta(days=7),
            'created_at': now,
            'updated_at': now
        }

        result = self.collection.insert_one(group_doc)
        group_doc['_id'] = result.inserted_id
        return self._serialize_group(group_doc)

    def _serialize_group(self, group_doc):
        created_at = group_doc.get('created_at')
        updated_at = group_doc.get('updated_at')

        return {
            'id': str(group_doc.get('_id')),
            'name': group_doc.get('name', 'Private Group'),
            'owner_id': str(group_doc.get('owner_id')),
            'member_count': len(group_doc.get('members', [])),
            'created_at': created_at.isoformat() if isinstance(created_at, datetime) else created_at,
            'updated_at': updated_at.isoformat() if isinstance(updated_at, datetime) else updated_at
        }

    def _serialize_message(self, msg):
        timestamp = msg.get('timestamp')

        return {
            'id': str(msg.get('id', '')),
            'sender_id': str(msg.get('sender_id')),
            'sender_name': msg.get('sender_name', 'Member'),
            'content': msg.get('content', ''),
            'message_type': msg.get('message_type', 'text'),
            'image_url': msg.get('image_url'),
            'timestamp': timestamp.isoformat() if isinstance(timestamp, datetime) else timestamp
        }

    def list_groups_for_member(self, user_id):
        user_oid = self._to_object_id(user_id)
        groups = list(
            self.collection.find({'members': user_oid}).sort('updated_at', -1)
        )
        return [self._serialize_group(group) for group in groups]

    def is_member(self, group_id, user_id):
        user_oid = self._to_object_id(user_id)
        group_oid = self._to_object_id(group_id)
        group = self.collection.find_one({'_id': group_oid, 'members': user_oid}, {'_id': 1})
        return bool(group)

    def get_group_messages(self, group_id, user_id):
        user_oid = self._to_object_id(user_id)
        group_oid = self._to_object_id(group_id)
        group = self.collection.find_one({'_id': group_oid, 'members': user_oid}, {'messages': 1})

        if not group:
            return None

        messages = group.get('messages', [])
        return [self._serialize_message(msg) for msg in messages]

    def add_message(self, group_id, user_id, sender_name, content, message_type='text', image_url=None):
        user_oid = self._to_object_id(user_id)
        group_oid = self._to_object_id(group_id)

        message = {
            'id': ObjectId(),
            'sender_id': self._normalize_sender_id(user_id),
            'sender_name': sender_name,
            'content': content,
            'message_type': message_type,
            'image_url': image_url,
            'timestamp': datetime.utcnow()
        }

        result = self.collection.update_one(
            {'_id': group_oid, 'members': user_oid},
            {
                '$push': {'messages': message},
                '$set': {'updated_at': datetime.utcnow()}
            }
        )

        if result.matched_count == 0:
            return None

        return self._serialize_message(message)

    def add_assistant_message(self, group_id, content, sender_name='AI Assistant'):
        """Store assistant-generated messages in a group chat."""
        group_oid = self._to_object_id(group_id)

        message = {
            'id': ObjectId(),
            'sender_id': 'assistant-bot',
            'sender_name': sender_name,
            'content': content,
            'message_type': 'text',
            'image_url': None,
            'timestamp': datetime.utcnow()
        }

        result = self.collection.update_one(
            {'_id': group_oid},
            {
                '$push': {'messages': message},
                '$set': {'updated_at': datetime.utcnow()}
            }
        )

        if result.matched_count == 0:
            return None

        return self._serialize_message(message)

    def generate_invite_code(self, group_id, user_id):
        user_oid = self._to_object_id(user_id)
        group_oid = self._to_object_id(group_id)

        invite_code = secrets.token_urlsafe(18)
        expires_at = datetime.utcnow() + timedelta(days=7)

        result = self.collection.update_one(
            {'_id': group_oid, 'members': user_oid},
            {
                '$set': {
                    'invite_code': invite_code,
                    'invite_expires_at': expires_at,
                    'updated_at': datetime.utcnow()
                }
            }
        )

        if result.matched_count == 0:
            return None

        return {
            'invite_code': invite_code,
            'expires_at': expires_at
        }

    def join_with_invite_code(self, invite_code, user_id):
        user_oid = self._to_object_id(user_id)
        now = datetime.utcnow()

        group = self.collection.find_one({
            'invite_code': invite_code,
            'invite_expires_at': {'$gt': now}
        })

        if not group:
            raise ValueError('INVALID_OR_EXPIRED_INVITE')

        members = group.get('members', [])
        already_member = any(str(member) == str(user_oid) for member in members)

        if not already_member and len(members) >= self.MAX_MEMBERS:
            raise ValueError('GROUP_MEMBER_LIMIT_REACHED')

        self.collection.update_one(
            {'_id': group['_id']},
            {
                '$addToSet': {'members': user_oid},
                '$set': {'updated_at': datetime.utcnow()}
            }
        )

        fresh = self.collection.find_one({'_id': group['_id']})
        return self._serialize_group(fresh)

    def leave_group(self, group_id, user_id):
        """Remove a member from group; owner cannot leave without deleting group."""
        user_oid = self._to_object_id(user_id)
        group_oid = self._to_object_id(group_id)

        group = self.collection.find_one({'_id': group_oid})
        if not group:
            raise ValueError('GROUP_NOT_FOUND')

        if str(group.get('owner_id')) == str(user_oid):
            raise ValueError('OWNER_CANNOT_LEAVE')

        result = self.collection.update_one(
            {
                '_id': group_oid,
                'members': user_oid
            },
            {
                '$pull': {'members': user_oid},
                '$set': {'updated_at': datetime.utcnow()}
            }
        )

        if result.matched_count == 0:
            raise ValueError('NOT_A_MEMBER')

        return True

    def delete_group(self, group_id, owner_id):
        """Delete group permanently; allowed only for owner."""
        owner_oid = self._to_object_id(owner_id)
        group_oid = self._to_object_id(group_id)

        result = self.collection.delete_one({
            '_id': group_oid,
            'owner_id': owner_oid
        })

        if result.deleted_count == 0:
            group = self.collection.find_one({'_id': group_oid}, {'owner_id': 1})
            if not group:
                raise ValueError('GROUP_NOT_FOUND')
            raise ValueError('ONLY_OWNER_CAN_DELETE')

        return True
