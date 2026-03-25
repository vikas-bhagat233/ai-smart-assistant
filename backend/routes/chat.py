from flask import Blueprint, request, jsonify
from werkzeug.utils import secure_filename
from middleware.auth_middleware import token_required
from services.gemini_service import GeminiService
from models.user import UserModel
from models.group_chat import GroupChatModel
from io import BytesIO
from urllib.parse import quote, quote_plus
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
import hashlib
from html import escape
import os
import uuid
from socketio_instance import socketio

from pypdf import PdfReader
from docx import Document
chat_bp = Blueprint('chat', __name__)
gemini_service = GeminiService()
user_model = UserModel()
group_chat_model = GroupChatModel()

MAX_DOCUMENT_CHARS = 120000
ALLOWED_TEXT_EXTENSIONS = {
    'txt', 'md', 'csv', 'json', 'py', 'js', 'ts', 'html', 'css', 'xml', 'yaml', 'yml', 'pdf', 'doc', 'docx'
}
ALLOWED_IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp', 'gif'}
CONTENT_TYPE_TO_EXTENSION = {
    'image/png': 'png',
    'image/jpeg': 'jpg',
    'image/jpg': 'jpg',
    'image/webp': 'webp',
    'image/gif': 'gif',
    'image/svg+xml': 'svg',
    'image/avif': 'avif'
}


def _broadcast_group_message(group_id, message_payload):
    """Broadcast group message updates without breaking API response if socket fails."""
    try:
        socketio.emit(
            'group_message',
            {
                'group_id': str(group_id),
                'message': message_payload
            },
            to=f'group_{group_id}'
        )
    except Exception as emit_error:
        # Realtime is best-effort; message persistence should still succeed.
        print(f"Socket broadcast warning for group {group_id}: {emit_error}")


def _extract_document_content(raw_bytes, extension):
    """Extract text content from supported document formats."""
    if extension == 'pdf':
        reader = PdfReader(BytesIO(raw_bytes))
        page_text = []
        for page in reader.pages:
            page_text.append(page.extract_text() or '')
        return "\n".join(page_text)

    if extension == 'docx':
        doc = Document(BytesIO(raw_bytes))
        return "\n".join([paragraph.text for paragraph in doc.paragraphs])

    # Legacy .doc is not fully supported by python-docx; attempt safe text decode fallback.
    if extension == 'doc':
        try:
            return raw_bytes.decode('utf-8')
        except UnicodeDecodeError:
            return raw_bytes.decode('latin-1', errors='ignore')

    try:
        return raw_bytes.decode('utf-8')
    except UnicodeDecodeError:
        return raw_bytes.decode('latin-1', errors='ignore')


def _download_generated_image(source_url):
    """Download generated image and save it locally for stable rendering."""
    request_obj = Request(
        source_url,
        headers={
            'User-Agent': 'Mozilla/5.0 (AI-Smart-Assistant)'
        }
    )

    with urlopen(request_obj, timeout=45) as response:
        content_type = (response.headers.get('Content-Type') or '').split(';')[0].strip().lower()
        if content_type in CONTENT_TYPE_TO_EXTENSION:
            extension = CONTENT_TYPE_TO_EXTENSION[content_type]
        elif content_type.startswith('image/'):
            # Keep uncommon image types (e.g., image/heic) instead of failing hard.
            extension = content_type.split('/', 1)[1].split('+', 1)[0].strip() or 'jpg'
            if extension == 'jpeg':
                extension = 'jpg'
        else:
            raise ValueError(f"Unsupported image content type: {content_type or 'unknown'}")

        image_bytes = response.read()
        if not image_bytes:
            raise ValueError('Image provider returned empty content')

        filename = f"generated_{uuid.uuid4().hex}.{extension}"
        upload_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'uploads'))
        os.makedirs(upload_dir, exist_ok=True)

        save_path = os.path.join(upload_dir, filename)
        with open(save_path, 'wb') as image_file:
            image_file.write(image_bytes)

        return filename


