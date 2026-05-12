let ipaData = null;
let keyIndexMap = {};
let currentAudio = null;
let annotations = [];
let currentFilename = null;

const audioFile = document.getElementById('audioFile');
const audioPlayer = document.getElementById('audioPlayer');
const playerSection = document.getElementById('playerSection');
const ipaPalette = document.getElementById('ipaPalette');
const transcriptionInput = document.getElementById('transcriptionInput');
const addSegmentBtn = document.getElementById('addSegment');
const annotationsDiv = document.getElementById('annotations');
const saveBtn = document.getElementById('saveBtn');
const waveformCanvas = document.getElementById('waveformCanvas');
const waveformContainer = document.getElementById('waveformContainer');
const toggleWaveformBtn = document.getElementById('toggleWaveform');
const muteToggle = document.getElementById('muteToggle');
const clearTimestampsBtn = document.getElementById('clearTimestamps');
const createSegmentsBtn = document.getElementById('createSegmentsBtn');
const timestampMarkersDiv = document.getElementById('timestampMarkers');

let audioBuffer = null;
let timestamps = [];
let waveformCollapsed = false;
let activeSegmentIndex = null;
let dirty = false;
let lastWaveformWidth = 0;

const TIMESTAMP_DEDUPE_EPSILON = 0.005;

function markDirty() { dirty = true; }
function markClean() { dirty = false; }

function showToast(msg, type = 'info') {
    const el = document.createElement('div');
    el.className = `toast toast-${type}`;
    el.textContent = msg;
    document.body.appendChild(el);
    setTimeout(() => el.remove(), 2200);
}

window.addEventListener('beforeunload', (e) => {
    if (dirty) {
        e.preventDefault();
        e.returnValue = '';
    }
});

async function loadIPASymbols() {
    const res = await fetch('/static/ipa_symbols.json');
    ipaData = await res.json();
    renderIPAPalette();
    setupKeyboardShortcuts();
}

function renderIPAPalette() {
    ipaPalette.innerHTML = '';

    const keys = Object.keys(ipaData.keyboard_map).sort();

    keys.forEach(key => {
        const symbols = ipaData.keyboard_map[key];

        const keyGroup = document.createElement('div');
        keyGroup.className = 'key-group';

        const keyLabel = document.createElement('div');
        keyLabel.className = 'key-label';
        keyLabel.textContent = `Ctrl+${key.toUpperCase()}`;
        keyGroup.appendChild(keyLabel);

        const symbolsContainer = document.createElement('div');
        symbolsContainer.className = 'key-symbols';

        symbols.forEach(symbol => {
            const btn = document.createElement('div');
            btn.className = 'ipa-symbol';
            btn.textContent = symbol;
            btn.onclick = () => {
                insertAtCursor(symbol);
            };
            symbolsContainer.appendChild(btn);
        });

        keyGroup.appendChild(symbolsContainer);
        ipaPalette.appendChild(keyGroup);
    });
}

function setupKeyboardShortcuts() {
    transcriptionInput.addEventListener('keydown', (e) => {
        if (e.ctrlKey && !e.altKey && !e.metaKey) {
            const key = e.key.toLowerCase();
            const symbolSet = ipaData.keyboard_map[key];

            if (symbolSet && symbolSet.length > 0) {
                e.preventDefault();

                if (!keyIndexMap[key]) {
                    keyIndexMap[key] = 0;
                } else {
                    keyIndexMap[key] = (keyIndexMap[key] + 1) % symbolSet.length;
                }

                const symbol = symbolSet[keyIndexMap[key]];
                insertAtCursor(symbol);
            }
            return;
        }

        if (e.key === 'Enter' && !e.altKey && !e.metaKey && !e.shiftKey) {
            e.preventDefault();
            addSegmentBtn.click();
        }
    });
}

