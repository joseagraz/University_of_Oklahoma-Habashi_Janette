# Muse Voice Transcription

## Program information

| Item | Value |
| --- | --- |
| Program | Muse Voice Transcription |
| Script | `Muse_Voice_Transcribe.py` |
| Version | 1.2.0 |
| Author | Jose L. Agraz, PhD |

## Description

This command-line program transcribes an audio recording with Meta's Muse Voice Transcribe API. It uses FFmpeg to convert the source recording to mono, 16 kHz, 16-bit PCM WAV and divide it into nine-minute chunks. Each chunk is submitted separately, validated, and saved. The program then creates plain-text, speaker-labeled, and structured JSON outputs.

The nine-minute chunk size is an implementation choice in this script, based on its stated assumption that API requests must remain under ten minutes. Confirm current limits, model availability, request fields, and data-handling requirements in the official Muse documentation before production use.

## Key limitation: speaker identity

Every audio chunk is sent as a separate Muse session. Speaker labels are therefore local to a chunk and cannot be assumed to identify the same person in another chunk. For example, `Speaker 0` in chunk 1 may not be the same person as `Speaker 0` in chunk 2.

The combined JSON preserves `sessionId`, `chunkIndex`, and `speakerKey` so local labels are not mistaken for recording-wide identities. The script does not perform cross-chunk speaker matching.

## Requirements

