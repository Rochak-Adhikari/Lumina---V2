"""Direct API-key gate. Gemini handles authentication and quota enforcement."""
import os
from pathlib import Path
from .base import ProviderUnavailable


class BudgetGuard:
    def __init__(self):
        self.api_key = self._load_key()

    @staticmethod
    def _load_key():
        # User-local storage supports Explorer launches without embedding keys in a package.
        # An explicit environment value (including empty) always takes precedence.
        from ..communication.manager import settings_from_environment
        settings = settings_from_environment()
        if 'GEMINI_API_KEY' in settings:
            return settings['GEMINI_API_KEY'].strip()
        try:
            local_data = Path(os.environ.get('LOCALAPPDATA', Path.home() / 'AppData' / 'Local'))
            candidates = (local_data / 'LUMINA' / '.gemini-key', Path('.gemini-key'))
            key_file = next((path for path in candidates if path.is_file()), None)
            return key_file.read_text(encoding='utf-8-sig').strip() if key_file else ''
        except (OSError, UnicodeError):
            return ''

    async def check(self):
        self.api_key = self._load_key()
        if not self.api_key:
            raise ProviderUnavailable("Gemini is not configured. Set GEMINI_API_KEY or update LUMINA's user-local .gemini-key; local capabilities remain operational.")
        return True

