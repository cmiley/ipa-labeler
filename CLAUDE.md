# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

IPA Labeler is a web application for annotating audio files with International Phonetic Alphabet (IPA) symbols. Users can transcribe audio by clicking or typing phonetic symbols, segment audio via waveform timestamps, and precisely align annotations with bidirectional synchronization between visual timeline and segment controls.

## Architecture

### Frontend (Vanilla JavaScript)
- **Waveform Visualization**: Canvas-based waveform rendered using Web Audio API
- **Timestamp System**:
  - Red markers: Free timestamps (user-created by clicking waveform)
  - Green markers: Segment boundaries (from annotations)
  - Orange markers: Highlighted when segment selected
  - All markers draggable for precision adjustment
- **IPA Symbol Palette**: Keyboard mapping with Ctrl+key cycling through related symbols
- **Annotation Editor**: Double-click inline editing for IPA text and semantic labels
- **Timeline View**: Horizontal blocks showing segments with real-time playback highlighting
- **Slider Controls**: Fine-tuned start/end time adjustment with overlap prevention
- **Mute Toggle**: Silent editing mode for focused work

### Backend (Flask)
- Audio file upload and storage (uploads/ directory)
- Annotation persistence (annotations.json)
- Export endpoints: JSON, TXT, ZIP (audio + both formats)
- Auto-loads harvard.wav for testing

### Data Model
```javascript
{
  "filename.wav": [
    {
      text: "ˈhɑːrvərd",           // IPA transcription
      semanticLabel: "Harvard",     // Optional English word(s)
      startTime: 0.5,              // Seconds
      endTime: 1.2                 // Seconds
    }
  ]
}
```

### IPA Keyboard Mapping
- Ctrl+A cycles: æ → ɑ → ʌ → ɐ
- Ctrl+D cycles: d → ð (voiced th)
- Ctrl+T cycles: t → θ → tʃ (voiceless th, ch)
- Ctrl+E cycles: ə → ɚ → ɛ → ɜ → ɝ (schwas and variants)
- Full mapping in static/ipa_symbols.json

## Key Workflows

### Pre-Segmentation Workflow
1. Load audio file (or use auto-loaded harvard.wav)
2. Click waveform to create timestamp markers (red)
3. Click "Create Segments" to generate annotation slots between timestamps
4. Fill in IPA transcriptions and optional semantic labels

### Manual Segmentation Workflow
1. Play audio and pause at desired segment start
2. Type IPA symbols using Ctrl+key shortcuts or click palette
3. Click "Add Segment" (creates 1-second segment at current playback position)
4. Adjust timing via sliders or drag waveform markers

### Editing Workflow
1. Click segment to highlight its waveform timestamps (orange)
2. Double-click IPA text or semantic label to edit inline
3. Drag green waveform markers to adjust boundaries
4. Use sliders for fine-tuned timestamp control
5. All changes sync bidirectionally (waveform ↔ sliders ↔ timeline)

### Playback Workflow
- Click segment or timeline block to play from start (auto-stops at end)
- Enable "Mute Audio" checkbox for silent editing
- Active segments highlight in green during playback

## Development Commands

```bash
# Install dependencies
uv sync

# Run development server
uv run python app.py

# Run tests
uv run pytest

# Format code
uv run ruff format

# Lint
uv run ruff check

# Type check
uv run pyright
```

## Code Style

- No comments unless logic is genuinely non-obvious
- Minimal abstractions; prefer explicit code
- Direct DOM manipulation or lightweight framework (not heavy frameworks)
- Pure functions where possible
- Short variable names in small scopes