function insertAtCursor(text) {
    const activeElement = document.activeElement;

    if (activeElement && (activeElement.tagName === 'INPUT' || activeElement.tagName === 'TEXTAREA')) {
        const start = activeElement.selectionStart;
        const end = activeElement.selectionEnd;
        const value = activeElement.value;

        activeElement.value = value.substring(0, start) + text + value.substring(end);
        activeElement.selectionStart = activeElement.selectionEnd = start + text.length;
        activeElement.focus();
    } else {
        const start = transcriptionInput.selectionStart;
        const end = transcriptionInput.selectionEnd;
        const value = transcriptionInput.value;

        transcriptionInput.value = value.substring(0, start) + text + value.substring(end);
        transcriptionInput.selectionStart = transcriptionInput.selectionEnd = start + text.length;
        transcriptionInput.focus();
    }
}

async function loadAudioFile(filename) {
    currentFilename = filename;
    audioPlayer.src = `/audio/${filename}`;
    playerSection.style.display = 'block';
    await loadAnnotations();
    setupPlaybackHighlighting();
    await loadWaveform(filename);
}

async function loadWaveform(filename) {
    try {
        const response = await fetch(`/audio/${filename}`);
        const arrayBuffer = await response.arrayBuffer();

        const audioContext = new (window.AudioContext || window.webkitAudioContext)();
        audioBuffer = await audioContext.decodeAudioData(arrayBuffer);

        drawWaveform();
    } catch (error) {
        console.error('Error loading waveform:', error);
    }
}

const waveformResizeObserver = new ResizeObserver(() => {
    const width = waveformContainer.clientWidth;
    if (width === 0 || width === lastWaveformWidth) return;
    lastWaveformWidth = width;
    drawWaveform();
});
waveformResizeObserver.observe(waveformContainer);

function drawWaveform() {
    if (!audioBuffer) return;

    const canvas = waveformCanvas;
    const container = waveformContainer;
    canvas.width = container.clientWidth;
    canvas.height = 150;

    const ctx = canvas.getContext('2d');
    const data = audioBuffer.getChannelData(0);
    const step = Math.ceil(data.length / canvas.width);
    const amp = canvas.height / 2;

    ctx.fillStyle = '#f0f0f0';
    ctx.fillRect(0, 0, canvas.width, canvas.height);

    ctx.beginPath();
    ctx.strokeStyle = '#2196f3';
    ctx.lineWidth = 1;

    for (let i = 0; i < canvas.width; i++) {
        let min = 1.0;
        let max = -1.0;

        for (let j = 0; j < step; j++) {
            const datum = data[(i * step) + j];
            if (datum < min) min = datum;
            if (datum > max) max = datum;
        }

        ctx.moveTo(i, (1 + min) * amp);
        ctx.lineTo(i, (1 + max) * amp);
    }

    ctx.stroke();
    renderTimestampMarkers();
}

function renderTimestampMarkers() {
    timestampMarkersDiv.innerHTML = '';
    const duration = audioPlayer.duration || audioBuffer.duration;

    timestamps.sort((a, b) => a - b);

    // Render free timestamps (red markers)
    timestamps.forEach((time, idx) => {
        const marker = document.createElement('div');
        marker.className = 'timestamp-marker timestamp-free';
        const leftPercent = (time / duration) * 100;
        marker.style.left = `${leftPercent}%`;
        marker.title = `${time.toFixed(2)}s (free)`;
        marker.dataset.type = 'free';
        marker.dataset.index = idx;

        makeDraggable(marker, (newTime) => {
            timestamps[idx] = newTime;
            renderTimestampMarkers();
        });

        const deleteBtn = document.createElement('span');
        deleteBtn.className = 'marker-delete';
        deleteBtn.textContent = '×';
        deleteBtn.onclick = (e) => {
            e.stopPropagation();
            timestamps.splice(idx, 1);
            renderTimestampMarkers();
        };

        marker.appendChild(deleteBtn);
        timestampMarkersDiv.appendChild(marker);
    });

    // Render segment boundary timestamps (green markers)
    annotations.forEach((seg, segIdx) => {
        // Start marker
        const startMarker = document.createElement('div');
        startMarker.className = 'timestamp-marker timestamp-segment';
        if (activeSegmentIndex === segIdx) {
            startMarker.classList.add('highlighted');
        }
        const startPercent = (seg.startTime / duration) * 100;
        startMarker.style.left = `${startPercent}%`;
        startMarker.title = `Segment ${segIdx + 1} start: ${seg.startTime.toFixed(2)}s`;
        startMarker.dataset.type = 'segment';
        startMarker.dataset.segmentIndex = segIdx;
        startMarker.dataset.field = 'startTime';

        makeDraggable(startMarker, (newTime) => {
            moveSegmentBoundary(segIdx, 'startTime', newTime);
        });

        timestampMarkersDiv.appendChild(startMarker);

        // End marker
        const endMarker = document.createElement('div');
        endMarker.className = 'timestamp-marker timestamp-segment';
        if (activeSegmentIndex === segIdx) {
            endMarker.classList.add('highlighted');
        }
        const endPercent = (seg.endTime / duration) * 100;
        endMarker.style.left = `${endPercent}%`;
        endMarker.title = `Segment ${segIdx + 1} end: ${seg.endTime.toFixed(2)}s`;
        endMarker.dataset.type = 'segment';
        endMarker.dataset.segmentIndex = segIdx;
        endMarker.dataset.field = 'endTime';

        makeDraggable(endMarker, (newTime) => {
            moveSegmentBoundary(segIdx, 'endTime', newTime);
        });

        timestampMarkersDiv.appendChild(endMarker);
    });
}

