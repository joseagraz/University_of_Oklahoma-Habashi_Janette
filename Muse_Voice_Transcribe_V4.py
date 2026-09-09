"""
Program: Muse Voice Transcription
File: Muse_Voice_Transcribe.py
Version: 1.2.0
Author: Jose L. Agraz, PhD
Date: 2026-09-09

Description:
    Transcribes an audio recording using the Muse Voice Transcribe API.
    Recordings longer than the API's 10-minute limit are converted into
    nine-minute WAV segments and submitted individually. The program saves
    each schema-validated API response and assembles the completed segments
    into combined text and application-specific JSON outputs. Cached results
    are isolated by both recording content and transcription configuration.

Requirements:
    - Python 3.10 or newer
    - requests
    - FFmpeg
    - Muse API key

Python package installation:
    conda install requests

FFmpeg installation:
    conda install -c conda-forge ffmpeg

Authentication:
    Insert the Muse API key in the MODEL_API_KEY configuration variable.

Usage:
    Insert MODEL_API_KEY in the configuration section. Either set FILE_NAME and
    FILE_PATH and run:

        python Muse_Voice_Transcribe.py

    Or provide an audio file on the command line:

        python Muse_Voice_Transcribe.py /path/to/recording.mp3

Example:
    FILE_NAME = "recording.wav"
    FILE_PATH = Path("/path/to/audio")

Supported input:
    Any audio format that the installed FFmpeg version can read.

Output:
    Creates a muse_output directory beside the input recording. The
    recording-specific subdirectory contains:

    - One JSON response for each successfully transcribed segment
    - A combined plain-text transcript
    - A timestamped, speaker-labeled transcript when turns are available
    - A combined structured JSON transcription
    - A failure report, which is an empty array when all segments succeeded

Processing:
    1. Validate Python, FFmpeg, the input file, and API credentials.
    2. Convert the recording to mono, 16-kHz PCM WAV audio.
    3. Divide the recording into nine-minute segments.
    4. Submit each segment to Muse Voice Transcribe.
    5. Retry temporary API or network failures.
    6. Save each successful response immediately.
    7. Combine the transcription segments in chronological order.

Notes:
    - The API key is stored directly in this script as requested.
    - Do not commit, publish, or share this file while it contains the key.
    - Speaker labels are scoped to one chunk/session and are not global
      identities across the complete recording.
    - HTTP 400-level errors normally require correcting the request.
    - HTTP 429 and selected 500-level errors are retried automatically.
    - Segment boundaries may occasionally divide a sentence.

Exit codes:
    0 - Processing completed successfully
    1 - Validation, transcription, or processing failure
"""
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import time
import wave
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any

import requests

FILE_NAME = "July_13_2022_SalwaJefna.mp3"
FILE_PATH = Path("/home/jagraz/Downloads/Habashi/Precondition_Audio")
INPUT_AUDIO_FILE = FILE_PATH / FILE_NAME
API_URL = "https://api.meta.ai/v1/asr/transcribe"
# Paste your own key between the quotation marks. Do not share this file.
MODEL_API_KEY="LLM_1059297227105699_VPf68TbQqH91hSCBr9HfpH5NBMo" 
MODEL = "muse-voice-transcribe-1.0"
TRANSCRIPTION_MODE = "DIARIZATION"
KEYWORDS: list[str] = []
LANGUAGE_BIAS: list[str] = []
CHUNK_SECONDS = 540  # 9 minutes
MAX_ATTEMPTS = 4
RETRYABLE_CODES = {429, 500, 502, 503, 504}
VALID_TRANSCRIPTION_MODES = {"PUSH_TO_TALK", "ENDPOINTING", "DIARIZATION"}
COMBINED_SCHEMA_NAME = "MuseCombinedTranscription"
COMBINED_SCHEMA_VERSION = "1.0"


