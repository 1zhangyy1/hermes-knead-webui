"""Login page locale helpers for WebUI routes."""

from __future__ import annotations

import json


LOGIN_LOCALE = {
    "en": {
        "lang": "en",
        "title": "Sign in",
        "subtitle": "Enter your password to continue",
        "placeholder": "Password",
        "btn": "Sign in",
        "invalid_pw": "Invalid password",
        "conn_failed": "Connection failed",
    },
    "fr": {
        "lang": "fr-FR",
        "title": "Se connecter",
        "subtitle": "Entrez votre mot de passe pour continuer",
        "placeholder": "Mot de passe",
        "btn": "Se connecter",
        "invalid_pw": "Mot de passe invalide",
        "conn_failed": "\u00c9chec de la connexion",
    },
    "es": {
        "lang": "es-ES",
        "title": "Iniciar sesi\u00f3n",
        "subtitle": "Introduce tu contrase\u00f1a para continuar",
        "placeholder": "Contrase\u00f1a",
        "btn": "Entrar",
        "invalid_pw": "Contrase\u00f1a inv\u00e1lida",
        "conn_failed": "Error de conexi\u00f3n",
    },
    "de": {
        "lang": "de-DE",
        "title": "Anmelden",
        "subtitle": "Geben Sie Ihr Passwort ein, um fortzufahren",
        "placeholder": "Passwort",
        "btn": "Anmelden",
        "invalid_pw": "Ung\u00fcltiges Passwort",
        "conn_failed": "Verbindung fehlgeschlagen",
    },
    "ru": {
        "lang": "ru-RU",
        "title": "\u0412\u043e\u0439\u0442\u0438",
        "subtitle": "\u0412\u0432\u0435\u0434\u0438\u0442\u0435 \u043f\u0430\u0440\u043e\u043b\u044c, \u0447\u0442\u043e\u0431\u044b \u043f\u0440\u043e\u0434\u043e\u043b\u0436\u0438\u0442\u044c",
        "placeholder": "\u041f\u0430\u0440\u043e\u043b\u044c",
        "btn": "\u0412\u043e\u0439\u0442\u0438",
        "invalid_pw": "\u041d\u0435\u0432\u0435\u0440\u043d\u044b\u0439 \u043f\u0430\u0440\u043e\u043b\u044c",
        "conn_failed": "\u041d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c \u043f\u043e\u0434\u043a\u043b\u044e\u0447\u0438\u0442\u044c\u0441\u044f",
    },
    "zh": {
        "lang": "zh-CN",
        "title": "\u767b\u5f55",
        "subtitle": "\u8f93\u5165\u5bc6\u7801\u7ee7\u7eed\u4f7f\u7528",
        "placeholder": "\u5bc6\u7801",
        "btn": "\u767b\u5f55",
        "invalid_pw": "\u5bc6\u7801\u9519\u8bef",
        "conn_failed": "\u8fde\u63a5\u5931\u8d25",
    },
    "zh-Hant": {
        "lang": "zh-TW",
        "title": "\u767b\u5f55",
        "subtitle": "\u8f38\u5165\u5bc6\u78bc\u7e7c\u7e8c\u4f7f\u7528",
        "placeholder": "\u5bc6\u78bc",
        "btn": "\u767b\u5f55",
        "invalid_pw": "\u5bc6\u78bc\u932f\u8aa4",
        "conn_failed": "\u9023\u63a5\u5931\u6557",
    },
    "it": {
        "lang": "it-IT",
        "title": "Accedi",
        "subtitle": "Inserisci la password per continuare",
        "placeholder": "Password",
        "btn": "Accedi",
        "invalid_pw": "Password non valida",
        "conn_failed": "Connessione fallita",
    },
    "ja": {
        "lang": "ja-JP",
        "title": "\u30b5\u30a4\u30f3\u30a4\u30f3",
        "subtitle": "\u30d1\u30b9\u30ef\u30fc\u30c9\u3092\u5165\u529b\u3057\u3066\u7d9a\u884c",
        "placeholder": "\u30d1\u30b9\u30ef\u30fc\u30c9",
        "btn": "\u30b5\u30a4\u30f3\u30a4\u30f3",
        "invalid_pw": "\u30d1\u30b9\u30ef\u30fc\u30c9\u304c\u7121\u52b9\u3067\u3059",
        "conn_failed": "\u63a5\u7d9a\u5931\u6557",
    },
    "pt": {
        "lang": "pt-BR",
        "title": "Entrar",
        "subtitle": "Digite sua senha para continuar",
        "placeholder": "Senha",
        "btn": "Entrar",
        "invalid_pw": "Senha inv\u00e1lida",
        "conn_failed": "Falha na conex\u00e3o",
    },
    "ko": {
        "lang": "ko-KR",
        "title": "\ub85c\uadf8\uc778",
        "subtitle": "\uacc4\uc18d\ud558\ub824\uba74 \ube44\ubc00\ubc88\ud638\ub97c \uc785\ub825\ud558\uc138\uc694",
        "placeholder": "\ube44\ubc00\ubc88\ud638",
        "btn": "\ub85c\uadf8\uc778",
        "invalid_pw": "\ube44\ubc00\ubc88\ud638\uac00 \uc62c\ubc14\ub974\uc9c0 \uc54a\uc2b5\ub2c8\ub2e4",
        "conn_failed": "\uc5f0\uacb0 \uc2e4\ud328",
    },
}


