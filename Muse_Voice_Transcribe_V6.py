"""Transcribe an audio recording with Meta's Muse Voice Transcribe API

Program metadata
----------------
Title: Muse Voice Transcribe
Author: Jose L. Agraz, PhD and the OU IT AI Consultant Team
Maintainer: J. Habashi, PhD 
AI coding assistant: Copilot
Created: 2026-11-14
Last updated: 2026-11-19
Version: 1.1
Python: 3.10 or later

Requires:
Python 3.10+
requests>=2.32,<3
pydantic>=2,<3
FFmpeg.
Install dependencies with "python -m pip install "requests>=2.32,<3" "pydantic>=2,<3"".
Set "MODEL_API_KEY" in the environment
Run "python Muse_Voice_Transcribe_V6.py --help" for usage.

Library roles
-------------
"argparse" parses command-line options
"hashlib" creates cache identity digests 
"json" handles API and application JSON
"math" performs numeric calculations
"os" manages environment and process resources
"re" matches normalized transcript tokens
"shutil" locates FFmpeg
"subprocess" runs FFmpeg
"tempfile" creates isolated chunk workspaces
"time" calculates retry delays
"unicodedata" normalizes Unicode text
"wave" reads and writes PCM WAV frames
"requests" sends authenticated API uploads and receives responses
"pydantic" validates settings and JSON schemas
"contextlib", "dataclasses", "datetime", and "email.utils" provide locking, 
typed chunk records, timestamps, and HTTP date parsing.

Audio Clips are mono, 16-kHz, 16-bit PCM WAV and upload sequentially. 
"CHUNK_SECONDS" is 1 to 599 (default 280); "OVERLAP_SECONDS" is 0 to30 (default 30), 
must be shorter than a chunk, and must keep every upload within the API's 9-minute limit.

Output is written to "muse_output/<recording>_<processing-id>/" beside the
source. Raw "chunk_NNN.json" responses are preserved. Combined text uses
timed turn transcripts, removes exact normalized text matches
only when their timestamps overlap, and keeps the later chunk's turn. Those
matches also align speaker labels across adjacent chunks when they yield an
unambiguous mapping. Unmatched or conflicting labels stay chunk-local.
Text matching is not voice identification and repeated phrases can be ambiguous.
It makes no change to raw chunk JSON files.
When turns are absent, the top-level transcript string is used. Combined turns
are sorted by source time; timestamps are turn-level, not word-level.
Word level matching might be the next step in the future, if the current speaker alignment 
is not sufficient.

Check "run_status.json" before using results: only "complete" guarantees every clip 
succeeded. Retries may resubmit a clip if a response was lost; write failures stop further uploads.
Individual files are atomic (Left unchanged), but the output set is not transactional.

Exit codes: 
0 success; 
1 processing/output failure; 
2 invalid configuration or missing dependencies; 
130 interrupted. 
See Meta's `speech-to-text documentation <https://dev.meta.ai/docs/speech-to-text>`_ and
`API reference <https://dev.meta.ai/docs/api-reference/voice/transcribe>`_.

Output files
------------
"chunk_NNN.json" contains the unmodified, Pydantic-validated API response
for that source chunk. 
"combined_transcript.txt" contains combined turn text in source order, with 
failed-chunk markers. 
"speaker_transcript.txt" contains timestamped turns and aligned or chunk-local speaker labels.
"combined_transcription.json" contains the application schema:
"sourceFile", "model", "audioEncoding", "mode", "overlapSeconds",
"transcript", source and processed durations, status, speaker scope, turns,
and chunk summaries. 
"failed_chunks.json" contains chunk numbers and safe error summaries. 
"run_status.json" records "running", "complete", "incomplete", "failed", or "interrupted" plus 
counts and timestamps.

Usage and recovery
------------------
Use "python Muse_Voice_Transcribe_V6.py /path/to/audio.wav" or pass
"--audio_file". With no path, "FILE_PATH / FILE_NAME" is used. 
Set "MODEL_API_KEY" in the environment.
The program normalizes WAV input with FFmpeg, creates numbered source chunks,
optionally prepends overlap frames, uploads sequentially, and writes files under
"muse_output/<source-stem>_<processing-id>/". Rerunning with the same file,
settings, and overlap reuses valid cached responses. A 402, authentication
failure, or permanent HTTP/client failure stops remaining uploads. Transient
network and retryable HTTP failures may consume every configured attempt before
a chunk is marked failed.

Do not use combined output until "run_status.json" is "complete".
"complete" means every chunk was processed successfully, not that the speech
recognition or speaker alignment is accurate. Remove ".muse.lock" only after
confirming no transcription process is active.

Implementation notes
--------------------
FFmpeg creates 16-kHz, mono, 16-bit PCM WAV source chunks. It selects the
first audio stream, ignores video, and resets segment timestamps. Segment
durations are measured from actual WAV frame counts rather than assumed
configuration boundaries, because container packet alignment can shift sample
boundaries.

For "OVERLAP_SECONDS > 0", each clip after the first prepends frames from the
tail of the immediately preceding source chunk. Source timeline offsets are
calculated from unique source frame counts, not from overlapped upload lengths.
Overlapping turn text is matched only when normalized text and mapped turn
intervals agree inside the overlap. 

Every JSON write uses UTF-8 and an atomic sibling temporary file. Text files
also use atomic replacement. "run_status.json" must be read as the authoritative completion indicator.
A 401, 403, 404, or 429 response stops later chunks; retryable 429/5xx responses
and network failures use exponential delay plus a valid server "Retry-After"
hint when present. A 402 response remains a terminal chunk failure.

Exit code 0 means processing completed successfully. Exit code 1 means output,
validation, or chunk processing failed. Exit code 2 means configuration,
dependencies, or the input CLI setup was invalid. Exit code 130 means the user
interrupted the process.

Troubleshooting
---------------
* HTTP 402: account credit, plan, or billing capacity may be exhausted.
* HTTP 504: an upstream gateway timed out; reduce chunk size or retry with a
  larger "MAX_ATTEMPTS" where the API and gateway permit it.
* HTTP 401/403/404/429: authentication, endpoint, or usage limits require
  configuration/account action, and later chunks are stopped.
* FFmpeg not found: install FFmpeg and ensure it is available on "PATH".
* Locked output: confirm no run is active before removing ".muse.lock".
* Incomplete status: retain cached "chunk_NNN.json" files and rerun; valid
  successful responses can be reused while failed chunks are retried.
* Speaker swaps: increase meaningful overlap and review ambiguous turns. Text
  matching cannot establish acoustic identity or resolve repeated phrases.

JSON examples
-------------
"run_status.json" is a status object with "state", "sourceFile",
"updatedAt", "totalChunks", "succeeded", "failed", and optional "message".
"failed_chunks.json" is a list of "chunk", "filename", and "error" objects.
"combined_transcription.json" has application "schema", source and API settings,
source/processed durations, a completion flag, "speakerScope", ordered "turns",
and ordered "chunks" summaries. Turn objects include "turnId", "startMs",
"endMs", "transcript", "speaker", "globalTurnIndex", "chunkIndex",
"sessionId", and optionally "speakerKey".

API key examples
-------------
Linux/macOS
export MODEL_API_KEY="your-api-key"
python Muse_Voice_Transcribe_V6.py
Windows
$env:MODEL_API_KEY = "your-api-key"
python Muse_Voice_Transcribe_V6.py

Persistence in powershell
[Environment]::SetEnvironmentVariable("MODEL_API_KEY", "your-api-key", "User")

Change history
--------------
-2026-11-14: Initial optimized transcription workflow.
-2026-11-16: Added overlap, source timelines, caching, recovery, overlap-aware
  transcript deduplication, and speaker-alignment behavior.
-2026-11-19: Added complete professional code documentation and Pydantic
  import/field guidance.
"""