def _create_local_placeholder_image(prompt):
        """Create a local SVG image so image generation always returns a renderable URL."""
        safe_prompt = escape((prompt or '').strip())[:140]
        if not safe_prompt:
                safe_prompt = 'Image generation unavailable'

        svg_content = f"""<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"1024\" height=\"768\" viewBox=\"0 0 1024 768\">
    <defs>
        <linearGradient id=\"bg\" x1=\"0\" y1=\"0\" x2=\"1\" y2=\"1\">
            <stop offset=\"0%\" stop-color=\"#182848\"/>
            <stop offset=\"100%\" stop-color=\"#4b6cb7\"/>
        </linearGradient>
    </defs>
    <rect width=\"1024\" height=\"768\" fill=\"url(#bg)\"/>
    <rect x=\"64\" y=\"64\" width=\"896\" height=\"640\" rx=\"20\" fill=\"rgba(255,255,255,0.08)\" stroke=\"rgba(255,255,255,0.25)\"/>
    <text x=\"96\" y=\"170\" font-family=\"Segoe UI, Arial, sans-serif\" font-size=\"42\" fill=\"#ffffff\">Image Preview</text>
    <text x=\"96\" y=\"240\" font-family=\"Segoe UI, Arial, sans-serif\" font-size=\"28\" fill=\"#dce6ff\">Prompt:</text>
    <foreignObject x=\"96\" y=\"270\" width=\"832\" height=\"360\">
        <div xmlns=\"http://www.w3.org/1999/xhtml\" style=\"font-family:Segoe UI,Arial,sans-serif;font-size:30px;line-height:1.35;color:#ffffff;word-wrap:break-word;\">{safe_prompt}</div>
    </foreignObject>
    <text x=\"96\" y=\"676\" font-family=\"Segoe UI, Arial, sans-serif\" font-size=\"22\" fill=\"#dce6ff\">External image providers were unavailable for this request.</text>
</svg>"""

        filename = f"generated_placeholder_{uuid.uuid4().hex}.svg"
        upload_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'uploads'))
        os.makedirs(upload_dir, exist_ok=True)
        save_path = os.path.join(upload_dir, filename)
        with open(save_path, 'w', encoding='utf-8') as svg_file:
                svg_file.write(svg_content)

        return filename

@chat_bp.route('/generate', methods=['POST'])
@token_required
def generate_response():
    """Generate AI response using Gemini API"""
    try:
        data = request.get_json()
        prompt = data.get('prompt')
        chat_id = data.get('chat_id')
        context = data.get('context', [])
        
        if not prompt:
            return jsonify({'error': 'Prompt is required'}), 400
        
        # Generate response
        response = gemini_service.generate_response(prompt, context)
        
        # Save to chat history if chat_id is provided
        if chat_id:
            # Update existing chat
            user_id = request.user['user_id']
            user = user_model.find_by_id(user_id)
            
            if user and 'chat_history' in user:
                for chat in user['chat_history']:
                    if str(chat['id']) == str(chat_id):
                        chat['messages'].append({
                            'role': 'user',
                            'content': prompt,
                            'timestamp': None
                        })
                        chat['messages'].append({
                            'role': 'assistant',
                            'content': response,
                            'timestamp': None
                        })
                        chat['updated_at'] = None
                        break
        
        return jsonify({
            'response': response,
            'success': True
        }), 200
        
    except Exception as e:
        print(f"Chat generation error: {e}")
        return jsonify({
            'error': str(e),
            'success': False
        }), 500

