from flask import request
from flask_socketio import emit, join_room, leave_room
from services.auth_service import AuthService
from models.group_chat import GroupChatModel


auth_service = AuthService()
group_chat_model = GroupChatModel()
connected_users = {}


def register_socket_events(socketio):
    @socketio.on('connect')
    def handle_connect(auth):
        auth_payload = auth or {}
        token = auth_payload.get('token')

        if not token:
            return False

        payload = auth_service.verify_token(token)
        if not payload:
            return False

        connected_users[request.sid] = payload
        emit('connected', {'success': True, 'user_id': payload.get('user_id')})

    @socketio.on('disconnect')
    def handle_disconnect():
        connected_users.pop(request.sid, None)

    @socketio.on('join_group')
    def handle_join_group(data):
        group_id = (data or {}).get('group_id')
        if not group_id:
            emit('socket_error', {'error': 'group_id is required'})
            return

        auth_payload = connected_users.get(request.sid)

        if not auth_payload:
            emit('socket_error', {'error': 'Unauthorized'})
            return

        if not group_chat_model.is_member(group_id, auth_payload['user_id']):
            emit('socket_error', {'error': 'Access denied for this group'})
            return

        room = f'group_{group_id}'
        join_room(room)
        emit('joined_group', {'group_id': group_id})

    @socketio.on('leave_group')
    def handle_leave_group(data):
        group_id = (data or {}).get('group_id')
        if not group_id:
            return

        room = f'group_{group_id}'
        leave_room(room)
        emit('left_group', {'group_id': group_id})