from __future__ import annotations
import sys
# -----------------------------------------------------------
# Check before evaluating third-party imports or Pydantic model definitions.
if sys.version_info < (3, 10):
    print("Python 3.10 or newer is required.", file=sys.stderr)
    raise SystemExit(2)
# -----------------------------------------------------------
import argparse
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import tempfile
import time
import unicodedata
import wave
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Annotated, Any, Iterator, Literal
try:
    import requests
    import pydantic
except ImportError:
    print(
        'Missing dependency. Run: python -m pip install "requests>=2.32,<3" "pydantic>=2,<3"',
        file=sys.stderr,
    )
    raise SystemExit(2)
if pydantic.__version__.split(".")[0] != "2":
    print('Pydantic 2.x is required. Run: python -m pip install "pydantic>=2,<3"', file=sys.stderr)
    raise SystemExit(2)
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    FilePath,
    HttpUrl,
    SecretStr,
    StringConstraints,
    ValidationError,
    field_validator,
    model_validator,
)
# Pydantic import roles:
# BaseModel: base class for strict settings and JSON-schema models.
# ConfigDict: shared model behavior, including extra fields, frozen instances,
#   strict parsing, and safe validation errors.
# Field: aliases, defaults, constraints, and JSON field names.
# FilePath: validates that the configured input exists and is a file.
# HttpUrl: validates the API URL type; the API URL validator also requires HTTPS.
# SecretStr: hides the API key in model representations and comparisons.
# StringConstraints: defines nonblank, whitespace-trimmed string types.
# ValidationError: structured Pydantic validation failures.
# field_validator: validates or transforms one named model field.
# model_validator: cross-validates multiple fields after or before model parsing.
# ---------------------------- EDIT CONFIGURATION HERE ----------------------------
# Name of the recording when no command-line --audio_file/-a path is supplied.
FILE_NAME = "recording.wav"
# Directory searched for FILE_NAME when no command-line path is supplied.
FILE_PATH = Path(".")
# ---------------------------- 
# May need updating if Meta releases a new model. Check the API reference for the latest.
# https://dev.meta.ai/docs/speech-to-text
API_URL = "https://api.meta.ai/v1/asr/transcribe"
MODEL = "muse-voice-transcribe-1.0" 
# ---------------------------- 
# API diarization, endpointing, or push-to-talk behavior.
TRANSCRIPTION_MODE = "DIARIZATION"
# Optional recognition hints. Empty lists disable that hint category.
KEYWORDS: list[str] = []
LANGUAGE_BIAS: list[str] = ["Arabic", "English"]
# Base source duration for each clip, 1--599 seconds. The final source clip can be shorter.
CHUNK_SECONDS = 180
# PCM overlap prepended to clips after the first, 0--30 seconds.
OVERLAP_SECONDS = 0
# Total attempts for one clip, including the initial upload.
MAX_ATTEMPTS = 4
# Connection setup timeout and response inactivity timeout, in seconds.
CONNECT_TIMEOUT_SECONDS = 30
READ_TIMEOUT_SECONDS = 1800
# Maximum local FFmpeg preparation time, in seconds.
AUDIO_PREPARATION_TIMEOUT_SECONDS = 3600
# Upper bound for exponential retry delays, in seconds.
MAX_RETRY_DELAY_SECONDS = 300
# -------------------------- END USER CONFIGURATION ------------------------------
# HTTP responses retried for transient server/rate-limit conditions.
RETRYABLE_CODES = frozenset({429, 500, 502, 503, 504})
# Conservative maximum normalized transcript-token count for overlap matching.
MAX_DEDUP_TOKENS_PER_SECOND = 20
# Names and versions identify the application-level JSON contract.
COMBINED_SCHEMA_NAME = "MuseCombinedTranscription"
COMBINED_SCHEMA_VERSION = "1.1"
# Muse upload duration and multipart-size safety limits.
MAX_AUDIO_DURATION_MS = 600_000
MAX_WAV_BYTES = 31_900_000  # Leave room for multipart headers below 32 MB.
NonNegativeInt = Annotated[int, Field(ge=0)]
PositiveInt = Annotated[int, Field(gt=0)]
NonBlankString = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
TranscriptionMode = Literal["PUSH_TO_TALK", "ENDPOINTING", "DIARIZATION"]
class StrictModel(BaseModel):
    """Shared validation policy; error formatting never includes input values."""
    model_config = ConfigDict(
        strict=True,
        extra="forbid",
        frozen=True,
        populate_by_name=True,
        validate_default=True,
        hide_input_in_errors=True,
        allow_inf_nan=False,
    )
class TranscriptionSettings(StrictModel):
    """Validate customer settings once, before conversion or any API request."""
    input_audio_file: FilePath = Field(alias="INPUT_AUDIO_FILE", description="Existing nonempty source recording.")
    api_key: SecretStr = Field(alias="MODEL_API_KEY", repr=False, description="Environment-only bearer credential.")
    api_url: HttpUrl = Field(alias="API_URL", description="HTTPS Muse transcription endpoint.")
    model: NonBlankString = Field(alias="MODEL", description="Muse transcription model identifier.")
    mode: TranscriptionMode = Field(alias="TRANSCRIPTION_MODE", description="Diarization, endpointing, or push-to-talk mode.")
    keywords: list[NonBlankString] = Field(alias="KEYWORDS", description="Optional recognition hints.")
    language_bias: list[Literal["Arabic", "English"]] = Field(alias="LANGUAGE_BIAS", description="Optional language preferences.")
    chunk_seconds: Annotated[int, Field(ge=1, le=599)] = Field(alias="CHUNK_SECONDS", description="Base source chunk duration.")
    overlap_seconds: Annotated[int, Field(ge=0, le=30)] = Field(alias="OVERLAP_SECONDS", description="PCM overlap prepended to later chunks.")
    max_attempts: Annotated[int, Field(ge=1, le=20)] = Field(alias="MAX_ATTEMPTS", description="Total attempts per clip.")
    connect_timeout: Annotated[float, Field(gt=0)] = Field(alias="CONNECT_TIMEOUT_SECONDS", description="HTTP connection timeout.")
    read_timeout: Annotated[float, Field(gt=0)] = Field(alias="READ_TIMEOUT_SECONDS", description="HTTP response inactivity timeout.")
    preparation_timeout: Annotated[float, Field(gt=0)] = Field(
        alias="AUDIO_PREPARATION_TIMEOUT_SECONDS",
        description="Maximum local FFmpeg conversion duration.",
    )
    max_retry_delay: Annotated[float, Field(ge=1)] = Field(
        alias="MAX_RETRY_DELAY_SECONDS",
        description="Maximum retry or Retry-After delay.",
    )
    @field_validator("input_audio_file")
    @classmethod
    def nonempty_input(cls, value: Path) -> Path:
        """Reject an empty source file before any conversion or API work."""
        if value.stat().st_size == 0:
            raise ValueError("The input recording is empty.")
        return value
    @field_validator("api_key")
    @classmethod
    def configured_key(cls, value: SecretStr) -> SecretStr:
        """Read a usable API key without storing or exposing its value."""
        key = value.get_secret_value().strip()
        if not key or key.upper() in {"PASTE_YOUR_API_KEY_HERE", "YOUR_API_KEY", "YOUR-OWN-KEY"}:
            raise ValueError(
                "Set your own MODEL_API_KEY environment variable."
            )
        if any(character.isspace() for character in key):
            raise ValueError("Use the raw API key without whitespace or a 'Bearer ' prefix.")
        return SecretStr(key)
    @field_validator("api_url")
    @classmethod
    def secure_api_url(cls, value: HttpUrl) -> HttpUrl:
        """Require HTTPS and reject credentials or fragments in the API URL."""
        if value.scheme != "https" or value.username or value.password or value.fragment:
            raise ValueError("API_URL must use HTTPS without embedded credentials or a fragment.")
        return value
    @model_validator(mode="after")
    def valid_chunk_overlap(self) -> TranscriptionSettings:
        """Require overlap and chunk lengths to remain within API limits."""
        if self.overlap_seconds >= self.chunk_seconds and self.overlap_seconds != 0:
            raise ValueError("OVERLAP_SECONDS must be shorter than CHUNK_SECONDS.")
        if self.chunk_seconds + self.overlap_seconds > MAX_AUDIO_DURATION_MS // 1000:
            raise ValueError(
                "CHUNK_SECONDS plus OVERLAP_SECONDS must not exceed the 10-minute API limit."
            )
        return self