@dataclass(frozen=True)
class Turn:
    """One speech turn from a buffered Muse transcription response."""

    turn_id: int
    start_ms: int
    end_ms: int
    transcript: str
    speaker: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Turn":
        """Validate and convert a Muse Turn object."""
        required = {
            "turnId": int,
            "startMs": int,
            "endMs": int,
            "transcript": str,
        }

        for field, expected_type in required.items():
            value = data.get(field)
            if (
                not isinstance(value, expected_type)
                or (expected_type is int and isinstance(value, bool))
            ):
                raise ValueError(
                    f"Invalid Muse Turn: {field!r} must be "
                    f"{expected_type.__name__}."
                )

        if data["turnId"] < 0:
            raise ValueError("Invalid Muse Turn: 'turnId' cannot be negative.")
        if data["startMs"] < 0 or data["endMs"] < data["startMs"]:
            raise ValueError(
                "Invalid Muse Turn: timestamps must satisfy "
                "0 <= startMs <= endMs."
            )

        speaker = data.get("speaker")
        if speaker is not None and not isinstance(speaker, str):
            raise ValueError("Invalid Muse Turn: 'speaker' must be a string.")

        return cls(
            turn_id=data["turnId"],
            start_ms=data["startMs"],
            end_ms=data["endMs"],
            transcript=data["transcript"],
            speaker=speaker,
        )

    def to_dict(self, offset_ms: int = 0) -> dict[str, Any]:
        """Return a JSON-ready turn, optionally shifted on the full timeline."""
        result = {
            "turnId": self.turn_id,
            "startMs": self.start_ms + offset_ms,
            "endMs": self.end_ms + offset_ms,
            "transcript": self.transcript,
        }
        if self.speaker is not None:
            result["speaker"] = self.speaker
        return result


@dataclass(frozen=True)
class TranscribeResponse:
    """The documented buffered application/json response from Muse."""

    session_id: str
    transcript: str
    audio_duration_ms: int
    turns: list[Turn]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TranscribeResponse":
        """Validate and convert a Muse TranscribeResponse object."""
        if not isinstance(data, dict):
            raise ValueError("The Muse response must be a JSON object.")

        required = {
            "sessionId": str,
            "transcript": str,
            "audioDurationMs": int,
            "turns": list,
        }

        for field, expected_type in required.items():
            value = data.get(field)
            if (
                not isinstance(value, expected_type)
                or (expected_type is int and isinstance(value, bool))
            ):
                raise ValueError(
                    f"Invalid Muse TranscribeResponse: {field!r} must be "
                    f"{expected_type.__name__}."
                )

        if data["audioDurationMs"] < 0:
            raise ValueError("'audioDurationMs' cannot be negative.")

        turns = []
        for turn_data in data["turns"]:
            if not isinstance(turn_data, dict):
                raise ValueError("Each item in 'turns' must be a JSON object.")
            turns.append(Turn.from_dict(turn_data))

        turn_ids = [turn.turn_id for turn in turns]
        if turn_ids != sorted(turn_ids):
            raise ValueError("Muse turns are not in ascending turnId order.")

        return cls(
            session_id=data["sessionId"],
            transcript=data["transcript"],
            audio_duration_ms=data["audioDurationMs"],
            turns=turns,
        )