function makeDraggable(marker, onDrag) {
    let isDragging = false;

    marker.addEventListener('mousedown', (e) => {
        if (e.target.classList.contains('marker-delete')) return;
        isDragging = true;
        marker.style.cursor = 'grabbing';
        e.preventDefault();
    });

    document.addEventListener('mousemove', (e) => {
        if (!isDragging) return;

        const rect = timestampMarkersDiv.getBoundingClientRect();
        const x = e.clientX - rect.left;
        const percent = Math.max(0, Math.min(1, x / rect.width));
        const duration = audioPlayer.duration || audioBuffer.duration;
        const newTime = percent * duration;

        onDrag(newTime);
    });

    document.addEventListener('mouseup', () => {
        if (isDragging) {
            isDragging = false;
            marker.style.cursor = 'grab';
        }
    });
}

function updateSegmentUI(segIdx) {
    // Update slider values
    const startSlider = document.querySelector(`.time-slider[data-index="${segIdx}"][data-field="startTime"]`);
    const endSlider = document.querySelector(`.time-slider[data-index="${segIdx}"][data-field="endTime"]`);
    const startValue = document.querySelector(`.time-value[data-index="${segIdx}"][data-field="startTime"]`);
    const endValue = document.querySelector(`.time-value[data-index="${segIdx}"][data-field="endTime"]`);

    if (startSlider) startSlider.value = annotations[segIdx].startTime;
    if (endSlider) endSlider.value = annotations[segIdx].endTime;
    if (startValue) startValue.textContent = `${annotations[segIdx].startTime.toFixed(2)}s`;
    if (endValue) endValue.textContent = `${annotations[segIdx].endTime.toFixed(2)}s`;

    renderTimestampMarkers();
    renderTimeline();
}

let currentPlayingSegment = null;

function setupPlaybackHighlighting() {
    audioPlayer.addEventListener('timeupdate', () => {
        const currentTime = audioPlayer.currentTime;

        if (currentPlayingSegment !== null) {
            const seg = annotations[currentPlayingSegment];
            if (seg && currentTime >= seg.endTime) {
                audioPlayer.pause();
                currentPlayingSegment = null;
            }
        }

        document.querySelectorAll('.annotation-segment').forEach(segment => {
            const idx = parseInt(segment.dataset.index);
            const ann = annotations[idx];

            if (ann && currentTime >= ann.startTime && currentTime <= ann.endTime) {
                segment.classList.add('active');
            } else {
                segment.classList.remove('active');
            }
        });

        document.querySelectorAll('.timeline-block').forEach(block => {
            const idx = parseInt(block.dataset.index);
            const ann = annotations[idx];

            if (ann && currentTime >= ann.startTime && currentTime <= ann.endTime) {
                block.classList.add('active');
            } else {
                block.classList.remove('active');
            }
        });
    });
}