class Turn(StrictModel):
    """One API speech turn. Preserve additional API fields in raw responses."""
    model_config = ConfigDict(extra="allow")
    turn_id: NonNegativeInt = Field(alias="turnId")
    start_ms: NonNegativeInt = Field(alias="startMs")
    end_ms: NonNegativeInt = Field(alias="endMs")
    transcript: str  # Empty text is valid, including silence or an unfinished turn.
    speaker: str | None = None
    @model_validator(mode="after")
    def valid_interval(self) -> Turn:
        """Require each turn to end at or after its start timestamp."""
        if self.end_ms < self.start_ms:
            raise ValueError("Turn timestamps must satisfy 0 <= startMs <= endMs.")
        return self
    def to_dict(self, offset_ms: int = 0) -> dict[str, Any]:
        """Return standard turn fields shifted onto the full recording timeline."""
        result = {
            "turnId": self.turn_id,
            "startMs": self.start_ms + offset_ms,
            "endMs": self.end_ms + offset_ms,
            "transcript": self.transcript,
        }
        if self.speaker is not None:
            result["speaker"] = self.speaker
        return result
class TranscribeResponse(StrictModel):
    """Validate buffered responses; unknown fields remain in the saved raw JSON."""
    model_config = ConfigDict(extra="allow")
    session_id: NonBlankString = Field(alias="sessionId")
    transcript: str
    audio_duration_ms: NonNegativeInt = Field(alias="audioDurationMs")
    turns: list[Turn]
    @model_validator(mode="after")
    def ordered_turns(self) -> TranscribeResponse:
        """Require unique ascending turn IDs and timestamps inside the clip."""
        ids = [turn.turn_id for turn in self.turns]
        if ids != sorted(ids) or len(ids) != len(set(ids)):
            raise ValueError("turns must have unique turnId values in ascending order.")
        if any(turn.end_ms > self.audio_duration_ms for turn in self.turns):
            raise ValueError("A turn's endMs must not exceed audioDurationMs.")
        return self
class CombinedTurn(Turn):
    """A speech turn on the full recording timeline with source provenance.
    ``speaker`` is the API's local label unless an unambiguous overlap match
    carries a label from the previous chunk forward. ``speakerKey`` identifies
    that aligned label in combined output; it is not a guarantee of voice
    identity and is session-local without overlap evidence.
    """
    model_config = ConfigDict(extra="forbid")
    global_turn_index: NonNegativeInt = Field(alias="globalTurnIndex")
    chunk_index: NonNegativeInt = Field(alias="chunkIndex")
    session_id: NonBlankString = Field(alias="sessionId")
    speaker_key: str | None = Field(default=None, alias="speakerKey")
class ChunkSummary(StrictModel):
    """Describe a clip and its unique source interval, including on failure."""
    chunk_index: NonNegativeInt = Field(alias="chunkIndex")
    source_chunk_duration_ms: PositiveInt = Field(alias="sourceChunkDurationMs")
    timeline_start_ms: NonNegativeInt = Field(alias="timelineStartMs")
    response_file: NonBlankString = Field(alias="responseFile")
    status: Literal["succeeded", "failed"]
    session_id: NonBlankString | None = Field(default=None, alias="sessionId")
    audio_duration_ms: NonNegativeInt | None = Field(default=None, alias="audioDurationMs")
    @model_validator(mode="after")
    def success_requires_response(self) -> ChunkSummary:
        """Require API identity and duration for every successful chunk."""
        if self.status == "succeeded" and (
            self.session_id is None or self.audio_duration_ms is None
        ):
            raise ValueError("A successful chunk requires sessionId and audioDurationMs.")
        return self
class SchemaInfo(StrictModel):
    """Identify the version of the application's combined-result schema."""
    name: Literal["MuseCombinedTranscription"] = COMBINED_SCHEMA_NAME
    version: Literal["1.1"] = COMBINED_SCHEMA_VERSION
class CombinedTranscription(StrictModel):
    """The application's combined schema, distinct from Meta's response schema."""
    schema_info: SchemaInfo = Field(default_factory=SchemaInfo, alias="schema")
    source_file: NonBlankString = Field(alias="sourceFile")
    model: NonBlankString
    audio_encoding: Literal["WAV"] = Field(default="WAV", alias="audioEncoding")
    mode: TranscriptionMode
    overlap_seconds: Annotated[int, Field(ge=0, le=30)] = Field(
        default=0, alias="overlapSeconds"
    )
    transcript: str
    audio_duration_ms: PositiveInt = Field(alias="audioDurationMs")
    processed_audio_duration_ms: NonNegativeInt = Field(alias="processedAudioDurationMs")
    complete: bool
    speaker_scope: str = Field(
        default=(
            "speakerKey is linked across adjacent chunks only by unambiguous "
            "matching transcript turns in the overlap; otherwise it is "
            "session-local and does not identify a person. No guarantee is "
            "made that all same-letter API labels identify the same real speaker "
            "across chunks."
        ),
        alias="speakerScope",
    )
    turns: list[CombinedTurn]
    chunks: Annotated[list[ChunkSummary], Field(min_length=1)]
    @model_validator(mode="after")
    def consistent_summary(self) -> CombinedTranscription:
        """Cross-check status, timelines, durations, and combined turn provenance."""
        if self.complete != all(chunk.status == "succeeded" for chunk in self.chunks):
            raise ValueError("complete must match chunk success/failure states.")
        offset = 0
        overlap_ms = self.overlap_seconds * 1000
        for index, chunk in enumerate(self.chunks):
            if chunk.chunk_index != index or chunk.timeline_start_ms != offset:
                raise ValueError("Chunk indices and timeline offsets must be consecutive.")
            if index < len(self.chunks) - 1 and chunk.source_chunk_duration_ms <= overlap_ms:
                raise ValueError("Overlap must be shorter than every non-final source chunk.")
            offset += chunk.source_chunk_duration_ms
        if self.audio_duration_ms != offset:
            raise ValueError("audioDurationMs must equal the sum of source chunk durations.")
        processed = sum(
            chunk.audio_duration_ms or 0 for chunk in self.chunks if chunk.status == "succeeded"
        )
        if self.processed_audio_duration_ms != processed:
            raise ValueError("processedAudioDurationMs must match successful API responses.")
        for index, turn in enumerate(self.turns):
            if turn.global_turn_index != index or turn.chunk_index >= len(self.chunks):
                raise ValueError("A combined turn has an invalid globalTurnIndex or chunkIndex.")
            chunk = self.chunks[turn.chunk_index]
            if chunk.status != "succeeded" or turn.session_id != chunk.session_id:
                raise ValueError("A combined turn must reference its successful source session.")
            clip_start_ms = max(0, chunk.timeline_start_ms - overlap_ms)
            if not (
                clip_start_ms
                <= turn.start_ms
                <= turn.end_ms
                <= clip_start_ms + (chunk.audio_duration_ms or 0)
            ):
                raise ValueError("A combined turn must lie within its source session's timeline.")
        return self