def build_transcribe_request() -> dict[str, Any]:
    """Build the documented buffered TranscribeRequest object."""
    if not isinstance(MODEL, str) or not MODEL.strip():
        raise ValueError("MODEL must be a non-empty string.")

    if (
        not isinstance(TRANSCRIPTION_MODE, str)
        or TRANSCRIPTION_MODE not in VALID_TRANSCRIPTION_MODES
    ):
        raise ValueError(
            f"TRANSCRIPTION_MODE must be one of "
            f"{sorted(VALID_TRANSCRIPTION_MODES)}."
        )

    if (
        not isinstance(CHUNK_SECONDS, int)
        or isinstance(CHUNK_SECONDS, bool)
        or not 0 < CHUNK_SECONDS < 600
    ):
        raise ValueError("CHUNK_SECONDS must be an integer from 1 through 599.")

    if not isinstance(KEYWORDS, list) or not all(
        isinstance(keyword, str) and keyword.strip() for keyword in KEYWORDS
    ):
        raise ValueError("KEYWORDS must be a list of non-empty strings.")

    if not isinstance(LANGUAGE_BIAS, list) or not all(
        isinstance(language, str) and language.strip()
        for language in LANGUAGE_BIAS
    ):
        raise ValueError(
            "LANGUAGE_BIAS must be a list of non-empty language-name strings."
        )

    request_data: dict[str, Any] = {
        "model": MODEL,
        "audioEncoding": "WAV",
        "mode": TRANSCRIPTION_MODE,
    }

    if KEYWORDS:
        request_data["keywords"] = KEYWORDS
    if LANGUAGE_BIAS:
        request_data["languageBias"] = LANGUAGE_BIAS

    # partialMode and emitAudioProgress apply only to event-stream responses.
    return request_data


def save_json(path, data):
    """Save JSON without risking a partially written result."""
    temporary_path = path.with_suffix(".tmp")

    with temporary_path.open("w", encoding="utf-8") as file:
        json.dump(data, file, indent=2, ensure_ascii=False)

    temporary_path.replace(path)


def file_hash(path):
    """Return a SHA-256 hash of a file."""
    digest = hashlib.sha256()

    with path.open("rb") as file:
        while block := file.read(1024 * 1024):
            digest.update(block)

    return digest.hexdigest()


