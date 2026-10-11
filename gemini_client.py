"""Capybara Vision API client and worker threads."""

from typing import List, Tuple, Generator, Optional
from PySide6.QtCore import QThread, Signal
from PIL import Image
import io
import time

try:
    from google import genai
    from google.genai import types
except ImportError:
    genai = None
    types = None


def _sanitize_error_msg(error_msg: str, secret: str = "") -> str:
    """Strip secret keys, tokens, and internal raw query credentials from error messages."""
    msg = str(error_msg)
    if secret and secret.strip():
        msg = msg.replace(secret.strip(), "[REDACTED_API_KEY]")
    # Redact common key prefixes if exposed in URL strings
    import re
    msg = re.sub(r'AIza[0-9A-Za-z-_]{35}', '[REDACTED_API_KEY]', msg)
    msg = re.sub(r'(api_key|key)=[^&\s]+', r'\1=[REDACTED]', msg)
    return msg


def test_api_key(api_key: str) -> Tuple[bool, str, List[str]]:
    """Test the Capybara Vision API key and return (success, message, models_list)."""
    cleaned_key = api_key.strip() if api_key else ""
    if not cleaned_key:
        return False, "API key is empty.", []
    
    if genai is None:
        return False, "google-genai package is not installed.", []

    try:
        client = genai.Client(api_key=cleaned_key)
        model_names = []
        for m in client.models.list():
            # Filter models that support content generation
            name = m.name if hasattr(m, 'name') else str(m)
            # Remove models/ prefix if present
            if name.startswith("models/"):
                name = name[len("models/"):]
            if "gemini" in name.lower() and not "embedding" in name.lower():
                model_names.append(name)
        
        # Sort so modern flash models come first
        preferred_order = ["gemini-3.8-flash", "gemini-3.7-flash", "gemini-3.5-flash", "gemini-2.5-flash"]
        sorted_models = []
        for p in preferred_order:
            if p in model_names:
                sorted_models.append(p)
                model_names.remove(p)
        sorted_models.extend(sorted(model_names))

        if not sorted_models:
            sorted_models = ["gemini-3.8-flash", "gemini-3.7-flash", "gemini-3.5-flash"]
            
        return True, "API Key is valid!", sorted_models
    except Exception as e:
        safe_msg = _sanitize_error_msg(str(e), cleaned_key)
        return False, f"API test failed: {safe_msg}", []


class GeminiStreamWorker(QThread):
    """Worker thread that streams Capybara Vision responses for image + prompt analysis."""
    chunk_received = Signal(str)
    finished_success = Signal()
    failed = Signal(str)

    def __init__(
        self,
        api_key: str,
        model_name: str,
        prompt: str,
        image_bytes: Optional[bytes] = None,
        system_instruction: str = "",
        chat_history: Optional[List[dict]] = None
    ):
        super().__init__()
        self.api_key = api_key.strip()
        self.model_name = model_name
        self.prompt = prompt
        self.image_bytes = image_bytes
        self.system_instruction = system_instruction
        self.chat_history = chat_history or []
        self._is_cancelled = False

    def cancel(self):
        self._is_cancelled = True

    def run(self):
        if not self.api_key:
            self.failed.emit("Capybara Vision API key is not set. Please open Settings to configure your key.")
            return

        if genai is None:
            self.failed.emit("google-genai SDK not found.")
            return

        try:
            client = genai.Client(api_key=self.api_key)
            contents = []

            # If there's an image, pass it as first part
            if self.image_bytes:
                contents.append(
                    types.Part.from_bytes(data=self.image_bytes, mime_type="image/png")
                )

            # Add prior conversation turns if any
            for turn in self.chat_history:
                contents.append(turn["text"])

            contents.append(self.prompt)

            config = None
            if self.system_instruction:
                config = types.GenerateContentConfig(
                    system_instruction=self.system_instruction
                )

            models_to_try = [self.model_name]
            # Fast fallback alternatives if 503/high-demand or rate-limit spike occurs
            fallback_candidates = ["gemini-3.8-flash", "gemini-3.7-flash", "gemini-3.5-flash"]
            for fb in fallback_candidates:
                if fb not in models_to_try:
                    models_to_try.append(fb)

            last_error = None
            for current_model in models_to_try:
                if self._is_cancelled:
                    return

                # Retry up to 2 attempts for transient capacity spikes
                for attempt in range(2):
                    if self._is_cancelled:
                        return
                    try:
                        response = client.models.generate_content_stream(
                            model=current_model,
                            contents=contents,
                            config=config,
                        )

                        received_any = False
                        for chunk in response:
                            if self._is_cancelled:
                                return
                            text = chunk.text
                            if text:
                                received_any = True
                                self.chunk_received.emit(text)

                        if received_any:
                            self.finished_success.emit()
                            return
                    except Exception as e:
                        last_error = e
                        err_str = str(e).lower()
                        # Detect transient capacity / 503 high demand / 429 quota spikes
                        is_transient = any(w in err_str for w in ("503", "unavailable", "high demand", "429", "rate limit", "overloaded"))
                        if is_transient and attempt == 0 and not self._is_cancelled:
                            time.sleep(1.2)
                            continue
                        elif is_transient:
                            # Try next fallback model
                            break
                        else:
                            # Permanent error (e.g. invalid credentials) - fail fast
                            safe_err = _sanitize_error_msg(str(e), self.api_key)
                            self.failed.emit(f"Error querying Capybara Vision: {safe_err}")
                            return

            if not self._is_cancelled and last_error:
                safe_err = _sanitize_error_msg(str(last_error), self.api_key)
                self.failed.emit(f"Error querying Capybara Vision: {safe_err}")
        except Exception as e:
            if not self._is_cancelled:
                safe_err = _sanitize_error_msg(str(e), self.api_key)
                self.failed.emit(f"Error querying Capybara Vision: {safe_err}")