class ChunkFailure(StrictModel):
    """Describe a clip that could not be transcribed or validated."""
    chunk: NonNegativeInt
    filename: NonBlankString
    error: NonBlankString
class RunStatus(StrictModel):
    """Written last at completion; a failed/interrupted run must not look complete."""
    state: Literal["running", "complete", "incomplete", "failed", "interrupted"]
    source_file: NonBlankString = Field(alias="sourceFile")
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc), alias="updatedAt"
    )
    total_chunks: PositiveInt | None = Field(default=None, alias="totalChunks")
    succeeded: NonNegativeInt = 0
    failed: NonNegativeInt = 0
    message: str | None = None
class TranscriptionError(RuntimeError):
    """An actionable, safe-to-display API/processing failure."""
    def __init__(self, message: str, *, stop_remaining: bool = False):
        """Store the display message and whether later uploads should stop."""
        super().__init__(message)
        self.stop_remaining = stop_remaining
def validation_message(error: ValidationError) -> str:
    """Report field paths/messages, omitting input values, context and URLs."""
    return "; ".join(
        f"{'.'.join(str(part) for part in item['loc']) or 'response'}: {item['msg']}"
        for item in error.errors(include_input=False, include_context=False, include_url=False)
    )
def build_settings(input_path: Path) -> TranscriptionSettings:
    """Read editable globals once and validate them, including the input file."""
    return TranscriptionSettings(
        input_audio_file=input_path,
        api_key=os.environ.get("MODEL_API_KEY", ""),
        api_url=API_URL,
        model=MODEL,
        mode=TRANSCRIPTION_MODE,
        keywords=KEYWORDS,
        language_bias=LANGUAGE_BIAS,
        chunk_seconds=CHUNK_SECONDS,
        overlap_seconds=OVERLAP_SECONDS,
        max_attempts=MAX_ATTEMPTS,
        connect_timeout=CONNECT_TIMEOUT_SECONDS,
        read_timeout=READ_TIMEOUT_SECONDS,
        preparation_timeout=AUDIO_PREPARATION_TIMEOUT_SECONDS,
        max_retry_delay=MAX_RETRY_DELAY_SECONDS,
    )
def atomic_write_text(path: Path, content: str) -> None:
    """Flush a unique sibling temporary file, then atomically replace the target.
    OSError propagates: storage failures abort processing rather than trigger more
    uploads. Atomic replacement protects one file, not the whole output set.
    """
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as stream:
            temporary_path = Path(stream.name)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
def save_json(path: Path, data: Any) -> None:
    """Write readable UTF-8 JSON; disallow nonstandard NaN/infinite numbers."""
    atomic_write_text(path, json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False) + "\n")
def save_run_status(
    output_directory: Path,
    source_file: str,
    state: str,
    *,
    total: int | None = None,
    succeeded: int = 0,
    failed: int = 0,
    message: str | None = None,
) -> None:
    """Validate status metadata before writing it. Never include an API key."""
    status = RunStatus(
        state=state,
        source_file=source_file,
        total_chunks=total,
        succeeded=succeeded,
        failed=failed,
        message=message,
    )
    save_json(
        output_directory / "run_status.json",
        status.model_dump(mode="json", by_alias=True, exclude_none=True),
    )
@contextmanager
def output_lock(directory: Path) -> Iterator[None]:
    """Exclude concurrent writers; release our lock on ordinary errors/Ctrl+C."""
    lock_path = directory / ".muse.lock"
    try:
        descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as error:
        raise TranscriptionError(
            f"Output directory is locked: {lock_path}. Another run may be active. "
            "If no run is active, remove this stale lock and retry."
        ) from error
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(f"pid={os.getpid()}\nstarted={datetime.now(timezone.utc).isoformat()}\n")
        yield
    finally:
        lock_path.unlink(missing_ok=True)