@chat_bp.route('/history', methods=['GET'])
@token_required
def get_chat_history():
    """Get user's chat history"""
    try:
        user_id = request.user['user_id']
        search_query = request.args.get('q', '').strip()
        favorites_only = request.args.get('favorites_only', 'false').lower() == 'true'

        if search_query:
            history = user_model.search_chat_history(user_id, search_query)
        else:
            history = user_model.get_chat_history(user_id)

        if favorites_only:
            history = [chat for chat in history if chat.get('is_pinned', False)]

        # Pinned chats first, then most recently updated.
        history.sort(
            key=lambda chat: (
                bool(chat.get('is_pinned', False)),
                chat.get('updated_at') or chat.get('created_at')
            ),
            reverse=True
        )
        
        # Convert ObjectId to string for JSON serialization
        formatted_history = []
        for chat in history:
            chat['id'] = str(chat['id'])
            chat['is_pinned'] = bool(chat.get('is_pinned', False))
            formatted_history.append(chat)
        
        return jsonify({
            'history': formatted_history,
            'success': True
        }), 200
        
    except Exception as e:
        print(f"Get history error: {e}")
        return jsonify({
            'error': str(e),
            'success': False
        }), 500

@chat_bp.route('/save', methods=['POST'])
@token_required
def save_chat():
    """Save a new chat or update existing"""
    try:
        data = request.get_json()
        user_id = request.user['user_id']
        chat_data = data.get('chat_data')
        
        if not chat_data:
            return jsonify({'error': 'Chat data is required'}), 400

        chat_id = chat_data.get('id')
        if chat_id:
            updated = user_model.replace_chat(user_id, chat_id, chat_data)
            if not updated:
                return jsonify({'error': 'Chat not found'}), 404
            saved_chat = {'id': str(chat_id)}
        else:
            saved_chat = user_model.update_chat_history(user_id, chat_data)
        
        return jsonify({
            'message': 'Chat saved successfully',
            'chat_id': saved_chat['id'],
            'success': True
        }), 200
        
    except Exception as e:
        print(f"Save chat error: {e}")
        return jsonify({
            'error': str(e),
            'success': False
        }), 500


@chat_bp.route('/rename/<chat_id>', methods=['PUT'])
@token_required
def rename_chat(chat_id):
    """Rename a specific chat"""
    try:
        data = request.get_json() or {}
        title = (data.get('title') or '').strip()
        if not title:
            return jsonify({'error': 'Title is required'}), 400

        user_id = request.user['user_id']
        updated = user_model.update_chat_metadata(user_id, chat_id, title=title)

        if not updated:
            return jsonify({'error': 'Chat not found'}), 404

        return jsonify({'message': 'Chat renamed successfully', 'success': True}), 200
    except Exception as e:
        print(f"Rename chat error: {e}")
        return jsonify({'error': str(e), 'success': False}), 500


@chat_bp.route('/pin/<chat_id>', methods=['PUT'])
@token_required
def pin_chat(chat_id):
    """Pin or unpin a chat"""
    try:
        data = request.get_json() or {}
        is_pinned = bool(data.get('is_pinned', False))

        user_id = request.user['user_id']
        updated = user_model.update_chat_metadata(user_id, chat_id, is_pinned=is_pinned)

        if not updated:
            return jsonify({'error': 'Chat not found'}), 404

        return jsonify({'message': 'Chat favorite status updated', 'success': True}), 200
    except Exception as e:
        print(f"Pin chat error: {e}")
        return jsonify({'error': str(e), 'success': False}), 500

@chat_bp.route('/delete/<chat_id>', methods=['DELETE'])
@token_required
def delete_chat(chat_id):
    """Soft delete a specific chat"""
    try:
        user_id = request.user['user_id']
        deleted = user_model.delete_chat(user_id, chat_id)

        if not deleted:
            return jsonify({'error': 'Chat not found', 'success': False}), 404
        
        return jsonify({
            'message': 'Chat archived successfully',
            'success': True
        }), 200
        
    except Exception as e:
        print(f"Delete chat error: {e}")
        return jsonify({
            'error': str(e),
            'success': False
        }), 500