audioFile.onchange = async (e) => {
    const file = e.target.files[0];
    if (!file) return;

    const formData = new FormData();
    formData.append('audio', file);

    try {
        const res = await fetch('/upload', {
            method: 'POST',
            body: formData
        });

        if (!res.ok) {
            const err = await res.json().catch(() => ({}));
            showToast(`Upload failed: ${err.error || res.statusText}`, 'error');
            return;
        }

        const data = await res.json();
        await loadAudioFile(data.filename);
    } catch (err) {
        showToast(`Upload failed: ${err.message}`, 'error');
    }
};

addSegmentBtn.onclick = () => {
    const text = transcriptionInput.value.trim();
    if (!text) return;

    const currentTime = audioPlayer.currentTime;
    const segment = {
        text,
        semanticLabel: '',
        startTime: currentTime,
        endTime: currentTime + 1
    };

    annotations.push(segment);
    transcriptionInput.value = '';
    markDirty();
    renderAnnotations();
};

waveformCanvas.onclick = (e) => {
    const rect = waveformCanvas.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const percent = x / rect.width;
    const duration = audioPlayer.duration || audioBuffer.duration;
    const time = percent * duration;

    if (timestamps.some(t => Math.abs(t - time) < TIMESTAMP_DEDUPE_EPSILON)) return;

    timestamps.push(time);
    renderTimestampMarkers();
};

clearTimestampsBtn.onclick = () => {
    timestamps = [];
    renderTimestampMarkers();
};

createSegmentsBtn.onclick = () => {
    if (timestamps.length === 0) {
        showToast('Add timestamps by clicking on the waveform first.', 'info');
        return;
    }

    if (annotations.length > 0) {
        if (!confirm('This will replace existing segments. Continue?')) {
            return;
        }
    }

    markDirty();

    const sortedTimestamps = [...timestamps].sort((a, b) => a - b);
    const duration = audioPlayer.duration || audioBuffer.duration;

    annotations = [];

    if (sortedTimestamps[0] > 0) {
        annotations.push({
            text: '',
            semanticLabel: '',
            startTime: 0,
            endTime: sortedTimestamps[0]
        });
    }

    for (let i = 0; i < sortedTimestamps.length - 1; i++) {
        annotations.push({
            text: '',
            semanticLabel: '',
            startTime: sortedTimestamps[i],
            endTime: sortedTimestamps[i + 1]
        });
    }

    if (sortedTimestamps[sortedTimestamps.length - 1] < duration) {
        annotations.push({
            text: '',
            semanticLabel: '',
            startTime: sortedTimestamps[sortedTimestamps.length - 1],
            endTime: duration
        });
    }

    renderAnnotations();
};

toggleWaveformBtn.onclick = () => {
    waveformCollapsed = !waveformCollapsed;
    if (waveformCollapsed) {
        waveformContainer.style.display = 'none';
        toggleWaveformBtn.textContent = '▶';
    } else {
        waveformContainer.style.display = 'block';
        toggleWaveformBtn.textContent = '▼';
    }
};

muteToggle.onchange = () => {
    audioPlayer.muted = muteToggle.checked;
};

const BOUNDARY_EPSILON = 0.001;

function findSharedBoundary(idx, field) {
    const currentVal = annotations[idx][field];
    const siblingField = field === 'startTime' ? 'endTime' : 'startTime';
    for (let i = 0; i < annotations.length; i++) {
        if (i === idx) continue;
        if (Math.abs(annotations[i][siblingField] - currentVal) < BOUNDARY_EPSILON) {
            return i;
        }
    }
    return -1;
}

function pointClearOfSegments(time, excludeIndices) {
    for (let i = 0; i < annotations.length; i++) {
        if (excludeIndices.includes(i)) continue;
        const other = annotations[i];
        if (time > other.startTime && time < other.endTime) return false;
    }
    return true;
}