def file_hash(path: Path) -> str:
    """Return a SHA-256 digest without reading the entire recording into memory."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()
def processing_id(input_path: Path, settings: TranscriptionSettings) -> str:
    """Keep the legacy cache key at zero overlap; distinguish other overlap values."""
    cache_settings = {
        "model": settings.model,
        "mode": settings.mode,
        "keywords": settings.keywords,
        "languageBias": settings.language_bias,
        "chunkSeconds": settings.chunk_seconds,
        "audioEncoding": "WAV",
        "sampleRateHz": 16000,
        "channels": 1,
    }
    if settings.overlap_seconds:
        cache_settings["overlapSeconds"] = settings.overlap_seconds
    digest = hashlib.sha256()
    digest.update(file_hash(input_path).encode("ascii"))
    digest.update(json.dumps(cache_settings, sort_keys=True, separators=(",", ":")).encode("utf-8"))
    return digest.hexdigest()[:12]
def wav_duration_ms(path: Path) -> int:
    """Check the actual prepared WAV format, byte size and API duration cap."""
    if path.stat().st_size > MAX_WAV_BYTES:
        raise TranscriptionError(
            "A prepared WAV exceeds the upload size budget. Reduce CHUNK_SECONDS or OVERLAP_SECONDS."
        )
    with wave.open(str(path), "rb") as audio:
        if (
            audio.getnchannels(),
            audio.getsampwidth(),
            audio.getframerate(),
            audio.getcomptype(),
        ) != (1, 2, 16000, "NONE"):
            raise TranscriptionError("Prepared audio must be mono, 16-bit PCM WAV at 16 kHz.")
        frames = audio.getnframes()
        duration = round(frames * 1000 / audio.getframerate())
        if frames > 0:
            audio.setpos(frames - 1)
            if len(audio.readframes(1)) != 2:
                raise TranscriptionError(
                    "A prepared WAV is truncated. Check available temporary disk space."
                )
    if frames <= 0 or duration <= 0:
        raise TranscriptionError("FFmpeg produced an empty or too-short audio clip.")
    if frames > 16000 * (MAX_AUDIO_DURATION_MS // 1000):
        raise TranscriptionError(
            "A prepared clip exceeds 10 minutes. Reduce CHUNK_SECONDS or OVERLAP_SECONDS."
        )
    return duration
def _wav_frame_count(path: Path) -> int:
    """Read the exact frame count from an already-validated normalized WAV."""
    with wave.open(str(path), "rb") as audio:
        return audio.getnframes()
def format_timestamp(milliseconds: int) -> str:
    """Convert a nonnegative millisecond position to HH:MM:SS.mmm."""
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, milliseconds = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{milliseconds:03d}"
_TRANSCRIPT_TOKEN = re.compile(r"[\w\u0640\u064b-\u065f\u0670]+", re.UNICODE)
def _normalized_transcript_tokens(text: str) -> tuple[list[str], list[re.Match[str]]]:
    """Return comparable tokens and their source spans, ignoring Arabic marks."""
    tokens: list[str] = []
    token_matches: list[re.Match[str]] = []
    for match in _TRANSCRIPT_TOKEN.finditer(text):
        token = "".join(
            character
            for character in unicodedata.normalize("NFKC", match.group()).casefold()
            if character != "\u0640" and unicodedata.category(character) != "Mn"
        )
        if token:
            tokens.append(token)
            token_matches.append(match)
    return tokens, token_matches
def remove_overlapping_transcript_prefix(
    previous_text: str, current_text: str, overlap_seconds: int
) -> str:
    """Remove an exact normalized suffix/prefix match from adjacent clip text.
    The match is bounded by the configured overlap and a conservative token-rate
    limit. Nonmatching text is retained; no fuzzy or translation-based edits are
    attempted.
    """
    if overlap_seconds <= 0 or not previous_text or not current_text:
        return current_text
    previous_tokens, _ = _normalized_transcript_tokens(previous_text)
    current_tokens, current_matches = _normalized_transcript_tokens(current_text)
    maximum_match = min(
        len(previous_tokens),
        len(current_tokens),
        overlap_seconds * MAX_DEDUP_TOKENS_PER_SECOND,
    )
    for token_count in range(maximum_match, 0, -1):
        if previous_tokens[-token_count:] == current_tokens[:token_count]:
            boundary = current_matches[token_count - 1].end()
            return current_text[boundary:].lstrip(" \t\r\n,،.;:!?؟؛…—-")
    return current_text
def overlapping_turn_matches(
    previous_turns: list[CombinedTurn],
    current_turns: list[CombinedTurn],
    overlap_start_ms: int,
    overlap_end_ms: int,
) -> list[tuple[CombinedTurn, CombinedTurn]]:
    """Pair exact transcript matches whose turn times intersect the overlap.
    This function does not establish true speaker identity. A match proves only
    that normalized turn text and source timing agree. Repeated speech can match
    incorrectly, and differing API transcripts can prevent alignment.
    """
    matched_previous_ids: set[int] = set()
    matches: list[tuple[CombinedTurn, CombinedTurn]] = []
    for current in current_turns:
        current_tokens, _ = _normalized_transcript_tokens(current.transcript)
        if not current_tokens:
            continue
        best_match: tuple[CombinedTurn, int] | None = None
        for previous in previous_turns:
            if previous.turn_id in matched_previous_ids:
                continue
            previous_tokens, _ = _normalized_transcript_tokens(previous.transcript)
            if previous_tokens != current_tokens:
                continue
            shared_start_ms = max(
                overlap_start_ms, previous.start_ms, current.start_ms
            )
            shared_end_ms = min(overlap_end_ms, previous.end_ms, current.end_ms)
            shared_duration_ms = shared_end_ms - shared_start_ms
            if shared_duration_ms > 0 and (
                best_match is None or shared_duration_ms > best_match[1]
            ):
                best_match = (previous, shared_duration_ms)
        if best_match is not None:
            previous = best_match[0]
            matched_previous_ids.add(previous.turn_id)
            matches.append((previous, current))
    return matches
def overlapping_duplicate_turn_ids(
    previous_turns: list[CombinedTurn],
    current_turns: list[CombinedTurn],
    overlap_start_ms: int,
    overlap_end_ms: int,
) -> set[int]:
    """Return prior turn IDs duplicated by exact text within the overlap."""
    return {
        previous.turn_id
        for previous, _ in overlapping_turn_matches(
            previous_turns, current_turns, overlap_start_ms, overlap_end_ms
        )
    }
def align_speakers_from_overlap(
    current_turns: list[CombinedTurn],
    matches: list[tuple[CombinedTurn, CombinedTurn]],
) -> list[CombinedTurn]:
    """Carry prior speaker labels forward only for conservative unambiguous matches.
    Each current-chunk label votes for exactly matched previous
    (speaker, speakerKey) targets. A target is accepted only when one target wins
    with the highest vote count and that target is claimed by exactly one current
    label. This avoids one-to-many mappings, but it still cannot guarantee the
    real speaker identity: overlap matching is based on transcript text and timing,
    not acoustic voice embeddings.
    Without qualifying evidence, the returned turn keeps its original chunk-local
    speaker and speakerKey. Raw API chunk JSON is never modified.
    """
    votes: dict[str, dict[tuple[str, str], int]] = {}
    for previous, current in matches:
        if previous.speaker is None or previous.speaker_key is None or current.speaker is None:
            continue
        # Count only exact transcript matches; repeated or unsupported text is
        # not enough to create a speaker identity mapping.
        target = (previous.speaker, previous.speaker_key)
        speaker_votes = votes.setdefault(current.speaker, {})
        speaker_votes[target] = speaker_votes.get(target, 0) + 1
    mappings: dict[str, tuple[str, str]] = {}
    for speaker, speaker_votes in votes.items():
        highest = max(speaker_votes.values())
        winners = [target for target, count in speaker_votes.items() if count == highest]
        if len(winners) == 1:
            mappings[speaker] = winners[0]
    target_claims: dict[tuple[str, str], int] = {}
    for target in mappings.values():
        # Reject mappings that would assign two current labels to one prior
        # speakerKey, because that is ambiguous evidence.
        target_claims[target] = target_claims.get(target, 0) + 1
    aligned_turns: list[CombinedTurn] = []
    for turn in current_turns:
        target = mappings.get(turn.speaker) if turn.speaker is not None else None
        if target is not None and target_claims[target] == 1:
            turn = turn.model_copy(
                update={"speaker": target[0], "speaker_key": target[1]}
            )
        aligned_turns.append(turn)
    return aligned_turns
def load_cached_response(path: Path) -> dict[str, Any] | None:
    """Reuse valid responses. Replace corrupt JSON, but propagate file-access errors."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        TranscribeResponse.model_validate(payload)
        return payload
    except FileNotFoundError:
        return None
    except (UnicodeError, ValueError):
        print(f"Ignoring corrupt or invalid cached response: {path.name}")
        return None
def completed_run_is_reusable(
    output_directory: Path, settings: TranscriptionSettings
) -> bool:
    """Return whether a prior successful run can be reused without conversion.
    The status, combined result, text output, failure list, and every cached API
    response must validate. Missing or malformed output causes normal processing
    to resume; filesystem access errors other than missing files still propagate.
    """
    try:
        status = RunStatus.model_validate_json(
            (output_directory / "run_status.json").read_text(encoding="utf-8")
        )
        if (
            status.state != "complete"
            or status.total_chunks is None
            or status.succeeded != status.total_chunks
            or status.failed != 0
        ):
            return False
        combined = CombinedTranscription.model_validate(
            json.loads(
                (output_directory / "combined_transcription.json").read_text(encoding="utf-8")
            )
        )
        if (
            combined.source_file != settings.input_audio_file.name
            or combined.model != settings.model
            or combined.mode != settings.mode
            or combined.overlap_seconds != settings.overlap_seconds
            or len(combined.chunks) != status.total_chunks
            or any(chunk.status != "succeeded" for chunk in combined.chunks)
            or (output_directory / "combined_transcript.txt").read_text(encoding="utf-8")
            != combined.transcript
            or not (output_directory / "speaker_transcript.txt").is_file()
            or json.loads(
                (output_directory / "failed_chunks.json").read_text(encoding="utf-8")
            )
            != []
        ):
            return False
        for index, chunk in enumerate(combined.chunks):
            if chunk.response_file != f"chunk_{index:03d}.json":
                return False
            if load_cached_response(output_directory / chunk.response_file) is None:
                return False
        return True
    except (FileNotFoundError, UnicodeError, ValueError):
        return False
def _copy_wave_frames(
    source: wave.Wave_read, destination: wave.Wave_write, frame_count: int
) -> None:
    """Copy exact PCM frames in bounded blocks.
    ``frame_count`` is expressed in normalized 16-kHz PCM frames. ``frame_size``
    combines channel count and sample width so reads can detect truncation and
    malformed frame boundaries. ``writeframesraw`` preserves streaming memory use.
    """
    frame_size = source.getnchannels() * source.getsampwidth()
    remaining = frame_count
    while remaining:
        block = source.readframes(min(remaining, 65_536))
        copied_frames = len(block) // frame_size
        if not block or len(block) % frame_size or copied_frames > remaining:
            raise TranscriptionError("A prepared WAV is truncated while adding overlap.")
        destination.writeframesraw(block)
        remaining -= copied_frames