def processing_id(input_path):
    """Identify both the recording and settings used to create cached results."""
    cache_settings = {
        "model": MODEL,
        "mode": TRANSCRIPTION_MODE,
        "keywords": KEYWORDS,
        "languageBias": LANGUAGE_BIAS,
        "chunkSeconds": CHUNK_SECONDS,
        "audioEncoding": "WAV",
        "sampleRateHz": 16000,
        "channels": 1,
    }
    digest = hashlib.sha256()
    digest.update(file_hash(input_path).encode("ascii"))
    digest.update(
        json.dumps(cache_settings, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
    )
    return digest.hexdigest()[:12]


def wav_duration_ms(path):
    """Measure an output WAV chunk precisely from its frame count."""
    with wave.open(str(path), "rb") as audio:
        frame_rate = audio.getframerate()
        if frame_rate <= 0:
            raise ValueError(f"Invalid WAV frame rate in {path.name}.")
        return round(audio.getnframes() * 1000 / frame_rate)


def format_timestamp(milliseconds):
    """Format milliseconds as HH:MM:SS.mmm."""
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, milliseconds = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{milliseconds:03d}"


def load_cached_response(path):
    """Return a valid cached Muse response, or None when it must be replaced."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        TranscribeResponse.from_dict(payload)
        return payload
    except (OSError, json.JSONDecodeError, ValueError) as error:
        print(f"Ignoring invalid cached response {path.name}: {error}")
        return None


def split_audio(input_path, chunk_directory):
    """Convert and split the recording into nine-minute WAV files."""
    command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
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
        str(CHUNK_SECONDS),
        "-reset_timestamps",
        "1",
        str(chunk_directory / "chunk_%03d.wav"),
    ]

    subprocess.run(command, check=True)

    chunks = sorted(chunk_directory.glob("chunk_*.wav"))

    if not chunks:
        raise RuntimeError("FFmpeg did not create any audio chunks.")

    return chunks


def retry_delay(response, attempt):
    """Honor numeric or HTTP-date Retry-After values when provided."""
    retry_after = response.headers.get("Retry-After", "")

    try:
        return max(float(retry_after), 1)
    except ValueError:
        pass

    try:
        retry_time = parsedate_to_datetime(retry_after)
        if retry_time.tzinfo is None:
            retry_time = retry_time.replace(tzinfo=timezone.utc)
        seconds = (retry_time - datetime.now(timezone.utc)).total_seconds()
        return max(seconds, 1)
    except (TypeError, ValueError, OverflowError):
        return 2 ** (attempt - 1)


def transcribe(audio_path, api_key):
    """Transcribe one audio chunk and retry temporary failures."""
    settings = build_transcribe_request()

    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            with audio_path.open("rb") as audio:
                response = requests.post(
                    API_URL,
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Accept": "application/json",
                    },
                    files={
                        "request": (
                            None,
                            json.dumps(settings),
                            "application/json",
                        ),
                        "audio": (
                            audio_path.name,
                            audio,
                            "audio/wav",
                        ),
                    },
                    timeout=(30, 900),
                )

            if response.ok:
                try:
                    payload = response.json()
                except ValueError as error:
                    raise RuntimeError(
                        f"The API returned invalid JSON: {response.text[:1000]}"
                    ) from error

                TranscribeResponse.from_dict(payload)
                return payload

            message = f"HTTP {response.status_code}: {response.text[:2000]}"

            if (
                response.status_code not in RETRYABLE_CODES
                or attempt == MAX_ATTEMPTS
            ):
                raise RuntimeError(message)

            delay = retry_delay(response, attempt)

        except requests.RequestException as error:
            if attempt == MAX_ATTEMPTS:
                raise RuntimeError(f"Network error: {error}") from error

            delay = 2 ** (attempt - 1)

        print(f"Request failed. Retrying in {delay:g} seconds...")
        time.sleep(delay)

    raise RuntimeError("The transcription request failed.")


def main():
    if sys.version_info < (3, 10):
        print("Python 3.10 or newer is required.")
        return 1

    if len(sys.argv) > 2:
        print(f"Usage: python {Path(sys.argv[0]).name} [AUDIO_FILE]")
        return 1

    input_audio_file = (
        Path(sys.argv[1]).expanduser().resolve()
        if len(sys.argv) == 2
        else INPUT_AUDIO_FILE
    )

    if not input_audio_file.is_file():
        print(f"Audio file not found: {input_audio_file}")
        return 1

    if not MODEL_API_KEY.strip() or MODEL_API_KEY == "PASTE_YOUR_API_KEY_HERE":
        print("Insert your Muse API key in MODEL_API_KEY.")
        return 1

    if shutil.which("ffmpeg") is None:
        print("FFmpeg is not installed or is not available in PATH.")
        return 1

    try:
        build_transcribe_request()
    except ValueError as error:
        print(f"Invalid transcription configuration: {error}")
        return 1

    recording_id = processing_id(input_audio_file)
    output_directory = (
        input_audio_file.parent
        / "muse_output"
        / f"{input_audio_file.stem}_{recording_id}"
    )
    output_directory.mkdir(parents=True, exist_ok=True)

    failures = []
    transcript_parts = []
    combined_turns = []
    speaker_transcript_lines = []
    processed_audio_duration_ms = 0
    chunk_summaries = []

    with tempfile.TemporaryDirectory(prefix="muse_chunks_") as temporary:
        try:
            chunks = split_audio(input_audio_file, Path(temporary))
            chunk_durations_ms = [wav_duration_ms(chunk) for chunk in chunks]
        except (
            OSError,
            subprocess.CalledProcessError,
            ValueError,
            wave.Error,
        ) as error:
            print(f"Audio preparation failed: {error}")
            return 1

        total_audio_duration_ms = sum(chunk_durations_ms)
        print(f"Created {len(chunks)} audio chunk(s).")

        chunk_offset_ms = 0
        for number, chunk in enumerate(chunks):
            result_path = output_directory / f"chunk_{number:03d}.json"
            chunk_duration_ms = chunk_durations_ms[number]

            try:
                if result_path.exists():
                    result = load_cached_response(result_path)
                else:
                    result = None

                if result is not None:
                    print(f"Using saved result for chunk {number + 1}.")
                else:
                    print(
                        f"Transcribing chunk {number + 1} of {len(chunks)}..."
                    )
                    result = transcribe(chunk, MODEL_API_KEY)
                    save_json(result_path, result)

                parsed_result = TranscribeResponse.from_dict(result)
                transcript_parts.append(parsed_result.transcript)
                processed_audio_duration_ms += parsed_result.audio_duration_ms

                for turn in parsed_result.turns:
                    combined_turn = turn.to_dict(offset_ms=chunk_offset_ms)
                    combined_turn["globalTurnIndex"] = len(combined_turns)
                    combined_turn["chunkIndex"] = number
                    combined_turn["sessionId"] = parsed_result.session_id
                    if turn.speaker is not None:
                        combined_turn["speakerKey"] = (
                            f"{parsed_result.session_id}:{turn.speaker}"
                        )
                    combined_turns.append(combined_turn)

                    speaker_label = turn.speaker or "Unknown"
                    start = format_timestamp(turn.start_ms + chunk_offset_ms)
                    end = format_timestamp(turn.end_ms + chunk_offset_ms)
                    speaker_transcript_lines.append(
                        f"[{start} - {end}] Chunk {number + 1}, "
                        f"Speaker {speaker_label}: {turn.transcript}"
                    )

                chunk_summaries.append(
                    {
                        "chunkIndex": number,
                        "sessionId": parsed_result.session_id,
                        "audioDurationMs": parsed_result.audio_duration_ms,
                        "sourceChunkDurationMs": chunk_duration_ms,
                        "timelineStartMs": chunk_offset_ms,
                        "responseFile": result_path.name,
                        "status": "succeeded",
                    }
                )

            except (OSError, RuntimeError, ValueError) as error:
                print(f"Chunk {number + 1} failed: {error}")

                failures.append(
                    {
                        "chunk": number,
                        "filename": chunk.name,
                        "error": str(error),
                    }
                )

                transcript_parts.append(
                    f"[Transcription failed for chunk {number + 1}]"
                )

                failure_start = format_timestamp(chunk_offset_ms)
                failure_end = format_timestamp(
                    chunk_offset_ms + chunk_duration_ms
                )
                speaker_transcript_lines.append(
                    f"[{failure_start} - {failure_end}] Chunk {number + 1}: "
                    "[Transcription failed]"
                )

                chunk_summaries.append(
                    {
                        "chunkIndex": number,
                        "sourceChunkDurationMs": chunk_duration_ms,
                        "timelineStartMs": chunk_offset_ms,
                        "responseFile": result_path.name,
                        "status": "failed",
                    }
                )

            chunk_offset_ms += chunk_duration_ms

    transcript_path = output_directory / "combined_transcript.txt"
    transcript_path.write_text(
        "\n\n".join(transcript_parts),
        encoding="utf-8",
    )

    speaker_transcript_path = output_directory / "speaker_transcript.txt"
    speaker_transcript_path.write_text(
        "\n".join(speaker_transcript_lines),
        encoding="utf-8",
    )

    combined_result_path = output_directory / "combined_transcription.json"
    save_json(
        combined_result_path,
        {
            "schema": {
                "name": COMBINED_SCHEMA_NAME,
                "version": COMBINED_SCHEMA_VERSION,
            },
            "sourceFile": input_audio_file.name,
            "model": MODEL,
            "audioEncoding": "WAV",
            "mode": TRANSCRIPTION_MODE,
            "transcript": "\n\n".join(transcript_parts),
            "audioDurationMs": total_audio_duration_ms,
            "processedAudioDurationMs": processed_audio_duration_ms,
            "complete": not failures,
            "speakerScope": (
                "Speaker labels are local to each chunk/session; speakerKey "
                "does not identify a person across sessions."
            ),
            "turns": combined_turns,
            "chunks": chunk_summaries,
        },
    )

    failure_path = output_directory / "failed_chunks.json"
    save_json(failure_path, failures)
    if failures:
        print(f"Some chunks failed. Details: {failure_path}")

    print(f"Transcript: {transcript_path}")
    print(f"Speaker transcript: {speaker_transcript_path}")
    print(f"Structured transcription: {combined_result_path}")
    print(f"Raw results: {output_directory}")

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