function moveSegmentBoundary(idx, field, newTime) {
    const seg = annotations[idx];
    const partner = findSharedBoundary(idx, field);

    if (partner !== -1) {
        const lower = field === 'startTime' ? annotations[partner].startTime : seg.startTime;
        const upper = field === 'startTime' ? seg.endTime : annotations[partner].endTime;

        if (newTime <= lower || newTime >= upper) return;
        if (!pointClearOfSegments(newTime, [idx, partner])) return;

        const partnerField = field === 'startTime' ? 'endTime' : 'startTime';
        seg[field] = newTime;
        annotations[partner][partnerField] = newTime;
        markDirty();
        updateSegmentUI(idx);
        updateSegmentUI(partner);
        return;
    }

    if (checkOverlap(idx, field, newTime)) {
        seg[field] = newTime;
        markDirty();
        updateSegmentUI(idx);
    }
}

function checkOverlap(idx, field, value) {
    const segment = annotations[idx];
    const newStart = field === 'startTime' ? value : segment.startTime;
    const newEnd = field === 'endTime' ? value : segment.endTime;

    if (newStart >= newEnd) return false;

    for (let i = 0; i < annotations.length; i++) {
        if (i === idx) continue;
        const other = annotations[i];

        if ((newStart >= other.startTime && newStart < other.endTime) ||
            (newEnd > other.startTime && newEnd <= other.endTime) ||
            (newStart <= other.startTime && newEnd >= other.endTime)) {
            return false;
        }
    }
    return true;
}

function renderAnnotations() {
    annotationsDiv.innerHTML = '';
    const duration = audioPlayer.duration || 100;

    annotations.forEach((seg, idx) => {
        const div = document.createElement('div');
        div.className = 'annotation-segment';
        div.setAttribute('data-index', idx);
        div.draggable = true;

        const textContainer = document.createElement('div');
        textContainer.className = 'text-container';

        const textSpan = document.createElement('span');
        textSpan.className = 'annotation-text';
        textSpan.textContent = seg.text;
        textSpan.setAttribute('data-index', idx);

        textSpan.ondblclick = (e) => {
            e.stopPropagation();
            const input = document.createElement('input');
            input.type = 'text';
            input.className = 'annotation-text-edit';
            input.value = seg.text;

            input.onblur = () => {
                if (input.value !== seg.text) markDirty();
                seg.text = input.value;
                renderAnnotations();
                renderTimeline();
            };

            input.onkeydown = (e) => {
                if (e.key === 'Enter') {
                    input.blur();
                }
            };

            textSpan.replaceWith(input);
            input.focus();
            input.select();
        };

        textContainer.appendChild(textSpan);

        const semanticSpan = document.createElement('span');
        semanticSpan.className = 'semantic-label';
        semanticSpan.textContent = seg.semanticLabel || '(add word)';
        semanticSpan.setAttribute('data-index', idx);

        semanticSpan.ondblclick = (e) => {
            e.stopPropagation();
            const input = document.createElement('input');
            input.type = 'text';
            input.className = 'semantic-label-edit';
            input.value = seg.semanticLabel || '';
            input.placeholder = 'English word(s)';

            input.onblur = () => {
                if (input.value !== (seg.semanticLabel || '')) markDirty();
                seg.semanticLabel = input.value;
                renderAnnotations();
                renderTimeline();
            };

            input.onkeydown = (e) => {
                if (e.key === 'Enter') {
                    input.blur();
                }
            };

            semanticSpan.replaceWith(input);
            input.focus();
            input.select();
        };

        textContainer.appendChild(semanticSpan);
        div.appendChild(textContainer);

        const timeControls = document.createElement('div');
        timeControls.className = 'time-controls';
        timeControls.innerHTML = `
            <div class="time-slider-group">
                <label>Start: <span class="time-value" data-index="${idx}" data-field="startTime">${seg.startTime.toFixed(2)}s</span></label>
                <input type="range" class="time-slider" value="${seg.startTime}"
                       step="0.01" min="0" max="${duration}" data-index="${idx}" data-field="startTime">
            </div>
            <div class="time-slider-group">
                <label>End: <span class="time-value" data-index="${idx}" data-field="endTime">${seg.endTime.toFixed(2)}s</span></label>
                <input type="range" class="time-slider" value="${seg.endTime}"
                       step="0.01" min="0" max="${duration}" data-index="${idx}" data-field="endTime">
            </div>
        `;

        div.appendChild(timeControls);

        const deleteBtn = document.createElement('button');
        deleteBtn.className = 'delete-btn';
        deleteBtn.textContent = 'Delete';
        deleteBtn.onclick = () => deleteSegment(idx);
        div.appendChild(deleteBtn);

        div.onclick = (e) => {
            if (!e.target.classList.contains('delete-btn') &&
                !e.target.classList.contains('time-slider') &&
                !e.target.classList.contains('annotation-text-edit') &&
                !e.target.classList.contains('semantic-label-edit')) {
                activeSegmentIndex = idx;
                renderTimestampMarkers();
                if (!muteToggle.checked) {
                    currentPlayingSegment = idx;
                    audioPlayer.currentTime = seg.startTime;
                    audioPlayer.play();
                }
            }
        };

        annotationsDiv.appendChild(div);
    });

    document.querySelectorAll('.time-slider').forEach(slider => {
        slider.addEventListener('input', (e) => {
            const idx = parseInt(e.target.dataset.index);
            const field = e.target.dataset.field;
            const value = parseFloat(e.target.value);
            const before = annotations[idx][field];

            moveSegmentBoundary(idx, field, value);

            if (annotations[idx][field] === before) {
                e.target.value = before;
            }
        });
    });

    renderTimeline();
}