def _add_audio_overlap(chunks: list[Path], directory: Path, overlap_seconds: int) -> list[Path]:
    """Prepend each clip with audio from the tail of the preceding source clip."""
    if overlap_seconds == 0 or len(chunks) < 2:
        return chunks
    overlapping_chunks = [chunks[0]]
    for index in range(1, len(chunks)):
        previous_path = chunks[index - 1]
        current_path = chunks[index]
        output_path = directory / f"overlap_{index:06d}.wav"
        with wave.open(str(previous_path), "rb") as previous, wave.open(
            str(current_path), "rb"
        ) as current:
            previous_format = (
                previous.getnchannels(),
                previous.getsampwidth(),
                previous.getframerate(),
                previous.getcomptype(),
            )
            current_format = (
                current.getnchannels(),
                current.getsampwidth(),
                current.getframerate(),
                current.getcomptype(),
            )
            if previous_format != current_format or current_format != (1, 2, 16000, "NONE"):
                raise TranscriptionError("Audio chunks have incompatible WAV formats.")
            overlap_frames = overlap_seconds * previous.getframerate()
            if previous.getnframes() < overlap_frames:
                raise TranscriptionError(
                    "A source chunk is shorter than OVERLAP_SECONDS; reduce the overlap."
                )
            previous.setpos(previous.getnframes() - overlap_frames)
            current_frames = current.getnframes()
            with wave.open(str(output_path), "wb") as output:
                output.setnchannels(current.getnchannels())
                output.setsampwidth(current.getsampwidth())
                output.setframerate(current.getframerate())
                output.setcomptype(current.getcomptype(), "not compressed")
                _copy_wave_frames(previous, output, overlap_frames)
                _copy_wave_frames(current, output, current_frames)
        overlapping_chunks.append(output_path)
    return overlapping_chunks
@dataclass(frozen=True)
class PreparedChunk:
    """An uploaded clip and its exact unique source interval."""
    audio_path: Path
    source_start_ms: int
    source_duration_ms: int
def split_audio(
    input_path: Path, chunk_directory: Path, settings: TranscriptionSettings, ffmpeg_path: str
) -> list[PreparedChunk]:
    """Normalize and segment audio, retaining exact source offsets.
    FFmpeg maps the first audio stream and writes mono, 16-kHz, signed 16-bit
    PCM files. Segment output frame counts are measured per WAV and converted
    to source milliseconds so overlap upload lengths cannot alter timelines.
    """
    source_chunk_directory = chunk_directory / "source_chunks"
    source_chunk_directory.mkdir()
    command = [
        ffmpeg_path,
        "-nostdin",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(input_path),
        "-map",
        "0:a:0",
        "-vn",
        "-ar",
        "16000",
        "-ac",
        "1",
        "-c:a",
        "pcm_s16le",
        "-f",
        "segment",
        "-segment_time",
        str(settings.chunk_seconds),
        "-reset_timestamps",
        "1",
        str(source_chunk_directory / "chunk_%06d.wav"),
    ]
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=settings.preparation_timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as error:
        raise TranscriptionError(
            "Audio conversion timed out. Check the input or increase AUDIO_PREPARATION_TIMEOUT_SECONDS."
        ) from error
    if result.returncode != 0:
        detail = result.stderr.strip()[-1500:] or "FFmpeg returned no diagnostic text."
        raise TranscriptionError(
            f"Audio conversion failed. Check that the recording is readable and contains audio. {detail}"
        )
    chunks = sorted(
        source_chunk_directory.glob("chunk_*.wav"),
        key=lambda path: int(path.stem.split("_")[-1]),
    )
    if not chunks:
        raise TranscriptionError("FFmpeg did not produce any audio clips.")
    source_frame_counts = []
    for chunk in chunks:
        wav_duration_ms(chunk)
        source_frame_counts.append(_wav_frame_count(chunk))
    upload_chunks = _add_audio_overlap(chunks, chunk_directory, settings.overlap_seconds)
    prepared_chunks: list[PreparedChunk] = []
    source_start_frames = 0
    for audio_path, source_frame_count in zip(upload_chunks, source_frame_counts):
        source_start_ms = round(source_start_frames * 1000 / 16000)
        source_end_ms = round((source_start_frames + source_frame_count) * 1000 / 16000)
        prepared_chunks.append(
            PreparedChunk(
                audio_path=audio_path,
                source_start_ms=source_start_ms,
                source_duration_ms=source_end_ms - source_start_ms,
            )
        )
        source_start_frames += source_frame_count
    return prepared_chunks
def retry_delay(response: requests.Response, attempt: int, maximum: float) -> float:
    """Honor valid Retry-After hints; stop rather than retry sooner than requested."""
    retry_after = response.headers.get("Retry-After", "")
    delay: float | None = None
    try:
        candidate = float(retry_after)
        if math.isfinite(candidate):
            delay = max(candidate, 1.0)
    except ValueError:
        try:
            retry_time = parsedate_to_datetime(retry_after)
            if retry_time.tzinfo is None:
                retry_time = retry_time.replace(tzinfo=timezone.utc)
            delay = max((retry_time - datetime.now(timezone.utc)).total_seconds(), 1.0)
        except (TypeError, ValueError, OverflowError):
            pass
    if delay is None:
        delay = min(float(2 ** (attempt - 1)), maximum)
    if delay > maximum:
        raise TranscriptionError(
            "The API requested a retry delay longer than MAX_RETRY_DELAY_SECONDS. "
            "Rerun later or increase that setting.",
            stop_remaining=True,
        )
    return delay
def http_error_message(status: int) -> str:
    """Use actionable messages rather than echoing an untrusted response body."""
    guidance = {
        400: "Check the model, transcription mode, and prepared audio format/duration.",
        401: "The API rejected the key. Check or replace MODEL_API_KEY.",
        403: "The key lacks access. Check your Meta project/model permissions.",
        404: "Check API_URL, the model name, and whether your account has access.",
        406: "The API did not accept the requested JSON response format.",
        413: "The upload is too large. Reduce CHUNK_SECONDS.",
        429: "The API rate/concurrency limit was reached. Rerun later.",
    }.get(
        status,
        "The API could not complete the request. Check service availability and configuration.",
    )
    return f"HTTP {status}: {guidance}"
