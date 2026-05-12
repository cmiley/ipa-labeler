# IPA Labeler

A web application for annotating audio files with International Phonetic Alphabet (IPA) symbols. Features waveform visualization, precision timestamp control, and keyboard-driven IPA input.

![IPA Labeler Interface](docs/screenshot.png)

## Quick Start

### Installation

```bash
# Install dependencies
uv sync

# Run the application
uv run python app.py
```

Navigate to http://localhost:5000 in your browser.

### First Steps

1. The app auto-loads `harvard.wav` for testing
2. Click the waveform to create timestamp markers
3. Click "Create Segments" to generate annotation slots
4. Use Ctrl+key shortcuts to type IPA symbols (see palette)
5. Click "Save Annotations" to persist your work

## User Guide

### Creating Segments

**Method 1: Pre-Segmentation (Recommended)**
1. Click on the waveform where you want segment boundaries
   - Red vertical lines appear at each click
   - Click "Clear Timestamps" to start over
2. Click "Create Segments" button
   - Generates annotation slots between all timestamps
   - Each segment is ready for transcription

**Method 2: Manual Addition**
1. Play audio and pause where you want a segment
2. Type your IPA transcription in the input field
3. Click "Add Segment" (creates 1-second segment at current position)

### IPA Symbol Input

**Keyboard Shortcuts** (Press Ctrl+key repeatedly to cycle)
- **Ctrl+A**: æ → ɑ → ʌ → ɐ (TRAP, LOT, STRUT vowels)
- **Ctrl+D**: d → ð (voiced th)
- **Ctrl+E**: ə → ɚ → ɛ → ɜ → ɝ (schwas and variants)
- **Ctrl+I**: ɪ → i (KIT, FLEECE)
- **Ctrl+J**: dʒ → ʒ (JUDGE, MEASURE)
- **Ctrl+N**: n → ŋ (sing)
- **Ctrl+O**: ɔ → ɒ → oʊ (THOUGHT, LOT, GOAT)
- **Ctrl+S**: s → ʃ (SIP, SHIP)
- **Ctrl+T**: t → θ → tʃ (voiceless th, CHURCH)
- **Ctrl+U**: ʊ → u (FOOT, GOOSE)
- **Ctrl+'**: ˈ → ˌ (primary and secondary stress)
- **Ctrl+:**: ː (length mark)

**Click to Insert**
- Click any symbol in the palette below the input field
- Works in any focused text input (transcription or semantic label)

### Editing Segments

**Edit Text**
- Double-click the IPA transcription to edit inline
- Double-click the semantic label (gray italics) to add/edit English word

**Adjust Timing**
1. **Sliders**: Drag Start/End sliders for precise control
2. **Waveform Markers**:
   - Click a segment to highlight its timestamps (orange)
   - Drag green markers on waveform to adjust boundaries
   - Changes sync automatically with sliders

**Visual Marker Guide**
- 🔴 **Red markers**: Free timestamps (not yet assigned to segments)
- 🟢 **Green markers**: Segment boundaries (start/end times)
- 🟠 **Orange markers**: Selected segment's timestamps

**Delete Segments**
- Click the red "Delete" button on any segment

### Playback Controls

**Play Segments**
- Click a segment or timeline block to play it
- Audio auto-stops at segment end
- Currently playing segment highlights in green

**Mute Toggle**
- Check "Mute Audio" for silent editing
- Useful when focusing on waveform visualization

### Saving and Exporting

**Save Annotations**
- Click "Save Annotations" to persist to `annotations.json`
- Auto-saves per audio file

**Export Options**
1. **Export JSON**: Structured data with timestamps
2. **Export TXT**: Human-readable format with times
3. **Export ZIP**: Audio file + both annotation formats

Example TXT output:
```
0.00s - 0.50s: ðə (the)
0.50s - 1.20s: ˈhɑːrvərd (Harvard)
```

## Technical Documentation

### Architecture

**Frontend** (`static/app.js`)
- Vanilla JavaScript with Web Audio API for waveform rendering
- Canvas-based visualization with draggable timestamp markers
- Bidirectional synchronization between UI components
- No frameworks or build tools required

**Backend** (`app.py`)
- Flask server with file upload and annotation storage
- RESTful endpoints for annotations and export
- Simple JSON persistence for annotations

