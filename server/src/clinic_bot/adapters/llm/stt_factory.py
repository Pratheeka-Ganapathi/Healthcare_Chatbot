"""Speech-to-text for voice input: a Gemini Live transcription service per mic session."""

from __future__ import annotations

from pipecat.services.google.gemini_live.stt import GeminiSTTService
from pipecat.services.stt_service import STTService
from pipecat.transcriptions.language import Language

from clinic_bot.config import Settings

SAMPLE_RATE = 16_000  # the widget records 16 kHz mono PCM, the rate the model prefers
# Bias recognition toward words patients say to this front desk.
CLINIC_PHRASES = ["City Care Clinic", "appointment", "Indiranagar", "follow-up"]


class GeminiSTTFactory:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def create(self) -> STTService:
        return GeminiSTTService(
            api_key=self._settings.api_key("google"),
            sample_rate=SAMPLE_RATE,
            settings=GeminiSTTService.Settings(
                model=self._settings.stt_model,
                languages=[Language.EN_IN],  # English only in v1 (SPEC 1)
                adaptation_phrases=CLINIC_PHRASES,
            ),
            audio_passthrough=False,
        )