@chat_bp.route('/upload', methods=['POST'])
@token_required
def upload_document():
    """Upload a text-like document and return extracted content for Q&A context"""
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'File is required', 'success': False}), 400

        uploaded_file = request.files['file']
        if not uploaded_file or uploaded_file.filename == '':
            return jsonify({'error': 'File is required', 'success': False}), 400

        filename = secure_filename(uploaded_file.filename)
        extension = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''

        if extension not in ALLOWED_TEXT_EXTENSIONS:
            return jsonify({
                'error': 'Unsupported file type. Use text, PDF, or Word files (txt, md, csv, json, py, js, ts, html, css, xml, yaml, pdf, doc, docx).',
                'success': False
            }), 400

        raw_bytes = uploaded_file.read()
        content = _extract_document_content(raw_bytes, extension)

        content = (content or '').strip()
        if not content:
            return jsonify({
                'error': 'Could not extract readable text from this file. For Word, please prefer .docx files.',
                'success': False
            }), 400

        truncated = False
        if len(content) > MAX_DOCUMENT_CHARS:
            content = content[:MAX_DOCUMENT_CHARS]
            truncated = True

        return jsonify({
            'success': True,
            'filename': filename,
            'content': content,
            'truncated': truncated
        }), 200

    except Exception as e:
        print(f"Upload document error: {e}")
        return jsonify({'error': str(e), 'success': False}), 500