### Key Technical Features

#### Waveform Rendering
```javascript
// Uses Web Audio API to decode audio buffer
const audioContext = new AudioContext();
audioBuffer = await audioContext.decodeAudioData(arrayBuffer);

// Downsamples to canvas width for efficient rendering
const step = Math.ceil(data.length / canvas.width);
for (let i = 0; i < canvas.width; i++) {
    // Find min/max in this bucket for accurate waveform
    let min = 1.0, max = -1.0;
    for (let j = 0; j < step; j++) {
        const datum = data[(i * step) + j];
        if (datum < min) min = datum;
        if (datum > max) max = datum;
    }
    // Draw vertical line from min to max
    ctx.moveTo(i, (1 + min) * amp);
    ctx.lineTo(i, (1 + max) * amp);
}
```

#### Timestamp Dragging
```javascript
// Each marker has drag handler with overlap prevention
function makeDraggable(marker, onDrag) {
    marker.addEventListener('mousedown', (e) => {
        isDragging = true;
    });

    document.addEventListener('mousemove', (e) => {
        if (!isDragging) return;
        const percent = x / rect.width;
        const newTime = percent * duration;
        onDrag(newTime);  // Updates annotation
    });
}
```

#### Overlap Prevention
```javascript
// Prevents segments from overlapping during adjustment
function checkOverlap(idx, field, value) {
    const newStart = field === 'startTime' ? value : segment.startTime;
    const newEnd = field === 'endTime' ? value : segment.endTime;

    // Check against all other segments
    for (let i = 0; i < annotations.length; i++) {
        if (i === idx) continue;
        const other = annotations[i];
        if (/* intervals overlap */) return false;
    }
    return true;
}
```

#### Bidirectional Sync
- Slider changes → Update annotation → Re-render waveform markers + timeline
- Waveform drag → Update annotation → Re-render sliders + timeline
- All updates go through single source of truth (`annotations` array)

### File Structure

```
IPA_labeler/
├── app.py                    # Flask backend
├── templates/
│   └── index.html           # Single-page app HTML
├── static/
│   ├── app.js               # Core application logic
│   ├── style.css            # UI styling
│   └── ipa_symbols.json     # Keyboard mapping configuration
├── uploads/                 # Audio file storage
├── annotations.json         # Persisted annotations
├── pyproject.toml          # Python dependencies
├── CLAUDE.md               # Developer guide
└── README.md               # This file
```

### API Endpoints

**POST /upload**
- Upload audio file
- Returns: `{ filename: string }`

**GET /audio/:filename**
- Serve audio file for playback

**GET /annotations/:filename**
- Retrieve annotations for file
- Returns: Array of annotation objects

**POST /annotations/:filename**
- Save annotations for file
- Body: Array of annotation objects

**GET /export/:filename/:format**
- Export annotations as json or txt
- Returns: File download

**GET /export/:filename/zip**
- Export audio + annotations bundle
- Returns: ZIP file download

### Customization

**Add IPA Symbols**
Edit `static/ipa_symbols.json`:
```json
{
  "keyboard_map": {
    "x": ["newSymbol1", "newSymbol2"]
  }
}
```

**Styling**
All styles in `static/style.css`. Key classes:
- `.timestamp-free`: Red free markers
- `.timestamp-segment`: Green segment markers
- `.timestamp-segment.highlighted`: Orange selected markers
- `.annotation-segment.active`: Playing segment highlight

### Browser Compatibility

- Chrome/Edge: Full support
- Firefox: Full support
- Safari: Full support (requires user gesture for audio)
- Mobile: Limited (drag interactions require mouse)

## Development

### Running Tests
```bash
uv run pytest
```

### Code Style
```bash
# Format
uv run ruff format

# Lint
uv run ruff check
```

### Development Tips

1. **Debugging**: Open browser DevTools console for errors
2. **Audio Issues**: Check browser audio permissions
3. **Performance**: Large audio files may slow waveform rendering
4. **Data**: `annotations.json` stores all work (backup regularly)

## License

MIT

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

## Support

For issues or questions:
- Open an issue on GitHub
- Check browser console for error messages
- Ensure audio file is in supported format (WAV, MP3, OGG)