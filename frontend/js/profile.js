const API_BASE_URL = 'http://localhost:5000/api';

const token = localStorage.getItem('token');
if (!token) {
    window.location.href = 'login.html';
}

const profileForm = document.getElementById('profileForm');
const usernameInput = document.getElementById('username');
const emailInput = document.getElementById('email');
const avatarInput = document.getElementById('avatar');
const timezoneSelect = document.getElementById('timezone');
const avatarPreview = document.getElementById('avatarPreview');
const sessionList = document.getElementById('sessionList');
const revokeAllSessionsBtn = document.getElementById('revokeAllSessionsBtn');

function getTimezones() {
    if (typeof Intl !== 'undefined' && typeof Intl.supportedValuesOf === 'function') {
        return Intl.supportedValuesOf('timeZone');
    }

    return [
        'UTC',
        'America/New_York',
        'America/Chicago',
        'America/Denver',
        'America/Los_Angeles',
        'Europe/London',
        'Europe/Berlin',
        'Asia/Kolkata',
        'Asia/Tokyo',
        'Australia/Sydney'
    ];
}

function populateTimezoneOptions(selectedTimezone) {
    const timezones = getTimezones();
    timezoneSelect.innerHTML = '';

    timezones.forEach((timezone) => {
        const option = document.createElement('option');
        option.value = timezone;
        option.textContent = timezone;
        if (timezone === selectedTimezone) {
            option.selected = true;
        }
        timezoneSelect.appendChild(option);
    });

    if (!selectedTimezone) {
        timezoneSelect.value = Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC';
    }
}

function updateAvatarPreview(url) {
    if (url && url.trim()) {
        avatarPreview.src = url.trim();
        avatarPreview.hidden = false;
    } else {
        avatarPreview.src = '';
        avatarPreview.hidden = true;
    }
}

async function loadProfile() {
    try {
        const response = await fetch(`${API_BASE_URL}/auth/profile`, {
            headers: {
                'Authorization': `Bearer ${token}`
            }
        });

        const data = await response.json();
        if (!response.ok) {
            throw new Error(data.error || 'Failed to load profile');
        }

        const profile = data.profile;
        usernameInput.value = profile.username || '';
        emailInput.value = profile.email || '';
        avatarInput.value = profile.avatar || '';
        populateTimezoneOptions(profile.timezone || 'UTC');
        updateAvatarPreview(profile.avatar || '');
    } catch (error) {
        showToast(error.message || 'Failed to load profile', 'error');
    }
}

function renderSessions(sessions) {
    if (!sessionList) {
        return;
    }

    sessionList.innerHTML = '';
    if (!sessions.length) {
        sessionList.innerHTML = '<div class="session-item"><div class="session-title">No active sessions</div></div>';
        return;
    }

    sessions.forEach((session) => {
        const item = document.createElement('div');
        item.className = 'session-item';

        const created = session.created_at ? new Date(session.created_at).toLocaleString() : 'Unknown';
        const expires = session.expires_at ? new Date(session.expires_at).toLocaleString() : 'Unknown';
        const status = session.revoked_at ? 'Revoked' : 'Active';

        item.innerHTML = `
            <div class="session-title">${status} session</div>
            <div class="session-meta">${session.user_agent || 'Unknown browser'}<br>${session.ip_address || 'Unknown IP'}<br>Created: ${created}<br>Expires: ${expires}</div>
            ${session.revoked_at ? '' : '<button class="btn-submit secondary-btn" type="button">Revoke</button>'}
        `;

        const revokeBtn = item.querySelector('button');
        if (revokeBtn) {
            revokeBtn.addEventListener('click', async () => {
                try {
                    const response = await fetch(`${API_BASE_URL}/auth/sessions/${session.session_id}`, {
                        method: 'DELETE',
                        headers: {
                            'Authorization': `Bearer ${token}`
                        }
                    });

                    const data = await response.json();
                    if (!response.ok) {
                        throw new Error(data.error || 'Failed to revoke session');
                    }

                    showToast('Session revoked', 'success');
                    await loadSessions();
                } catch (error) {
                    showToast(error.message || 'Failed to revoke session', 'error');
                }
            });
        }

        sessionList.appendChild(item);
    });
}

async function loadSessions() {
    if (!sessionList) {
        return;
    }

    try {
        const response = await fetch(`${API_BASE_URL}/auth/sessions`, {
            headers: {
                'Authorization': `Bearer ${token}`
            }
        });

        const data = await response.json();
        if (!response.ok) {
            throw new Error(data.error || 'Failed to load sessions');
        }

        renderSessions(data.sessions || []);
    } catch (error) {
        showToast(error.message || 'Failed to load sessions', 'error');
    }
}

avatarInput.addEventListener('input', (event) => {
    updateAvatarPreview(event.target.value);
});

profileForm.addEventListener('submit', async (event) => {
    event.preventDefault();

    const payload = {
        username: usernameInput.value.trim(),
        avatar: avatarInput.value.trim(),
        timezone: timezoneSelect.value
    };

    try {
        const response = await fetch(`${API_BASE_URL}/auth/profile`, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${token}`
            },
            body: JSON.stringify(payload)
        });

        const data = await response.json();
        if (!response.ok) {
            throw new Error(data.error || 'Failed to update profile');
        }

        const existingUser = JSON.parse(localStorage.getItem('user') || '{}');
        localStorage.setItem('user', JSON.stringify({
            ...existingUser,
            username: data.profile.username,
            email: data.profile.email,
            avatar: data.profile.avatar,
            timezone: data.profile.timezone
        }));

        showToast('Profile updated successfully', 'success');
    } catch (error) {
        showToast(error.message || 'Failed to update profile', 'error');
    }
});

if (revokeAllSessionsBtn) {
    revokeAllSessionsBtn.addEventListener('click', async () => {
        try {
            const response = await fetch(`${API_BASE_URL}/auth/sessions/revoke-all`, {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${token}`
                }
            });

            const data = await response.json();
            if (!response.ok) {
                throw new Error(data.error || 'Failed to revoke all sessions');
            }

            showToast('All sessions revoked', 'success');
            await loadSessions();
        } catch (error) {
            showToast(error.message || 'Failed to revoke all sessions', 'error');
        }
    });
}

loadProfile();
loadSessions();
