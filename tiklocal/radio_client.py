import io
from urllib.parse import quote, unquote, urlencode, urlsplit, urlunsplit

import segno
from flask import request, send_file

from tiklocal.auth import LoginAttemptLimiter
from tiklocal.services.library import AUDIO_EXTENSIONS
from tiklocal.services.radio import RadioCandidate


def register_radio_client_routes(
    app,
    *,
    app_version,
    instance_name,
    auth_store,
    device_auth_store,
    pairing_grant_store,
    library_service,
    favorite_service,
    radio_service,
    thumbnail_service,
) -> None:
    pair_limiter = LoginAttemptLimiter()
    grant_limiter = LoginAttemptLimiter()

    def ok(data, status=200):
        return {"success": True, "data": data}, status

    def error(code: str, message: str, status: int):
        return {"success": False, "error": {"code": code, "message": message}}, status

    def existing_audio_uri(raw_uri: str) -> str:
        uri = library_service.find_existing_uri(unquote(str(raw_uri or "")))
        path = library_service.resolve_path(uri)
        if not path or not path.exists() or not path.is_file():
            return ""
        if path.suffix.lower() not in AUDIO_EXTENSIONS:
            return ""
        return library_service.get_relative_path(path)

    def serialize_track(item: RadioCandidate) -> dict:
        encoded = quote(item.name, safe="")
        return {
            "id": item.name,
            "uri": item.name,
            "title": item.title,
            "artist": item.artist,
            "album": item.album,
            "duration": item.duration,
            "is_favorite": item.is_favorite,
            "media_path": f"/api/v1/radio/media?uri={encoded}",
            "artwork_path": f"/api/v1/radio/artwork?uri={encoded}",
            "metadata_path": f"/api/v1/radio/metadata?uri={encoded}",
        }

    def bearer_token() -> str:
        authorization = str(request.headers.get("Authorization") or "")
        scheme, separator, token = authorization.partition(" ")
        return token.strip() if separator and scheme.lower() == "bearer" else ""

    def paired_device_payload(credential):
        return {
            "server": _server_payload(instance_name, app_version, auth_required=True),
            "device": {
                "id": credential.device_id,
                "name": credential.device_name,
                "token": credential.token,
            },
        }

    @app.post("/api/v1/pair")
    def api_v1_pair():
        payload = request.get_json(silent=True) or {}
        if not app.extensions.get("auth_enabled"):
            return ok({
                "server": _server_payload(instance_name, app_version, auth_required=False),
                "device": {"id": "", "token": ""},
            })

        client_key = request.remote_addr or "unknown"
        retry_after = pair_limiter.retry_after(client_key)
        if retry_after:
            response, status = error(
                "too_many_attempts",
                "Too many pairing attempts. Try again later.",
                429,
            )
            return response, status, {"Retry-After": str(retry_after)}
        if not auth_store.verify(str(payload.get("password") or "")):
            pair_limiter.record_failure(client_key)
            return error("invalid_password", "The access password is incorrect", 401)

        pair_limiter.clear(client_key)
        credential = device_auth_store.issue(
            str(payload.get("device_name") or ""),
            auth_revision=auth_store.revision,
        )
        return ok(paired_device_payload(credential), 201)

    @app.post("/api/radio/pairing-grants")
    def api_radio_pairing_grant():
        if not app.extensions.get("auth_enabled"):
            return error(
                "pairing_not_required",
                "This TikLocal Server does not require pairing",
                409,
            )
        payload = request.get_json(silent=True) or {}
        server_url = _pairing_server_url(
            payload.get("server_url") or request.host_url
        )
        if not server_url:
            return error(
                "invalid_server_url",
                "Enter an HTTP or HTTPS Server address without a path",
                400,
            )
        grant = pairing_grant_store.issue(auth_revision=auth_store.revision)
        pairing_uri = "tiklocal-radio://pair?" + urlencode({
            "server": server_url,
            "grant": grant.token,
            "v": "1",
        })
        qr_data_uri = segno.make_qr(
            pairing_uri,
            error="m",
        ).svg_data_uri(
            scale=6,
            border=4,
            dark="#0b211c",
        )
        return ok({
            "pairing_uri": pairing_uri,
            "qr_data_uri": qr_data_uri,
            "server_url": server_url,
            "expires_at": grant.expires_at,
            "expires_in": grant.expires_in,
        }, 201)

    @app.post("/api/v1/pair/claim")
    def api_v1_claim_pairing_grant():
        if not app.extensions.get("auth_enabled"):
            return error(
                "pairing_not_required",
                "This TikLocal Server does not require pairing",
                409,
            )
        client_key = request.remote_addr or "unknown"
        retry_after = grant_limiter.retry_after(client_key)
        if retry_after:
            response, status = error(
                "too_many_attempts",
                "Too many pairing attempts. Try again later.",
                429,
            )
            return response, status, {"Retry-After": str(retry_after)}
        payload = request.get_json(silent=True) or {}
        if not pairing_grant_store.consume(
            str(payload.get("grant") or ""),
            auth_revision=auth_store.revision,
        ):
            grant_limiter.record_failure(client_key)
            return error(
                "invalid_pairing_grant",
                "This pairing link has expired or was already used",
                401,
            )
        grant_limiter.clear(client_key)
        credential = device_auth_store.issue(
            str(payload.get("device_name") or ""),
            auth_revision=auth_store.revision,
        )
        return ok(paired_device_payload(credential), 201)

    @app.get("/api/v1/server")
    def api_v1_server():
        return ok(_server_payload(
            instance_name,
            app_version,
            auth_required=bool(app.extensions.get("auth_enabled")),
        ))

    @app.delete("/api/v1/device")
    def api_v1_revoke_device():
        revoked = device_auth_store.revoke_token(
            bearer_token(),
            auth_revision=auth_store.revision,
        )
        return ok({"revoked": revoked})

    @app.get("/api/radio/devices")
    def api_radio_devices():
        return ok({
            "devices": device_auth_store.list_devices(
                auth_revision=auth_store.revision,
            ),
        })

    @app.delete("/api/radio/devices/<device_id>")
    def api_revoke_radio_device(device_id):
        if not device_auth_store.revoke(device_id):
            return {"success": False, "error": "Device not found"}, 404
        return ok({"revoked": True})

    @app.get("/api/v1/radio/stations")
    def api_v1_radio_stations():
        return ok({"stations": radio_service.list_stations()})

    @app.get("/api/v1/radio/tune")
    def api_v1_radio_tune():
        limit = _bounded_int(request.args.get("limit"), default=12, minimum=1, maximum=30)
        excluded = {
            unquote(value.strip())
            for value in str(request.args.get("exclude") or "").split(",")
            if value.strip()
        }
        payload = radio_service.tune(
            station=str(request.args.get("station") or "default").strip(),
            limit=limit,
            exclude=excluded,
            seed=str(request.args.get("seed") or "").strip() or None,
            serialize_track=serialize_track,
        )
        return ok(payload)

    @app.get("/api/v1/radio/metadata")
    def api_v1_radio_metadata():
        uri = existing_audio_uri(request.args.get("uri") or "")
        if not uri:
            return error("audio_not_found", "Audio not found", 404)
        metadata = radio_service.metadata_for_uri(uri)
        path = library_service.resolve_path(uri)
        return ok({
            "uri": uri,
            "title": metadata.title or (path.stem if path else uri),
            "artist": metadata.artist,
            "album": metadata.album,
            "duration": metadata.duration,
        })

    @app.get("/api/v1/radio/media")
    def api_v1_radio_media():
        uri = existing_audio_uri(request.args.get("uri") or "")
        if not uri:
            return error("audio_not_found", "Audio not found", 404)
        return send_file(library_service.resolve_path(uri), conditional=True)

    @app.get("/api/v1/radio/artwork")
    def api_v1_radio_artwork():
        uri = existing_audio_uri(request.args.get("uri") or "")
        if not uri:
            return error("audio_not_found", "Audio not found", 404)
        path, mimetype = thumbnail_service.get_radio_artwork(uri)
        return send_file(io.BytesIO(path) if isinstance(path, bytes) else path, mimetype=mimetype)

    @app.put("/api/v1/radio/favorite")
    def api_v1_radio_favorite():
        payload = request.get_json(silent=True) or {}
        uri = existing_audio_uri(payload.get("uri") or "")
        if not uri:
            return error("audio_not_found", "Audio not found", 404)
        if not isinstance(payload.get("favorite"), bool):
            return error("invalid_favorite", "favorite must be a boolean", 400)
        try:
            favorite = favorite_service.set_favorite(uri, payload["favorite"])
        except (OSError, ValueError):
            return error("favorite_unavailable", "Favorite storage is unavailable", 503)
        return ok({"uri": uri, "is_favorite": favorite})

    @app.post("/api/v1/radio/feedback")
    def api_v1_radio_feedback():
        payload = request.get_json(silent=True) or {}
        uri = existing_audio_uri(payload.get("uri") or "")
        event = str(payload.get("event") or "").strip()
        if not uri:
            return error("audio_not_found", "Audio not found", 404)
        if event not in {"play", "complete", "replay", "skip", "favorite", "error"}:
            return error("invalid_event", "Invalid feedback event", 400)
        ratio = _ratio(payload.get("ratio"))
        profile = radio_service.record_feedback(uri, event, ratio=ratio)
        return ok({"profile": profile})


def _server_payload(instance_name: str, app_version: str, *, auth_required: bool) -> dict:
    return {
        "name": instance_name,
        "server_version": app_version,
        "api_version": 1,
        "auth_required": auth_required,
    }


def _pairing_server_url(value) -> str:
    candidate = str(value or "").strip()
    if not candidate or len(candidate) > 500:
        return ""
    try:
        parsed = urlsplit(candidate)
        port = parsed.port
    except ValueError:
        return ""
    if (
        parsed.scheme.lower() not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
    ):
        return ""
    hostname = parsed.hostname
    if ":" in hostname:
        hostname = f"[{hostname}]"
    netloc = f"{hostname}:{port}" if port else hostname
    return urlunsplit((parsed.scheme.lower(), netloc, "", "", ""))


def _bounded_int(value, *, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(parsed, maximum))


def _ratio(value) -> float | None:
    if value is None:
        return None
    try:
        return max(0.0, min(float(value), 1.0))
    except (TypeError, ValueError):
        return None
