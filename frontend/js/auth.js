const API_BASE_URL = `${window.location.origin}/api`;

// Toast notification
function showToast(message, type = 'success') {
    const toast = document.getElementById('toast');
    toast.textContent = message;
    toast.className = `toast ${type} show`;
    
    setTimeout(() => {
        toast.classList.remove('show');
    }, 3000);
}

// Toggle password visibility
document.querySelectorAll('.toggle-password').forEach(button => {
    button.addEventListener('click', () => {
        const input = button.previousElementSibling;
        const type = input.getAttribute('type') === 'password' ? 'text' : 'password';
        input.setAttribute('type', type);
        button.classList.toggle('fa-eye-slash');
    });
});

async function verifyToken(token) {
    try {
        const response = await fetch(`${API_BASE_URL}/auth/verify`, {
            headers: {
                'Authorization': `Bearer ${token}`
            }
        });

        return response.ok;
    } catch (error) {
        return false;
    }
}

async function refreshAccessToken() {
    const refreshToken = localStorage.getItem('refreshToken');
    if (!refreshToken) {
        return false;
    }

    try {
        const response = await fetch(`${API_BASE_URL}/auth/refresh`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ refresh_token: refreshToken })
        });

        const data = await response.json();
        if (!response.ok) {
            return false;
        }

        localStorage.setItem('token', data.token);
        localStorage.setItem('refreshToken', data.refresh_token);
        localStorage.setItem('sessionId', data.session_id);
        localStorage.setItem('user', JSON.stringify(data.user));
        return true;
    } catch (error) {
        return false;
    }
}

async function autoRedirectAuthenticatedUsers() {
    const token = localStorage.getItem('token');
    const onAuthPage = window.location.pathname.includes('login.html') || window.location.pathname.includes('signup.html');

    if (!token || !onAuthPage) {
        return;
    }

    const valid = await verifyToken(token);
    if (valid) {
        window.location.href = 'dashboard.html';
    } else {
        const refreshed = await refreshAccessToken();
        if (refreshed) {
            window.location.href = 'dashboard.html';
            return;
        }
        localStorage.removeItem('token');
        localStorage.removeItem('refreshToken');
        localStorage.removeItem('sessionId');
        localStorage.removeItem('user');
    }
}

async function loadSecurityQuestionsForSignup() {
    const securityQuestionSelect = document.getElementById('securityQuestion');
    if (!securityQuestionSelect) {
        return;
    }

    try {
        const response = await fetch(`${API_BASE_URL}/auth/security-questions`);
        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.error || 'Failed to load security questions');
        }

        (data.questions || []).forEach((question) => {
            const option = document.createElement('option');
            option.value = question.key;
            option.textContent = question.text;
            securityQuestionSelect.appendChild(option);
        });
    } catch (error) {
        showToast(error.message || 'Failed to load security questions', 'error');
    }
}

// Login form handler
const loginForm = document.getElementById('loginForm');
if (loginForm) {
    loginForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        
        const email = document.getElementById('email').value;
        const password = document.getElementById('password').value;
        
        try {
            const response = await fetch(`${API_BASE_URL}/auth/login`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ email, password })
            });
            
            const data = await response.json();
            
            if (response.ok) {
                localStorage.setItem('token', data.token);
                localStorage.setItem('refreshToken', data.refresh_token);
                localStorage.setItem('sessionId', data.session_id);
                localStorage.setItem('user', JSON.stringify(data.user));
                showToast('Login successful! Redirecting...', 'success');
                setTimeout(() => {
                    window.location.href = 'dashboard.html';
                }, 1500);
            } else {
                showToast(data.error || 'Login failed', 'error');
            }
        } catch (error) {
            showToast('Network error. Please try again.', 'error');
        }
    });
}

// Signup form handler
const signupForm = document.getElementById('signupForm');
if (signupForm) {
    signupForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        
        const username = document.getElementById('username').value;
        const email = document.getElementById('email').value;
        const password = document.getElementById('password').value;
        const securityQuestion = document.getElementById('securityQuestion').value;
        const securityAnswer = document.getElementById('securityAnswer').value;
        
        try {
            const response = await fetch(`${API_BASE_URL}/auth/register`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    username,
                    email,
                    password,
                    security_question_key: securityQuestion,
                    security_answer: securityAnswer
                })
            });
            
            const data = await response.json();
            
            if (response.ok) {
                localStorage.setItem('token', data.token);
                localStorage.setItem('refreshToken', data.refresh_token);
                localStorage.setItem('sessionId', data.session_id);
                localStorage.setItem('user', JSON.stringify(data.user));
                showToast('Account created successfully! Redirecting...', 'success');
                setTimeout(() => {
                    window.location.href = 'dashboard.html';
                }, 1500);
            } else {
                showToast(data.error || 'Registration failed', 'error');
            }
        } catch (error) {
            showToast('Network error. Please try again.', 'error');
        }
    });
}