function renderTimeline() {
    const timeline = document.getElementById('timeline');
    if (!timeline) return;

    const duration = audioPlayer.duration || 100;
    timeline.innerHTML = '';

    annotations.forEach((seg, idx) => {
        const block = document.createElement('div');
        block.className = 'timeline-block';
        block.setAttribute('data-index', idx);

        const leftPercent = (seg.startTime / duration) * 100;
        const widthPercent = ((seg.endTime - seg.startTime) / duration) * 100;

        block.style.left = `${leftPercent}%`;
        block.style.width = `${widthPercent}%`;

        const displayText = seg.semanticLabel ? `${seg.semanticLabel} [${seg.text}]` : seg.text;
        block.textContent = displayText;

        const tooltipText = seg.semanticLabel
            ? `${seg.semanticLabel} (${seg.text}) - ${seg.startTime.toFixed(2)}s to ${seg.endTime.toFixed(2)}s`
            : `${seg.text} (${seg.startTime.toFixed(2)}s - ${seg.endTime.toFixed(2)}s)`;
        block.title = tooltipText;

        block.onclick = () => {
            if (!muteToggle.checked) {
                currentPlayingSegment = idx;
                audioPlayer.currentTime = seg.startTime;
                audioPlayer.play();
            }
        };

        timeline.appendChild(block);
    });
}

window.deleteSegment = (idx) => {
    annotations.splice(idx, 1);
    markDirty();
    renderAnnotations();
};

saveBtn.onclick = async () => {
    if (!currentFilename) return;

    try {
        const res = await fetch(`/annotations/${currentFilename}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(annotations)
        });
        if (!res.ok) {
            showToast(`Save failed: ${res.statusText}`, 'error');
            return;
        }
        markClean();
        showToast('Saved', 'success');
    } catch (err) {
        showToast(`Save failed: ${err.message}`, 'error');
    }
};

document.getElementById('exportJson').onclick = () => {
    if (!currentFilename) return;
    window.location.href = `/export/${currentFilename}/json`;
};

document.getElementById('exportTxt').onclick = () => {
    if (!currentFilename) return;
    window.location.href = `/export/${currentFilename}/txt`;
};

document.getElementById('exportZip').onclick = () => {
    if (!currentFilename) return;
    window.location.href = `/export/${currentFilename}/zip`;
};

async function loadAnnotations() {
    if (!currentFilename) return;

    const res = await fetch(`/annotations/${currentFilename}`);
    const data = await res.json();
    annotations = data || [];

    annotations.forEach(seg => {
        if (!seg.hasOwnProperty('semanticLabel')) {
            seg.semanticLabel = '';
        }
    });

    markClean();
    renderAnnotations();
}

async function init() {
    await loadIPASymbols();

    const res = await fetch('/audio/harvard.wav');
    if (res.ok) {
        await loadAudioFile('harvard.wav');
    }
}

init();