"""Gmail REST adapter. Configuration is supplied by the communication manager.

prepare() performs all reply lookups before confirmation; send() never looks up
or retries a message. Attachments are returned as metadata, never downloaded.
"""
import asyncio
import base64
import math
import re
import time
from email import policy
from email.message import EmailMessage
from email.parser import HeaderParser

from .base import CommunicationError, request


API = "https://gmail.googleapis.com/gmail/v1/users/me"
OAUTH = "https://oauth2.googleapis.com/token"


def _fail(code, message):
    return CommunicationError(code, message)


def _header(value):
    if not isinstance(value, str) or any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise _fail("invalid_input", "Invalid email header.")
    return value


def _recipient(value):
    value = _header(value).strip()
    try:
        parsed = HeaderParser(policy=policy.default).parsestr("To: " + value + "\n\n")["To"]
        addresses = parsed.addresses
        if parsed.defects or len(addresses) != 1:
            raise ValueError()
        address = addresses[0]
        if not address.username or not address.domain or any(c.isspace() for c in address.addr_spec):
            raise ValueError()
        if any(group.display_name is not None for group in parsed.groups):
            raise ValueError()
    except Exception:
        raise _fail("invalid_input", "A single valid email recipient is required.") from None
    return value


def _id(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", value):
        raise _fail("invalid_input", "Invalid Gmail message or thread identifier.")
    return value


def _reply_headers(headers):
    if not isinstance(headers, dict) or set(headers) - {"In-Reply-To", "References"}:
        raise _fail("invalid_input", "Unsupported email headers.")
    result = {}
    for key, value in headers.items():
        value = _header(value)
        if not re.fullmatch(r"<[^<>\s]+>(?: +<[^<>\s]+>)*", value):
            raise _fail("invalid_input", "Invalid reply headers.")
        if key == "In-Reply-To" and value.count("<") != 1:
            raise _fail("invalid_input", "Invalid reply headers.")
        result[key] = value
    return result


class Gmail:
    def __init__(self, settings):
        self._settings = dict(settings)
        self._credential_file = self._settings.get("GMAIL_CREDENTIAL_FILE")
        if self._credential_file:
            from .gmail_credentials import load
            stored = load(self._credential_file)
            for key, value in stored.items():
                if key not in self._settings:
                    self._settings[key] = value
        self._token = self._settings.get("GMAIL_ACCESS_TOKEN", "")
        self._expires = 0
        self._lock = asyncio.Lock()

    async def _request(self, method, url, **kwargs):
        try:
            result = await request(method, url, **kwargs)
            if not isinstance(result, dict) or "error" in result:
                raise ValueError()
            return result
        except CommunicationError as exc:
            if url == OAUTH:
                raise _fail('authorization_required','Gmail authorization must be renewed; OAuth refresh failed.') from None
            raise exc from None
        except Exception:
            # Do not retain provider response bodies or exception chains.
            message = ("Gmail send failed; delivery may be uncertain. Check Sent before trying again."
                       if url == API + "/messages/send" else
                       "Gmail request failed; check credentials and permissions.")
            raise _fail("gmail_request_failed", message) from None

    async def _authorize(self, force=False):
        async with self._lock:
            refresh = self._settings.get("GMAIL_REFRESH_TOKEN")
            if self._token and not force and (not self._expires or time.monotonic() < self._expires):
                _header(self._token)
                return
            if refresh:
                client = self._settings.get("GMAIL_CLIENT_ID")
                secret = self._settings.get("GMAIL_CLIENT_SECRET")
                if not client or not secret:
                    raise _fail("gmail_configuration", "Gmail refresh requires client ID and client secret.")
                result = await self._request("POST", OAUTH, data={
                    "client_id": client, "client_secret": secret,
                    "refresh_token": refresh, "grant_type": "refresh_token",
                })
                token = result.get("access_token")
                try:
                    _header(token)
                    lifetime = float(result.get("expires_in", 3600))
                    if not token or lifetime <= 0 or not math.isfinite(lifetime):
                        raise ValueError()
                except Exception:
                    raise _fail("gmail_auth_failed", "Gmail returned invalid authentication data.") from None
                self._token = token
                self._expires = time.monotonic() + max(0, lifetime - 60)
                if self._credential_file:
                    from .gmail_credentials import save
                    # Persist long-lived credentials only; access tokens expire.
                    save(self._credential_file, {k: self._settings[k] for k in (
                        "GMAIL_CLIENT_ID", "GMAIL_CLIENT_SECRET", "GMAIL_REFRESH_TOKEN")})
            elif not self._token:
                raise _fail("gmail_configuration", "Gmail credentials are not configured.")
            _header(self._token)

    async def _api(self, method, path, **kwargs):
        await self._authorize()
        try:
            return await self._request(method, API + path,headers={"Authorization": "Bearer " + self._token}, **kwargs)
        except CommunicationError as exc:
            if method=='GET' and exc.code=='authorization_required' and self._settings.get('GMAIL_REFRESH_TOKEN'):
                await self._authorize(force=True)
                return await self._request(method,API+path,headers={'Authorization':'Bearer '+self._token},**kwargs)
            raise

    async def validate(self):
        await self._authorize(force=bool(self._settings.get("GMAIL_REFRESH_TOKEN")))
        profile = await self._api("GET", "/profile")
        if self._credential_file and not self._settings.get("GMAIL_REFRESH_TOKEN"):
            from .gmail_credentials import save
            save(self._credential_file, {"GMAIL_ACCESS_TOKEN": self._token})
        return profile

    async def read(self, destination="", query=""):
        if not isinstance(query, str):
            raise _fail("invalid_input", "Invalid Gmail search query.")
        if destination:
            recipient = _recipient(destination)
            addr = HeaderParser(policy=policy.default).parsestr("To: " + recipient + "\n\n")["To"].addresses[0].addr_spec
            if any(c in addr for c in '\\"(){}'):
                raise _fail("invalid_input", "Recipient cannot be used as a search filter.")
            query = (query + ' from:"' + addr + '"').strip()
        return await self._api("GET", "/messages", params={"q": query, "maxResults": 20})

    async def get(self, message_id):
        result = await self._api("GET", "/messages/" + _id(message_id), params={"format": "full"})
        # Strip attachment bytes even when Gmail inlines a small attachment.
        def scrub(part):
            if not isinstance(part, dict):
                return
            body = part.get("body", {})
            attachment = any(isinstance(h, dict) and str(h.get("name", "")).lower() == "content-disposition"
                             and str(h.get("value", "")).lower().lstrip().startswith("attachment")
                             for h in part.get("headers", []))
            if attachment or part.get("filename") or (isinstance(body, dict) and body.get("attachmentId")):
                if isinstance(body, dict):
                    body.pop("data", None)
            for child in part.get("parts", []):
                scrub(child)
        scrub(result.get("payload", {}))
        def text_parts(part):
            if not isinstance(part,dict) or part.get('filename'):return []
            texts=[]
            if part.get('mimeType')=='text/plain' and part.get('body',{}).get('data'):
                encoded=part['body']['data']
                try:texts.append(base64.urlsafe_b64decode(encoded+'='*(-len(encoded)%4)).decode('utf-8',errors='replace')[:32768])
                except (ValueError,TypeError):pass
            for child in part.get('parts',[]):texts.extend(text_parts(child))
            return texts
        result['content']='\n'.join(text_parts(result.get('payload',{})))[:32768]
        return result

    async def prepare(self, destination, content, subject="", message_id=""):
        if not isinstance(content, str):
            raise _fail("invalid_input", "Email content must be text.")
        _header(subject)
        headers = {}
        thread_id = ""
        if message_id:
            original = await self.get(message_id)
            try:
                fields = {}
                for item in original["payload"]["headers"]:
                    name = item["name"].lower()
                    if name in fields and name in {"reply-to", "from", "subject", "message-id", "references"}:
                        raise ValueError()
                    fields[name] = item["value"]
                destination = destination or fields.get("reply-to") or fields["from"]
                # Gmail threading requires matching subject, so preserve it.
                original_subject = _header(fields.get("subject", ""))
                if subject and subject != original_subject:
                    raise ValueError()
                subject = original_subject
                thread_id = _id(original["threadId"])
                parent = _header(fields["message-id"])
                headers = _reply_headers({"In-Reply-To": parent,
                    "References": (fields.get("references", "") + " " + parent).strip()})
            except Exception:
                raise _fail("gmail_reply_invalid", "Cannot safely prepare this Gmail reply.") from None
        return {"destination": _recipient(destination), "content": content,
                "subject": subject, "message_id": message_id,
                "thread_id": thread_id, "headers": headers}

    async def send(self, destination, content, subject="", message_id="", thread_id="", headers=None):
        destination = _recipient(destination)
        subject = _header(subject)
        headers = _reply_headers({} if headers is None else headers)
        if not isinstance(content, str):
            raise _fail("invalid_input", "Email content must be text.")
        if message_id:
            _id(message_id)
        if thread_id:
            _id(thread_id)
        if bool(message_id) != bool(thread_id) or (bool(message_id) != bool(headers)):
            raise _fail("invalid_input", "Reply must be prepared before sending.")
        if message_id and set(headers) != {"In-Reply-To", "References"}:
            raise _fail("invalid_input", "Reply must include threading headers.")
        try:
            message = EmailMessage(policy=policy.SMTP)
            message["To"] = destination
            message["Subject"] = subject
            for name, value in headers.items():
                message[name] = value
            message.set_content(content)
            raw = base64.urlsafe_b64encode(message.as_bytes()).decode("ascii")
        except Exception:
            raise _fail("invalid_input", "Cannot encode email message.") from None
        payload = {"raw": raw}
        if thread_id:
            payload["threadId"] = thread_id
        return await self._api("POST", "/messages/send", json=payload)
