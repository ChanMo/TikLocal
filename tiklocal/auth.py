import datetime
import secrets
import time
from collections import defaultdict, deque
from urllib.parse import urlsplit

from flask import redirect, render_template, request, session, url_for


UNSAFE_METHODS = {'POST', 'PUT', 'PATCH', 'DELETE'}


class LoginAttemptLimiter:
    def __init__(self, limit: int = 5, window_seconds: int = 300):
        self.limit = limit
        self.window_seconds = window_seconds
        self._attempts: dict[str, deque[float]] = defaultdict(deque)

    def retry_after(self, key: str) -> int:
        attempts = self._active(key)
        if len(attempts) < self.limit:
            return 0
        return max(1, int(self.window_seconds - (time.monotonic() - attempts[0])))

    def record_failure(self, key: str) -> None:
        self._active(key).append(time.monotonic())

    def clear(self, key: str) -> None:
        self._attempts.pop(key, None)

    def _active(self, key: str) -> deque[float]:
        attempts = self._attempts[key]
        cutoff = time.monotonic() - self.window_seconds
        while attempts and attempts[0] < cutoff:
            attempts.popleft()
        return attempts


def configure_auth(app, auth_store, *, enabled: bool) -> None:
    app.extensions['auth_store'] = auth_store
    app.extensions['auth_enabled'] = enabled
    limiter = LoginAttemptLimiter()

    if not enabled:
        @app.context_processor
        def auth_disabled_context():
            return {'auth_enabled': False, 'csrf_token': lambda: ''}
        return

    app.secret_key = auth_store.secret_key
    app.config.update(
        SESSION_COOKIE_NAME='tiklocal_session',
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE='Lax',
        SESSION_COOKIE_SECURE=bool(app.config.get('AUTH_COOKIE_SECURE', False)),
        PERMANENT_SESSION_LIFETIME=datetime.timedelta(days=30),
    )

    def ensure_csrf_token() -> str:
        token = session.get('_csrf_token')
        if not token:
            token = secrets.token_urlsafe(32)
            session['_csrf_token'] = token
        return str(token)

    def is_authenticated() -> bool:
        return bool(
            session.get('authenticated') is True
            and int(session.get('auth_revision') or 0) == auth_store.revision
        )

    def safe_next(value: str | None) -> str:
        candidate = str(value or '').strip()
        parsed = urlsplit(candidate)
        if not candidate.startswith('/') or candidate.startswith('//') or parsed.scheme or parsed.netloc:
            return '/'
        return candidate

    def csrf_value_from_request() -> str:
        value = request.headers.get('X-CSRF-Token') or request.form.get('_csrf_token')
        if value:
            return str(value)
        payload = request.get_json(silent=True)
        if isinstance(payload, dict):
            return str(payload.get('_csrf_token') or '')
        return ''

    def csrf_is_valid() -> bool:
        expected = str(session.get('_csrf_token') or '')
        supplied = csrf_value_from_request()
        return bool(expected and supplied and secrets.compare_digest(expected, supplied))

    def unauthorized_response():
        if request.path.startswith('/api/'):
            return {'success': False, 'error': 'Authentication required'}, 401
        if request.path.startswith('/media') or request.path == '/thumb':
            return 'Authentication required', 401
        target = request.full_path.rstrip('?') if request.method == 'GET' else '/'
        return redirect(url_for('login_view', next=target))

    def csrf_error_response():
        if request.path.startswith('/api/'):
            return {'success': False, 'error': 'Invalid CSRF token'}, 403
        return 'Invalid CSRF token', 403

    @app.before_request
    def enforce_authentication():
        if request.endpoint == 'static':
            return None
        if request.endpoint == 'login_view':
            if request.method in UNSAFE_METHODS and not csrf_is_valid():
                return csrf_error_response()
            return None
        if not is_authenticated():
            return unauthorized_response()
        if request.method in UNSAFE_METHODS and not csrf_is_valid():
            return csrf_error_response()
        return None

    @app.after_request
    def apply_security_headers(response):
        response.headers.setdefault('X-Content-Type-Options', 'nosniff')
        response.headers.setdefault('X-Frame-Options', 'SAMEORIGIN')
        response.headers.setdefault('Referrer-Policy', 'same-origin')
        if request.endpoint == 'login_view':
            response.headers['Cache-Control'] = 'no-store'
        return response

    @app.context_processor
    def auth_context():
        return {'auth_enabled': True, 'csrf_token': ensure_csrf_token}

    @app.route('/login', methods=['GET', 'POST'])
    def login_view():
        next_url = safe_next(request.values.get('next'))
        if is_authenticated():
            return redirect(next_url)

        error = ''
        status = 200
        if request.method == 'POST':
            client_key = request.remote_addr or 'unknown'
            retry_after = limiter.retry_after(client_key)
            if retry_after:
                minutes = max(1, (retry_after + 59) // 60)
                error = f'尝试次数过多，请在 {minutes} 分钟后重试。'
                status = 429
            elif not auth_store.verify(request.form.get('password', '')):
                limiter.record_failure(client_key)
                error = '访问密码不正确，请再试一次。'
                status = 401
            else:
                limiter.clear(client_key)
                remember = request.form.get('remember') == '1'
                session.clear()
                session['authenticated'] = True
                session['auth_revision'] = auth_store.revision
                session.permanent = remember
                ensure_csrf_token()
                return redirect(next_url)

        return render_template(
            'login.html',
            csrf_value=ensure_csrf_token(),
            next_url=next_url,
            error=error,
        ), status

    @app.post('/logout')
    def logout_view():
        session.clear()
        return redirect(url_for('login_view'))