def resolve_login_locale_key(raw_lang: str | None, locale: dict = LOGIN_LOCALE) -> str:
    """Resolve settings.language to a known login locale key."""
    if not raw_lang:
        return "en"
    lang = str(raw_lang).strip()
    if not lang:
        return "en"
    if lang in locale:
        return lang

    normalized = lang.replace("_", "-")
    lower = normalized.lower()

    for key in locale:
        if key.lower() == lower:
            return key

    if lower == "zh" or lower.startswith("zh-cn") or lower.startswith("zh-sg") or lower.startswith("zh-hans"):
        return "zh"
    if lower.startswith("zh-tw") or lower.startswith("zh-hk") or lower.startswith("zh-mo") or lower.startswith("zh-hant"):
        return "zh-Hant" if "zh-Hant" in locale else "zh"

    base = lower.split("-", 1)[0]
    for key in locale:
        if key.lower() == base:
            return key
    return "en"


def handle_auth_login(
    handler,
    body,
    *,
    verify_password_fn,
    create_session_fn,
    set_auth_cookie_fn,
    is_auth_enabled_fn,
    check_login_rate_fn,
    record_login_attempt_fn,
    security_headers_fn,
    json_response_fn,
    bad_response_fn,
):
    if not is_auth_enabled_fn():
        return json_response_fn(handler, {"ok": True, "message": "Auth not enabled"})
    client_ip = handler.client_address[0]
    if not check_login_rate_fn(client_ip):
        return json_response_fn(
            handler,
            {"error": "Too many attempts. Try again in a minute."},
            status=429,
        )
    password = body.get("password", "")
    if not verify_password_fn(password):
        record_login_attempt_fn(client_ip)
        return bad_response_fn(handler, "Invalid password", 401)

    cookie_val = create_session_fn()
    handler.send_response(200)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Cache-Control", "no-store")
    security_headers_fn(handler)
    set_auth_cookie_fn(handler, cookie_val)
    handler.end_headers()
    handler.wfile.write(json.dumps({"ok": True}).encode())
    return True


def handle_auth_logout(
    handler,
    *,
    clear_auth_cookie_fn,
    invalidate_session_fn,
    parse_cookie_fn,
    security_headers_fn,
):
    cookie_val = parse_cookie_fn(handler)
    if cookie_val:
        invalidate_session_fn(cookie_val)
    handler.send_response(200)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Cache-Control", "no-store")
    security_headers_fn(handler)
    clear_auth_cookie_fn(handler)
    handler.end_headers()
    handler.wfile.write(json.dumps({"ok": True}).encode())
    return True