- Python 3.10 or newer
- [requests](https://requests.readthedocs.io/) Python package
- [FFmpeg](https://ffmpeg.org/) available on `PATH`
- A valid [Muse API key](https://dev.meta.ai/?project_id=1867221984267473&team_id=2237112550356004)
- Network access to the configured Muse endpoint
- Read permission for the recording and write permission for its parent directory

Install the dependencies with Conda:

```bash
conda install -c conda-forge ffmpeg requests
```

## Configuration

Edit the constants near the beginning of the script:

| Setting | Purpose |
| --- | --- |
| `FILE_NAME` | Default recording filename |
| `FILE_PATH` | Default recording directory |
| `MODEL_API_KEY` | Muse bearer credential |
| `MODEL` | Muse model identifier |
| `TRANSCRIPTION_MODE` | `DIARIZATION`, `ENDPOINTING`, or `PUSH_TO_TALK` |
| `KEYWORDS` | Optional list of terms used to bias recognition |
| `LANGUAGE_BIAS` | Optional list of language names used to bias recognition |
| `CHUNK_SECONDS` | Chunk length; must be an integer from 1 through 599 |
| `MAX_ATTEMPTS` | Maximum attempts for each API request |

The current script uses `DIARIZATION` (best for interviews) mode and a chunk duration of 540 seconds.

### API-key security

The uploaded script stores its API key directly in `MODEL_API_KEY`. The credential is intentionally not reproduced in this documentation. Do not commit or distribute the script while it contains an active key. If the uploaded credential is real or has been shared, rotate it and update the private working copy.

## Usage

### Use the configured recording

Set `FILE_NAME`, `FILE_PATH`, and `MODEL_API_KEY`, then run:

```bash
python Muse_Voice_Transcribe.py
```

## Processing workflow

1. Validate input file, API key, FFmpeg installation, and request settings.
2. Generate a processing ID from the recording content and transcript-related settings.
3. Convert and split the source audio into temporary WAV chunks.
4. Reuse an existing chunk response only if its JSON passes schema validation.
5. Submit uncached chunks to Muse and retry temporary failures.
6. Save each successful response immediately.
7. Offset speech-turn timestamps onto the complete recording timeline.
8. Write combined transcripts, structured JSON, and a failure report.
9. Delete the temporary WAV chunks automatically.

## Outputs

Results are written beside the source recording:

```text
muse_output/<recording_name>_<processing_id>/
```

| File | Contents |
| --- | --- |
| `chunk_NNN.json` | Validated raw Muse response for a successful chunk |
| `combined_transcript.txt` | Combined transcript in chunk order |
| `speaker_transcript.txt` | Timestamped speech turns with chunk and speaker labels |
| `combined_transcription.json` | Combined transcript, turns, durations, sessions, and chunk status |
| `failed_chunks.json` | Failed chunk records; `[]` means all chunks succeeded |

A failed chunk is represented by a visible marker in both text outputs. Later chunks continue processing.

## Expected Muse response

The script expects each successful response to have this general structure:

```json
{
  "sessionId": "string",
  "transcript": "string",
  "audioDurationMs": 12345,
  "turns": [
    {
      "turnId": 0,
      "startMs": 0,
      "endMs": 2500,
      "transcript": "Example speech",
      "speaker": "optional string"
    }
  ]
}
```

The program verifies field types, nonnegative IDs and timestamps, `startMs <= endMs`, and ascending `turnId` order. An invalid response is treated as a failed chunk.

## Combined JSON

`combined_transcription.json` identifies itself as `MuseCombinedTranscription`, schema version `1.0`. Important fields include:

| Field | Meaning |
| --- | --- |
| `transcript` | Combined text from all chunks, including failure markers |
| `audioDurationMs` | Total duration calculated from the generated WAV chunks |
| `processedAudioDurationMs` | Sum of durations reported by successful Muse responses |
| `complete` | `true` only when every chunk succeeded |
| `turns` | Valid turns placed on the full recording timeline |
| `chunks` | Status and timing information for every chunk |
| `speakerScope` | Reminder that speaker labels are local to a session |

Each combined turn also contains `globalTurnIndex`, `chunkIndex`, `sessionId`, and, when a speaker label exists, `speakerKey`.

## Caching and resuming

The output directory's 12-character processing ID is derived from:

- The complete source-file content
- Model and transcription mode
- Keywords and language bias
- Chunk duration
- Audio encoding, sample rate, and channel count

Rerunning the same recording with the same transcript-related settings reuses valid `chunk_NNN.json` files. Missing, malformed, or schema-invalid responses are requested again. Changing a setting included in the processing ID creates a separate output directory.

## Retry and error behavior

- Network exceptions and HTTP 429, 500, 502, 503, and 504 responses are retried.
- A valid numeric or HTTP-date `Retry-After` header is honored.
- Otherwise, the program uses exponential backoff.
- Nonretryable HTTP errors fail immediately for that chunk.
- The request uses a 30-second connection timeout and a 900-second response timeout.
- Any failed chunk causes a final exit code of 1, even though the program writes the available partial results.

## Exit codes

| Code | Meaning |
| --- | --- |
| `0` | Every chunk was transcribed successfully |
| `1` | Validation or audio preparation failed, or at least one chunk failed |

## Troubleshooting

### Audio file not found

Verify `FILE_PATH` and `FILE_NAME`, or supply an existing file as the command-line argument.

### FFmpeg is unavailable

Install FFmpeg and confirm that `ffmpeg -version` works in the same environment used to run the script.

### Audio preparation failed

Confirm that the source contains an audio stream and that FFmpeg can read its format. The script selects the first audio stream.

### HTTP 401 or 403

Confirm that the key is active and authorized for the configured endpoint and model. These errors are not retried.

### HTTP 400

Review the API response printed by the script and verify the model, mode, optional request fields, and current Muse schema.

### Speaker labels change between chunks

This is expected because each chunk creates a separate Muse session. Use `sessionId`, `chunkIndex`, and `speakerKey` to interpret a label within its proper scope.

## Known limitations

- Chunk boundaries can split a sentence or speech turn.
- The script does not overlap chunks or reconcile boundary text.
- It does not match speaker identities between chunks.
- It does not translate, summarize, redact, or identify speakers by name.
- Partial results may contain gaps when a chunk fails.
- Output files may contain sensitive speech and are not encrypted by the script.
- The API interface and limits can change independently of this program.