def transcribe(
    audio_path: Path, settings: TranscriptionSettings, session: requests.Session
) -> dict[str, Any]:
    """Upload one prepared WAV; retry transient HTTP/network failures only.
    Returns the original JSON after Pydantic validation. Raises TranscriptionError
    for API/response errors and propagates local OSError so storage failures abort.
    The multipart request contains a JSON ``request`` part and a WAV ``audio``
    part. Authorization uses a bearer token from ``SecretStr``. TLS verification
    remains enabled. 401/403/404/429 are terminal; 429/5xx responses and network
    failures retry up to ``MAX_ATTEMPTS``. 402 is a terminal chunk failure.
    """
    request_data = {
        "model": settings.model,
        "audioEncoding": "WAV",
        "mode": settings.mode,
    }
    if settings.keywords:
        request_data["keywords"] = settings.keywords
    if settings.language_bias:
        request_data["languageBias"] = settings.language_bias
    for attempt in range(1, settings.max_attempts + 1):
        try:
            with audio_path.open("rb") as audio:
                with session.post(
                    str(settings.api_url),
                    headers={
                        "Authorization": f"Bearer {settings.api_key.get_secret_value()}",
                        "Accept": "application/json",
                    },
                    files={
                        "request": (None, json.dumps(request_data), "application/json"),
                        "audio": (audio_path.name, audio, "audio/wav"),
                    },
                    timeout=(settings.connect_timeout, settings.read_timeout),
                    allow_redirects=False,
                ) as response:
                    if 200 <= response.status_code < 300:
                        try:
                            payload = response.json()
                        except ValueError as error:
                            raise TranscriptionError(
                                "The API returned invalid JSON. The clip was not saved as successful."
                            ) from error
                        try:
                            TranscribeResponse.model_validate(payload)
                        except ValidationError as error:
                            raise TranscriptionError(
                                f"Invalid API response: {validation_message(error)}"
                            ) from error
                        return payload
                    if (
                        response.status_code not in RETRYABLE_CODES
                        or attempt == settings.max_attempts
                    ):
                        raise TranscriptionError(
                            http_error_message(response.status_code),
                            stop_remaining=response.status_code in {401, 403, 404, 429},
                        )
                    delay = retry_delay(response, attempt, settings.max_retry_delay)
                    reason = f"HTTP {response.status_code}"
        except requests.exceptions.SSLError as error:
            raise TranscriptionError(
                "TLS certificate verification failed. Check your certificate/proxy configuration; verification remains enabled.",
                stop_remaining=True,
            ) from error
        except (requests.ConnectionError, requests.Timeout) as error:
            if attempt == settings.max_attempts:
                raise TranscriptionError(
                    f"Network failure after {settings.max_attempts} attempt(s). Check connectivity and rerun."
                ) from error
            delay = min(float(2 ** (attempt - 1)), settings.max_retry_delay)
            reason = "Network failure"
        except requests.RequestException as error:
            raise TranscriptionError(
                "The HTTP request could not be sent. Check the endpoint and local network configuration.",
                stop_remaining=True,
            ) from error
        print(
            f"{reason}. Retrying in {delay:g} seconds (next attempt {attempt + 1}/{settings.max_attempts})..."
        )
        time.sleep(delay)
    raise TranscriptionError("The transcription request did not complete.")
def write_combined_outputs(
    output_directory: Path,
    settings: TranscriptionSettings,
    transcript_parts: list[str],
    speaker_lines: list[str],
    turns: list[CombinedTurn],
    chunks: list[ChunkSummary],
    failures: list[ChunkFailure],
) -> None:
    """Validate the complete output structure before replacing combined files."""
    combined = CombinedTranscription(
        source_file=settings.input_audio_file.name,
        model=settings.model,
        mode=settings.mode,
        overlap_seconds=settings.overlap_seconds,
        transcript=" ".join(part.strip() for part in transcript_parts if part.strip()),
        audio_duration_ms=sum(chunk.source_chunk_duration_ms for chunk in chunks),
        processed_audio_duration_ms=sum(
            chunk.audio_duration_ms or 0 for chunk in chunks if chunk.status == "succeeded"
        ),
        complete=not failures,
        turns=turns,
        chunks=chunks,
    )
    save_json(
        output_directory / "combined_transcription.json",
        combined.model_dump(mode="json", by_alias=True, exclude_none=True),
    )
    atomic_write_text(output_directory / "combined_transcript.txt", combined.transcript)
    atomic_write_text(output_directory / "speaker_transcript.txt", "\n".join(speaker_lines))
    save_json(
        output_directory / "failed_chunks.json",
        [failure.model_dump(mode="json") for failure in failures],
    )