@chat_bp.route('/groups', methods=['GET'])
@token_required
def list_private_groups():
    """List private groups where current user is a member"""
    try:
        user_id = request.user['user_id']
        groups = group_chat_model.list_groups_for_member(user_id)
        return jsonify({'success': True, 'groups': groups}), 200
    except Exception as e:
        print(f"List groups error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@chat_bp.route('/groups/create', methods=['POST'])
@token_required
def create_private_group():
    """Create a private group chat"""
    try:
        data = request.get_json() or {}
        group_name = (data.get('name') or '').strip()

        if not group_name:
            return jsonify({'success': False, 'error': 'Group name is required'}), 400

        user_id = request.user['user_id']
        created = group_chat_model.create_group(user_id, group_name)

        invite_code_data = group_chat_model.generate_invite_code(created['id'], user_id)
        invite_code = invite_code_data['invite_code']
        invite_url = f"{request.host_url.rstrip('/')}/dashboard.html?groupInvite={quote(invite_code)}"

        return jsonify({
            'success': True,
            'group': created,
            'invite_code': invite_code,
            'invite_url': invite_url
        }), 201
    except Exception as e:
        print(f"Create group error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@chat_bp.route('/groups/<group_id>/messages', methods=['GET'])
@token_required
def get_private_group_messages(group_id):
    """Get private group messages for group members only"""
    try:
        user_id = request.user['user_id']
        messages = group_chat_model.get_group_messages(group_id, user_id)

        if messages is None:
            return jsonify({'success': False, 'error': 'Group not found or access denied'}), 404

        return jsonify({'success': True, 'messages': messages}), 200
    except Exception as e:
        print(f"Get group messages error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@chat_bp.route('/groups/<group_id>/message', methods=['POST'])
@token_required
def add_private_group_message(group_id):
    """Post a message in a private group"""
    try:
        data = request.get_json() or {}
        content = (data.get('message') or '').strip()

        if not content:
            return jsonify({'success': False, 'error': 'Message is required'}), 400

        user_id = request.user['user_id']
        sender_name = request.user.get('username', 'Member')

        saved = group_chat_model.add_message(group_id, user_id, sender_name, content)
        if saved is None:
            return jsonify({'success': False, 'error': 'Group not found or access denied'}), 404

        _broadcast_group_message(group_id, saved)

        assistant_message = None
        try:
            recent_messages = group_chat_model.get_group_messages(group_id, user_id) or []
            context = []
            for msg in recent_messages[-20:]:
                role = 'assistant' if msg.get('sender_id') == 'assistant-bot' else 'user'

                if msg.get('message_type') == 'image':
                    content_text = f"{msg.get('sender_name', 'Member')} shared an image"
                else:
                    content_text = msg.get('content', '')

                context.append({
                    'role': role,
                    'content': content_text
                })

            ai_response = gemini_service.generate_response(content, context)
            assistant_message = group_chat_model.add_assistant_message(group_id, ai_response)

            if assistant_message:
                _broadcast_group_message(group_id, assistant_message)
        except Exception as ai_error:
            print(f"Group assistant response warning: {ai_error}")

        return jsonify({'success': True, 'message': saved, 'assistant_message': assistant_message}), 200
    except Exception as e:
        print(f"Add group message error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@chat_bp.route('/groups/<group_id>/upload-image', methods=['POST'])
@token_required
def upload_group_image(group_id):
    """Upload image in private group chat and broadcast in realtime"""
    try:
        if 'file' not in request.files:
            return jsonify({'success': False, 'error': 'File is required'}), 400

        uploaded_file = request.files['file']
        if not uploaded_file or uploaded_file.filename == '':
            return jsonify({'success': False, 'error': 'File is required'}), 400

        filename = secure_filename(uploaded_file.filename)
        extension = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
        if extension not in ALLOWED_IMAGE_EXTENSIONS:
            return jsonify({'success': False, 'error': 'Only image files are allowed (png, jpg, jpeg, webp, gif).'}), 400

        user_id = request.user['user_id']
        sender_name = request.user.get('username', 'Member')

        unique_name = f"{uuid.uuid4().hex}.{extension}"
        upload_dir = os.path.join(os.path.dirname(__file__), '..', 'uploads')
        upload_dir = os.path.abspath(upload_dir)
        os.makedirs(upload_dir, exist_ok=True)

        save_path = os.path.join(upload_dir, unique_name)
        uploaded_file.save(save_path)

        image_url = f"{request.host_url.rstrip('/')}/uploads/{unique_name}"
        saved = group_chat_model.add_message(
            group_id,
            user_id,
            sender_name,
            content='[Image]',
            message_type='image',
            image_url=image_url
        )

        if saved is None:
            try:
                os.remove(save_path)
            except OSError:
                pass
            return jsonify({'success': False, 'error': 'Group not found or access denied'}), 404

        _broadcast_group_message(group_id, saved)

        return jsonify({'success': True, 'message': saved}), 200
    except Exception as e:
        print(f"Upload group image error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@chat_bp.route('/groups/<group_id>/invite', methods=['POST'])
@token_required
def create_group_invite(group_id):
    """Create or rotate an invite link for a private group"""
    try:
        user_id = request.user['user_id']
        invite = group_chat_model.generate_invite_code(group_id, user_id)

        if invite is None:
            return jsonify({'success': False, 'error': 'Group not found or access denied'}), 404

        invite_url = f"{request.host_url.rstrip('/')}/dashboard.html?groupInvite={quote(invite['invite_code'])}"
        return jsonify({
            'success': True,
            'invite_code': invite['invite_code'],
            'invite_url': invite_url,
            'expires_at': invite['expires_at']
        }), 200
    except Exception as e:
        print(f"Create group invite error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@chat_bp.route('/groups/join', methods=['POST'])
@token_required
def join_group_with_invite():
    """Join a private group by invite code"""
    try:
        data = request.get_json() or {}
        invite_code = (data.get('invite_code') or '').strip()

        if not invite_code:
            return jsonify({'success': False, 'error': 'Invite code is required'}), 400

        user_id = request.user['user_id']
        joined_group = group_chat_model.join_with_invite_code(invite_code, user_id)

        return jsonify({'success': True, 'group': joined_group}), 200
    except ValueError as e:
        if str(e) == 'GROUP_MEMBER_LIMIT_REACHED':
            return jsonify({'success': False, 'error': 'This group is full. Maximum 6 members allowed.'}), 400
        if str(e) == 'INVALID_OR_EXPIRED_INVITE':
            return jsonify({'success': False, 'error': 'Invalid or expired invite code'}), 404
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception as e:
        print(f"Join group error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@chat_bp.route('/groups/<group_id>/leave', methods=['POST'])
@token_required
def leave_group(group_id):
    """Leave a group for non-owner members."""
    try:
        user_id = request.user['user_id']
        group_chat_model.leave_group(group_id, user_id)
        return jsonify({'success': True, 'message': 'You left the group'}), 200
    except ValueError as e:
        if str(e) == 'GROUP_NOT_FOUND':
            return jsonify({'success': False, 'error': 'Group not found'}), 404
        if str(e) == 'OWNER_CANNOT_LEAVE':
            return jsonify({'success': False, 'error': 'Owner cannot leave. Delete group instead.'}), 400
        if str(e) == 'NOT_A_MEMBER':
            return jsonify({'success': False, 'error': 'You are not a group member'}), 400
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception as e:
        print(f"Leave group error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@chat_bp.route('/groups/<group_id>', methods=['DELETE'])
@token_required
def delete_group(group_id):
    """Delete a group; owner only."""
    try:
        user_id = request.user['user_id']
        group_chat_model.delete_group(group_id, user_id)
        return jsonify({'success': True, 'message': 'Group deleted successfully'}), 200
    except ValueError as e:
        if str(e) == 'GROUP_NOT_FOUND':
            return jsonify({'success': False, 'error': 'Group not found'}), 404
        if str(e) == 'ONLY_OWNER_CAN_DELETE':
            return jsonify({'success': False, 'error': 'Only group owner can delete this group'}), 403
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception as e:
        print(f"Delete group error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@chat_bp.route('/generate-image', methods=['POST'])
@token_required
def generate_image():
    """Generate an image URL from text prompt"""
    try:
        data = request.get_json() or {}
        prompt = (data.get('prompt') or '').strip()

        if not prompt:
            return jsonify({'success': False, 'error': 'Prompt is required'}), 400

        # Keep the prompt focused to reduce unrelated image elements.
        prompt_for_image = (
            f"Accurate visual depiction of: {prompt}. "
            "Do not add unrelated objects, text, or scenes."
        )
        seed = int.from_bytes(hashlib.sha256(prompt.encode('utf-8')).digest()[:4], 'big')
        image_url = (
            f"https://image.pollinations.ai/prompt/{quote(prompt_for_image)}"
            f"?model=flux&width=1024&height=768&seed={seed}&nologo=true&enhance=false"
        )

        fallback_url = f"https://loremflickr.com/1024/768/{quote_plus(prompt.replace(' ', ','))}"
        provider_candidates = [
            ('pollinations-flux', image_url),
            ('pollinations-basic', f"https://image.pollinations.ai/prompt/{quote(prompt)}"),
            ('loremflickr-fallback', fallback_url)
        ]

        saved_filename = None
        provider_used = None
        provider_errors = []

        for provider_name, provider_url in provider_candidates:
            try:
                saved_filename = _download_generated_image(provider_url)
                provider_used = provider_name
                break
            except (HTTPError, URLError, TimeoutError, ValueError) as provider_error:
                provider_errors.append(f"{provider_name}: {provider_error}")
                print(f"Image provider warning ({provider_name}): {provider_error}")

        if not saved_filename:
            saved_filename = _create_local_placeholder_image(prompt)
            provider_used = 'local-placeholder'

        return jsonify({
            'success': True,
            'image_url': f"{request.host_url.rstrip('/')}/uploads/{saved_filename}",
            'prompt_used': prompt_for_image,
            'provider_used': provider_used,
            'provider_errors': provider_errors
        }), 200
    except Exception as e:
        print(f"Generate image error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500