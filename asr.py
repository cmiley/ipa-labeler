"""Automatic transcription pipeline: word-level English ASR → per-word IPA.

Stack:
  - faster-whisper (CTranslate2) for English transcription with word timestamps
  - faster-whisper's built-in Silero VAD filter for skipping silent regions
  - gruut for English → IPA grapheme-to-phoneme

The two models are lazy-loaded on first call and cached for subsequent
requests. faster-whisper.transcribe is reentrant; gruut is pure-Python.
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Lazy singletons; first /api/clips/<id>/transcribe call pays the load cost.
_whisper_lock = threading.Lock()
_whisper_model = None


def _get_whisper():
    global _whisper_model
    if _whisper_model is None:
        with _whisper_lock:
            if _whisper_model is None:
                from faster_whisper import WhisperModel

                logger.info("loading faster-whisper tiny.en (int8)")
                _whisper_model = WhisperModel("tiny.en", device="cpu", compute_type="int8")
    return _whisper_model


def _word_to_ipa(word: str) -> str:
    import gruut

    word = word.strip(".,!?;:\"'()[]")
    if not word:
        return ""
    out_parts: list[str] = []
    for sent in gruut.sentences(word, lang="en-us"):
        for w in sent.words:
            if w.phonemes:
                out_parts.append("".join(w.phonemes))
    return "".join(out_parts)


def transcribe(audio_path: Path) -> dict[str, Any]:
    """Run ASR + G2P on an audio file. Returns a suggestion payload.

    Result shape:
        {
            "semanticLabel": "the full English transcription as one string",
            "segments": [
                {
                    "startTime": float,
                    "endTime": float,
                    "text": "<IPA>",        # gruut output for this word
                    "semanticLabel": "<word>",  # English token from Whisper
                },
                ...
            ],
        }
    """
    model = _get_whisper()
    segments_iter, info = model.transcribe(
        str(audio_path),
        word_timestamps=True,
        vad_filter=True,
        beam_size=1,  # tiny.en + beam=1 is fast and near-best on clean speech
    )

    words_out: list[dict[str, Any]] = []
    full_text_parts: list[str] = []

    for seg in segments_iter:
        if not seg.words:
            continue
        for w in seg.words:
            cleaned = w.word.strip()
            if not cleaned:
                continue
            full_text_parts.append(cleaned)
            ipa = _word_to_ipa(cleaned)
            words_out.append(
                {
                    "startTime": float(w.start),
                    "endTime": float(w.end),
                    "text": ipa,
                    "semanticLabel": cleaned.strip(".,!?;:\"'()[]"),
                }
            )

    return {
        "semanticLabel": " ".join(full_text_parts).strip(),
        "segments": words_out,
        "language": info.language,
        "languageProbability": info.language_probability,
    }