def process_recording(
    settings: TranscriptionSettings,
    output_directory: Path,
    ffmpeg_path: str,
    expected_source: tuple[int, int] | None = None,
) -> int:
    """Convert, transcribe/resume, and write outputs while this process owns the lock."""
    source_name = settings.input_audio_file.name
    summaries: list[ChunkSummary] = []
    failures: list[ChunkFailure] = []
    total: int | None = None
    save_run_status(output_directory, source_name, "running")
    try:
        original_stat = settings.input_audio_file.stat()
        if expected_source is not None and expected_source != (
            original_stat.st_size,
            original_stat.st_mtime_ns,
        ):
            raise TranscriptionError(
                "The input recording changed while being identified. Stop editing it and rerun."
            )
        with (
            tempfile.TemporaryDirectory(prefix="muse_chunks_") as temporary,
            requests.Session() as session,
        ):
            chunks = split_audio(settings.input_audio_file, Path(temporary), settings, ffmpeg_path)
            overlap_ms = settings.overlap_seconds * 1000
            for number, chunk in enumerate(chunks):
                upload_duration_ms = wav_duration_ms(chunk.audio_path)
                expected_duration_ms = chunk.source_duration_ms + (
                    overlap_ms if number > 0 else 0
                )
                if abs(upload_duration_ms - expected_duration_ms) > 1:
                    raise TranscriptionError(
                        f"Prepared clip {number + 1} does not match its source timeline and overlap."
                    )
            current_stat = settings.input_audio_file.stat()
            if (original_stat.st_size, original_stat.st_mtime_ns) != (
                current_stat.st_size,
                current_stat.st_mtime_ns,
            ):
                raise TranscriptionError(
                    "The input recording changed during conversion. Stop editing it and rerun."
                )
            total = len(chunks)
            print(f"Prepared {total} audio chunk(s). Output: {output_directory}")
            fallback_transcripts: list[tuple[int, int, str]] = []are you attending Nana’s meeting
            failed_speaker_lines: list[tuple[int, int, str]] = []
            combined_turns: list[CombinedTurn] = []
            previous_chunk_turns: list[CombinedTurn] = []
            previous_top_level_transcript: str | None = None
            stop_reason: str | None = None
            for number, chunk_info in enumerate(chunks):
                chunk = chunk_info.audio_path
                source_offset_ms = chunk_info.source_start_ms
                source_duration = chunk_info.source_duration_ms
                clip_offset_ms = max(0, source_offset_ms - overlap_ms)
                result_path = output_directory / f"chunk_{number:03d}.json"
                try:
                    result = load_cached_response(result_path)
                    if result is not None:
                        print(f"Using saved result for chunk {number + 1}/{total}.")
                    elif stop_reason is not None:
                        raise TranscriptionError(
                            f"Not uploaded because an earlier request failed: {stop_reason}"
                        )
                    else:
                        print(f"Transcribing chunk {number + 1}/{total}...")
                        result = transcribe(chunk, settings, session)
                        # Storage failures propagate and stop further uploads.
                        save_json(result_path, result)
                    parsed = TranscribeResponse.model_validate(result)
                    current_turns = [
                        CombinedTurn(
                            **turn.to_dict(offset_ms=clip_offset_ms),
                            global_turn_index=0,
                            chunk_index=number,
                            session_id=parsed.session_id,
                            speaker_key=f"{parsed.session_id}:{turn.speaker}"
                            if turn.speaker is not None
                            else None,
                        )
                        for turn in parsed.turns
                    ]
                    if current_turns:
                        if previous_chunk_turns and settings.overlap_seconds:
                            # Speaker labels A/B are local to each API response.
                            # Only exact, timestamp-overlapping text matches may
                            # provide evidence for carrying a previous label into
                            # this chunk. Ambiguous mappings remain chunk-local.
                            overlap_matches = overlapping_turn_matches(
                                previous_chunk_turns,
                                current_turns,
                                clip_offset_ms,
                                source_offset_ms,
                            )
                            current_turns = align_speakers_from_overlap(
                                current_turns, overlap_matches
                            )
                            duplicate_turn_ids = {
                                previous.turn_id for previous, _ in overlap_matches
                            }
                            combined_turns = [
                                turn
                                for turn in combined_turns
                                if not (
                                    turn.chunk_index == number - 1
                                    and turn.turn_id in duplicate_turn_ids
                                )
                            ]
                        combined_turns.extend(current_turns)
                        previous_chunk_turns = current_turns
                        previous_top_level_transcript = None
                    else:
                        previous_chunk_turns = []
                        fallback_text = remove_overlapping_transcript_prefix(
                            previous_top_level_transcript or "",
                            parsed.transcript,
                            settings.overlap_seconds,
                        )
                        if fallback_text:
                            fallback_transcripts.append(
                                (source_offset_ms, number, fallback_text)
                            )
                        previous_top_level_transcript = parsed.transcript
                    summaries.append(
                        ChunkSummary(
                            chunk_index=number,
                            session_id=parsed.session_id,
                            audio_duration_ms=parsed.audio_duration_ms,
                            source_chunk_duration_ms=source_duration,
                            timeline_start_ms=source_offset_ms,
                            response_file=result_path.name,
                            status="succeeded",
                        )
                    )
                except TranscriptionError as error:
                    previous_chunk_turns = []
                    previous_top_level_transcript = None
                    if error.stop_remaining:
                        stop_reason = str(error)
                    message = str(error)
                    print(f"Chunk {number + 1}/{total} failed: {message}", file=sys.stderr)
                    failures.append(ChunkFailure(chunk=number, filename=chunk.name, error=message))
                    failure_text = f"[Transcription failed for chunk {number + 1}]"
                    fallback_transcripts.append((source_offset_ms, number, failure_text))
                    failed_speaker_lines.append(
                        (
                            source_offset_ms,
                            number,
                            f"[{format_timestamp(source_offset_ms)} - {format_timestamp(source_offset_ms + source_duration)}] Chunk {number + 1}: [Transcription failed]",
                        )
                    )
                    summaries.append(
                        ChunkSummary(
                            chunk_index=number,
                            source_chunk_duration_ms=source_duration,
                            timeline_start_ms=source_offset_ms,
                            response_file=result_path.name,
                            status="failed",
                        )
                    )
                save_run_status(
                    output_directory,
                    source_name,
                    "running",
                    total=total,
                    succeeded=len(summaries) - len(failures),
                    failed=len(failures),
                )
        combined_turns.sort(
            key=lambda turn: (turn.start_ms, turn.end_ms, turn.chunk_index, turn.turn_id)
        )
        combined_turns = [
            CombinedTurn(
                **{
                    **turn.model_dump(),
                    "global_turn_index": index,
                }
            )
            for index, turn in enumerate(combined_turns)
        ]
        transcript_entries = [
            (turn.start_ms, turn.chunk_index, turn.turn_id, turn.transcript)
            for turn in combined_turns
            if turn.transcript.strip()
        ]
        transcript_entries.extend(
            (start_ms, chunk_index, -1, text)
            for start_ms, chunk_index, text in fallback_transcripts
        )
        transcript_entries.sort(key=lambda entry: (entry[0], entry[1], entry[2]))
        transcript_parts = [entry[3] for entry in transcript_entries]
        speaker_entries = [
            (
                turn.start_ms,
                turn.chunk_index,
                turn.turn_id,
                f"[{format_timestamp(turn.start_ms)} - {format_timestamp(turn.end_ms)}] "
                f"Chunk {turn.chunk_index + 1}, Speaker {turn.speaker or 'Unknown'}: "
                f"{turn.transcript}",
            )
            for turn in combined_turns
        ]
        speaker_entries.extend(
            (start_ms, chunk_index, -1, line)
            for start_ms, chunk_index, line in failed_speaker_lines
        )
        speaker_entries.sort(key=lambda entry: (entry[0], entry[1], entry[2]))
        speaker_lines = [entry[3] for entry in speaker_entries]
        write_combined_outputs(
            output_directory,
            settings,
            transcript_parts,
            speaker_lines,
            combined_turns,
            summaries,
            failures,
        )
        save_run_status(
            output_directory,
            source_name,
            "incomplete" if failures else "complete",
            total=total,
            succeeded=len(summaries) - len(failures),are you attending Nana’s meeting
            failed=len(failures),
        )
        print(f"Transcript: {output_directory / 'combined_transcript.txt'}")
        print(f"Speaker transcript: {output_directory / 'speaker_transcript.txt'}")
        print(f"Structured transcript: {output_directory / 'combined_transcription.json'}")
        if failures:
            print(
                f"Incomplete: {len(failures)}/{total} chunk(s) failed. See failed_chunks.json; rerun to retry.",
                file=sys.stderr,
            )
        return 1 if failures else 0
    except (
        KeyboardInterrupt,
        OSError,
        ValueError,
        TranscriptionError,
        wave.Error,
        EOFError,
    ) as error:
        # An interrupted or failed run must not leave a misleading 'complete' status.
        message = (
            "Interrupted. Rerun to reuse saved responses."
            if isinstance(error, KeyboardInterrupt)
            else validation_message(error)
            if isinstance(error, ValidationError)
            else str(error)
        )
        try:
            save_run_status(
                output_directory,
                source_name,
                "interrupted" if isinstance(error, KeyboardInterrupt) else "failed",
                total=total,
                succeeded=len(summaries) - len(failures),
                failed=len(failures),
                message=message,
            )
        except OSError:
            print(
                "Could not update run_status.json. Treat this run as incomplete.", file=sys.stderr
            )
        raise
def main(argv: list[str] | None = None) -> int:
    """Validate one input, acquire its output lock, and return the documented exit code."""
    parser = argparse.ArgumentParser(
        description="Transcribe one Arabic audio recording with Muse; save resumable UTF-8 outputs."
    )
    parser.add_argument(
        "-a",
        "--audio_file",
        nargs="?",
        type=Path,
        help="One recording; otherwise use FILE_PATH / FILE_NAME in this script.",
    )
    args = parser.parse_args(argv)
    try:
        input_path = (
            (args.audio_file if args.audio_file is not None else FILE_PATH / FILE_NAME)
            .expanduser()
            .resolve()
        )
        settings = build_settings(input_path)
        ffmpeg_path = shutil.which("ffmpeg")
        if ffmpeg_path is None:
            print(
                "FFmpeg was not found on PATH. Install FFmpeg before running this script.",
                file=sys.stderr,
            )
            return 2
    except ValidationError as error:
        print(f"Invalid configuration: {validation_message(error)}", file=sys.stderr)
        return 2
    except (OSError, ValueError, TypeError, RuntimeError) as error:
        print(f"Cannot configure the input: {error}", file=sys.stderr)
        return 2
    try:
        source_stat = settings.input_audio_file.stat()
        source_signature = (source_stat.st_size, source_stat.st_mtime_ns)
        recording_id = processing_id(settings.input_audio_file, settings)
        output_directory = (
            settings.input_audio_file.parent
            / "muse_output"
            / f"{settings.input_audio_file.stem}_{recording_id}"
        )
        output_directory.mkdir(parents=True, exist_ok=True)
        with output_lock(output_directory):
            if completed_run_is_reusable(output_directory, settings):
                print(f"Using validated completed outputs: {output_directory}")
                return 0
            return process_recording(settings, output_directory, ffmpeg_path, source_signature)
    except KeyboardInterrupt:
        print(
            "Interrupted. Saved responses are retained; rerun the same recording/settings to resume.",
            file=sys.stderr,
        )
        return 130
    except ValidationError as error:
        print(f"Validation failed: {validation_message(error)}", file=sys.stderr)
        return 1
    except (OSError, ValueError, TranscriptionError, wave.Error, EOFError) as error:
        print(f"Processing failed: {error}", file=sys.stderr)
        print(
            "Check run_status.json before using combined outputs. Saved responses are retained.",
            file=sys.stderr,
        )
        return 1
if __name__ == "__main__":
    raise SystemExit(main())