let activeRecoveryQuestionKey = null;

const toggleForgotPasswordBtn = document.getElementById('toggleForgotPassword');
const forgotPasswordForm = document.getElementById('forgotPasswordForm');
const getSecurityQuestionBtn = document.getElementById('getSecurityQuestionBtn');
const securityQuestionWrap = document.getElementById('securityQuestionWrap');
const securityQuestionLabel = document.getElementById('securityQuestionLabel');
const newPasswordWrap = document.getElementById('newPasswordWrap');
const resetPasswordBtn = document.getElementById('resetPasswordBtn');

if (toggleForgotPasswordBtn && forgotPasswordForm) {
    toggleForgotPasswordBtn.addEventListener('click', () => {
        forgotPasswordForm.hidden = !forgotPasswordForm.hidden;
    });
}

if (getSecurityQuestionBtn) {
    getSecurityQuestionBtn.addEventListener('click', async () => {
        const recoveryEmail = (document.getElementById('recoveryEmail')?.value || '').trim();
        if (!recoveryEmail) {
            showToast('Please enter your account email', 'error');
            return;
        }

        try {
            const response = await fetch(`${API_BASE_URL}/auth/security-question`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ email: recoveryEmail })
            });

            const data = await response.json();
            if (!response.ok) {
                throw new Error(data.error || 'Failed to fetch security question');
            }

            activeRecoveryQuestionKey = data.question.question_key;
            securityQuestionLabel.textContent = data.question.question_text;
            securityQuestionWrap.hidden = false;
            newPasswordWrap.hidden = false;
            resetPasswordBtn.hidden = false;
            showToast('Answer the security question to reset password', 'success');
        } catch (error) {
            showToast(error.message || 'Failed to fetch security question', 'error');
        }
    });
}

if (forgotPasswordForm) {
    forgotPasswordForm.addEventListener('submit', async (e) => {
        e.preventDefault();

        const recoveryEmail = (document.getElementById('recoveryEmail')?.value || '').trim();
        const securityAnswer = (document.getElementById('securityAnswer')?.value || '').trim();
        const newPassword = (document.getElementById('newPassword')?.value || '').trim();

        if (!recoveryEmail || !activeRecoveryQuestionKey || !securityAnswer || !newPassword) {
            showToast('Please fill all recovery fields', 'error');
            return;
        }

        try {
            const response = await fetch(`${API_BASE_URL}/auth/reset-password/security`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    email: recoveryEmail,
                    question_key: activeRecoveryQuestionKey,
                    answer: securityAnswer,
                    new_password: newPassword
                })
            });

            const data = await response.json();
            if (!response.ok) {
                throw new Error(data.error || 'Password reset failed');
            }

            showToast('Password reset successful. Please login.', 'success');
            forgotPasswordForm.reset();
            securityQuestionWrap.hidden = true;
            newPasswordWrap.hidden = true;
            resetPasswordBtn.hidden = true;
            activeRecoveryQuestionKey = null;
        } catch (error) {
            showToast(error.message || 'Password reset failed', 'error');
        }
    });
}

// Check if user is already logged in
function checkAuth() {
    const token = localStorage.getItem('token');
    if (token && window.location.pathname.includes('dashboard.html')) {
        // Verify token with backend
        fetch(`${API_BASE_URL}/auth/verify`, {
            headers: {
                'Authorization': `Bearer ${token}`
            }
        }).then(response => {
            if (!response.ok) {
                refreshAccessToken().then((refreshed) => {
                    if (!refreshed) {
                        localStorage.removeItem('token');
                        localStorage.removeItem('refreshToken');
                        localStorage.removeItem('sessionId');
                        localStorage.removeItem('user');
                        window.location.href = 'login.html';
                    }
                });
            }
        });
    } else if (!token && window.location.pathname.includes('dashboard.html')) {
        window.location.href = 'login.html';
    }
}

// Run auth check on page load
checkAuth();
autoRedirectAuthenticatedUsers();
loadSecurityQuestionsForSignup();