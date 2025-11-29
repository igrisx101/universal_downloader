"""
flask_universal_downloader.py

Fixed version with proper video+audio merging and playback support.

Requirements:
  - Python 3.10+
  - pip install yt-dlp flask
  - ffmpeg installed on system PATH

Run:
  python flask_universal_downloader.py
  Open http://127.0.0.1:5000 in your browser
"""

import os
import tempfile
import shutil
import threading
from pathlib import Path
from flask import Flask, request, jsonify, render_template_string, send_file
from yt_dlp import YoutubeDL

app = Flask(__name__)

YDL_PROBE_OPTS = {
    'quiet': True,
    'no_warnings': True,
    'skip_download': True,
}

INDEX_HTML = r"""
<!doctype html>
<html lang="en">
<head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Universal Downloader</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        .format-option {
            padding: 10px;
            margin: 5px 0;
            border: 1px solid #dee2e6;
            border-radius: 5px;
            cursor: pointer;
            transition: all 0.2s;
        }
        .format-option:hover {
            background-color: #f8f9fa;
            border-color: #0d6efd;
        }
        .format-option.selected {
            background-color: #e7f1ff;
            border-color: #0d6efd;
            border-width: 2px;
        }
        .format-badge {
            display: inline-block;
            padding: 2px 8px;
            margin: 2px;
            border-radius: 3px;
            font-size: 0.85em;
        }
        .quality-badge { background-color: #d1ecf1; color: #0c5460; }
        .size-badge { background-color: #d4edda; color: #155724; }
        .codec-badge { background-color: #fff3cd; color: #856404; }
        .has-audio-badge { background-color: #d1e7dd; color: #0f5132; }
        .no-audio-badge { background-color: #f8d7da; color: #842029; }
        .spinner { display: inline-block; width: 1rem; height: 1rem; border: 2px solid currentColor; border-right-color: transparent; border-radius: 50%; animation: spin 0.75s linear infinite; }
        @keyframes spin { to { transform: rotate(360deg); } }
        .quick-btn {
            border: 2px solid;
            font-weight: 500;
        }
    </style>
</head>
<body class="bg-light">
    <div class="container py-4" style="max-width: 1000px;">
        <h1 class="mb-3">🎬 Universal Downloader</h1>
        <p class="text-muted">Download videos and audio from any supported platform with quality selection.</p>

        <div class="card mb-4">
            <div class="card-body">
                <label for="urlInput" class="form-label fw-bold">Enter URL</label>
                <div class="input-group mb-3">
                    <input id="urlInput" class="form-control" placeholder="https://www.youtube.com/watch?v=..." />
                    <button id="probeBtn" class="btn btn-primary">
                        <span id="probeBtnText">Analyze</span>
                        <span id="probeSpinner" style="display:none;" class="spinner ms-2"></span>
                    </button>
                </div>
            </div>
        </div>

        <div id="errorArea" class="alert alert-danger" style="display:none;" role="alert"></div>

        <div id="resultArea" style="display:none">
            <div class="card mb-4">
                <div class="card-body">
                    <h5 class="card-title" id="videoTitle"></h5>
                    <p class="text-muted mb-0" id="videoDuration"></p>
                </div>
            </div>

            <div class="card mb-4">
                <div class="card-header bg-info text-white">
                    <strong>⚡ Quick Download Options</strong>
                </div>
                <div class="card-body">
                    <div class="d-flex gap-2 flex-wrap">
                        <button id="bestVideoBtn" class="btn btn-primary quick-btn">
                            📹 Best Quality Video (with audio)
                        </button>
                        <button id="bestAudioBtn" class="btn btn-success quick-btn">
                            🎵 Best Quality Audio Only
                        </button>
                        <button id="quickMP4Btn" class="btn btn-outline-primary quick-btn">
                            🎬 Best MP4 (compatible)
                        </button>
                    </div>
                    <p class="text-muted small mt-2 mb-0">
                        💡 <strong>Recommended:</strong> Use quick options above for best results. Manual selection below is for advanced users.
                    </p>
                </div>
            </div>

            <div class="row mb-4">
                <div class="col-12">
                    <div class="card">
                        <div class="card-header bg-secondary text-white">
                            <strong>🎯 Advanced: Manual Format Selection</strong>
                        </div>
                        <div class="card-body">
                            <div class="row">
                                <div class="col-md-6 mb-3">
                                    <h6>📹 Video Formats</h6>
                                    <div id="videoOptions" style="max-height: 300px; overflow-y: auto;">
                                    </div>
                                </div>
                                <div class="col-md-6 mb-3">
                                    <h6>🎵 Audio Formats</h6>
                                    <div id="audioOptions" style="max-height: 300px; overflow-y: auto;">
                                    </div>
                                </div>
                            </div>
                            <div class="alert alert-warning small mb-0" role="alert">
                                ⚠️ <strong>Note:</strong> Most video formats don't include audio. Select both video AND audio format, or use quick options above.
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            <div class="card">
                <div class="card-body">
                    <h6 class="card-title">Download Settings</h6>
                    
                    <div class="mb-3">
                        <label class="form-label">Custom Filename (optional)</label>
                        <input id="filename" class="form-control" placeholder="Leave blank to use video title"/>
                    </div>

                    <div class="mb-3">
                        <label class="form-label">Audio Format (for audio-only downloads)</label>
                        <select id="audioFormat" class="form-select" style="max-width:200px">
                            <option value="mp3">MP3</option>
                            <option value="m4a">M4A</option>
                            <option value="opus">OPUS</option>
                            <option value="wav">WAV</option>
                        </select>
                    </div>

                    <button id="downloadBtn" class="btn btn-success btn-lg">
                        <span id="downloadBtnText">⬇️ Download</span>
                        <span id="downloadSpinner" style="display:none;" class="spinner ms-2"></span>
                    </button>

                    <div id="downloadStatus" class="mt-3 alert alert-info" style="display:none;"></div>
                </div>
            </div>
        </div>

        <hr class="my-4"/>
        <p class="text-muted small">
            <strong>Note:</strong> Requires ffmpeg for merging video+audio. 
            Only download content you have rights to use.
        </p>
    </div>

<script>
let currentInfo = null;
let selectedVideo = null;
let selectedAudio = null;
let quickMode = null; // 'bestvideo', 'bestaudio', 'bestmp4'

function showError(msg) {
    const errArea = document.getElementById('errorArea');
    errArea.textContent = msg;
    errArea.style.display = 'block';
    setTimeout(() => errArea.style.display = 'none', 8000);
}

function formatFilesize(bytes) {
    if (!bytes || bytes === 0) return null;
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    if (bytes < 1024 * 1024 * 1024) return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
    return (bytes / (1024 * 1024 * 1024)).toFixed(2) + ' GB';
}

function formatDuration(seconds) {
    if (!seconds) return '';
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = Math.floor(seconds % 60);
    if (h > 0) return `${h}:${m.toString().padStart(2,'0')}:${s.toString().padStart(2,'0')}`;
    return `${m}:${s.toString().padStart(2,'0')}`;
}

async function probeUrl(url) {
    const res = await fetch('/probe', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({url})
    });
    if (!res.ok) {
        const text = await res.text();
        throw new Error(text);
    }
    return res.json();
}

function createFormatOption(format, type) {
    const div = document.createElement('div');
    div.className = 'format-option';
    div.dataset.formatId = format.format_id;
    div.dataset.type = type;
    
    let quality = '';
    let hasAudio = false;
    
    if (type === 'video') {
        quality = format.resolution || `${format.height}p`;
        if (format.fps) quality += ` @${format.fps}fps`;
        hasAudio = format.acodec && format.acodec !== 'none';
    } else {
        quality = format.abr ? `${Math.round(format.abr)}kbps` : 'Audio';
    }
    
    const vcodec = format.vcodec && format.vcodec !== 'none' ? format.vcodec.split('.')[0].toUpperCase() : '';
    const acodec = format.acodec && format.acodec !== 'none' ? format.acodec.split('.')[0].toUpperCase() : '';
    const codec = vcodec || acodec;
    
    // Calculate approximate bitrate for size estimation
    let bitrateInfo = '';
    const bitrate = format.tbr || format.vbr || format.abr;
    if (bitrate) {
        bitrateInfo = ` (${Math.round(bitrate)}kbps)`;
    }
    
    const size = formatFilesize(format.filesize || format.filesize_approx);
    const displaySize = size ? `${size}${bitrateInfo}` : (bitrate ? `~${Math.round(bitrate)}kbps` : 'Unknown');
    
    div.innerHTML = `
        <div class="d-flex justify-content-between align-items-center">
            <div>
                <strong>${format.ext.toUpperCase()}</strong>
                <span class="format-badge quality-badge">${quality}</span>
                ${codec ? `<span class="format-badge codec-badge">${codec}</span>` : ''}
                ${type === 'video' ? (hasAudio ? '<span class="format-badge has-audio-badge">✓ Audio</span>' : '<span class="format-badge no-audio-badge">✗ No Audio</span>') : ''}
            </div>
            <span class="format-badge size-badge">${displaySize}</span>
        </div>
    `;
    
    div.addEventListener('click', () => selectFormat(format, type, div));
    return div;
}

function selectFormat(format, type, element) {
    quickMode = null; // Reset quick mode
    if (type === 'video') {
        document.querySelectorAll('[data-type="video"]').forEach(el => el.classList.remove('selected'));
        selectedVideo = format.format_id;
    } else {
        document.querySelectorAll('[data-type="audio"]').forEach(el => el.classList.remove('selected'));
        selectedAudio = format.format_id;
    }
    element.classList.add('selected');
}

function estimateSize(format, duration) {
    // If we have actual file size, use it
    if (format.filesize) return format.filesize;
    if (format.filesize_approx) return format.filesize_approx;
    
    // Otherwise estimate from bitrate
    if (!duration) return null;
    
    let bitrate = format.tbr || format.vbr || format.abr;
    if (!bitrate) return null;
    
    // bitrate is in kbps, duration in seconds
    // size = (bitrate * 1000 / 8) * duration bytes
    return Math.round((bitrate * 1000 / 8) * duration);
}

function renderFormats(info) {
    currentInfo = info;
    document.getElementById('videoTitle').textContent = info.title || 'Unknown Title';
    
    const duration = info.duration;
    let durationText = duration ? `Duration: ${formatDuration(duration)}` : '';
    
    // Calculate best quality estimates for quick download options
    const videoFormats = (info.video_formats || []).sort((a, b) => 
        (b.height || 0) - (a.height || 0)
    );
    const audioFormats = (info.audio_formats || []).sort((a, b) => 
        (b.abr || 0) - (a.abr || 0)
    );
    
    if (duration && videoFormats.length > 0 && audioFormats.length > 0) {
        const bestVideo = videoFormats[0];
        const bestAudio = audioFormats[0];
        
        const videoSize = estimateSize(bestVideo, duration);
        const audioSize = estimateSize(bestAudio, duration);
        
        if (videoSize && audioSize) {
            const totalSize = videoSize + audioSize;
            durationText += ` • Estimated size: ${formatFilesize(totalSize)}`;
        }
    }
    
    document.getElementById('videoDuration').textContent = durationText;
    
    const videoContainer = document.getElementById('videoOptions');
    const audioContainer = document.getElementById('audioOptions');
    videoContainer.innerHTML = '';
    audioContainer.innerHTML = '';
    
    if (videoFormats.length === 0) {
        videoContainer.innerHTML = '<p class="text-muted">No video formats available</p>';
    } else {
        videoFormats.forEach(fmt => {
            // Enhance format with estimated size if missing
            if (!fmt.filesize && !fmt.filesize_approx && duration) {
                fmt.filesize_approx = estimateSize(fmt, duration);
            }
            videoContainer.appendChild(createFormatOption(fmt, 'video'));
        });
    }
    
    if (audioFormats.length === 0) {
        audioContainer.innerHTML = '<p class="text-muted">No audio formats available</p>';
    } else {
        audioFormats.forEach(fmt => {
            // Enhance format with estimated size if missing
            if (!fmt.filesize && !fmt.filesize_approx && duration) {
                fmt.filesize_approx = estimateSize(fmt, duration);
            }
            audioContainer.appendChild(createFormatOption(fmt, 'audio'));
        });
    }
    
    document.getElementById('resultArea').style.display = 'block';
}

document.getElementById('probeBtn').addEventListener('click', async () => {
    const url = document.getElementById('urlInput').value.trim();
    if (!url) {
        showError('Please enter a URL');
        return;
    }
    
    const btn = document.getElementById('probeBtn');
    const btnText = document.getElementById('probeBtnText');
    const spinner = document.getElementById('probeSpinner');
    
    btn.disabled = true;
    btnText.textContent = 'Analyzing...';
    spinner.style.display = 'inline-block';
    
    try {
        const info = await probeUrl(url);
        renderFormats(info);
        document.getElementById('errorArea').style.display = 'none';
    } catch (err) {
        showError('Failed to analyze URL: ' + err.message);
        console.error(err);
    } finally {
        btn.disabled = false;
        btnText.textContent = 'Analyze';
        spinner.style.display = 'none';
    }
});

document.getElementById('bestVideoBtn').addEventListener('click', () => {
    quickMode = 'bestvideo';
    selectedVideo = null;
    selectedAudio = null;
    document.querySelectorAll('.format-option').forEach(el => el.classList.remove('selected'));
    
    // Calculate approximate size
    if (currentInfo && currentInfo.video_formats && currentInfo.audio_formats && currentInfo.duration) {
        const bestVideo = currentInfo.video_formats[0];
        const bestAudio = currentInfo.audio_formats[0];
        const videoSize = estimateSize(bestVideo, currentInfo.duration);
        const audioSize = estimateSize(bestAudio, currentInfo.duration);
        
        if (videoSize && audioSize) {
            const totalSize = formatFilesize(videoSize + audioSize);
            showDownloadStatus(`✓ Best quality video with audio selected (approx. ${totalSize})`);
        } else {
            showDownloadStatus('✓ Best quality video with audio selected (will be merged)');
        }
    } else {
        showDownloadStatus('✓ Best quality video with audio selected (will be merged)');
    }
});

document.getElementById('bestAudioBtn').addEventListener('click', () => {
    quickMode = 'bestaudio';
    selectedVideo = null;
    selectedAudio = null;
    document.querySelectorAll('.format-option').forEach(el => el.classList.remove('selected'));
    
    // Calculate approximate size
    if (currentInfo && currentInfo.audio_formats && currentInfo.duration) {
        const bestAudio = currentInfo.audio_formats[0];
        const audioSize = estimateSize(bestAudio, currentInfo.duration);
        
        if (audioSize) {
            const sizeText = formatFilesize(audioSize);
            showDownloadStatus(`✓ Best audio quality selected (approx. ${sizeText})`);
        } else {
            showDownloadStatus('✓ Best audio quality selected');
        }
    } else {
        showDownloadStatus('✓ Best audio quality selected');
    }
});

document.getElementById('quickMP4Btn').addEventListener('click', () => {
    quickMode = 'bestmp4';
    selectedVideo = null;
    selectedAudio = null;
    document.querySelectorAll('.format-option').forEach(el => el.classList.remove('selected'));
    showDownloadStatus('✓ Best MP4 format selected (maximum compatibility)');
});

function showDownloadStatus(msg) {
    const status = document.getElementById('downloadStatus');
    status.textContent = msg;
    status.style.display = 'block';
    setTimeout(() => status.style.display = 'none', 4000);
}

document.getElementById('downloadBtn').addEventListener('click', async () => {
    let format;
    
    if (quickMode === 'bestvideo') {
        format = 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best';
    } else if (quickMode === 'bestaudio') {
        format = 'bestaudio';
    } else if (quickMode === 'bestmp4') {
        format = 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best';
    } else {
        // Manual selection
        if (!selectedVideo && !selectedAudio) {
            showError('Please select a format or use one of the quick download options above');
            return;
        }
        
        if (selectedVideo && selectedAudio) {
            format = `${selectedVideo}+${selectedAudio}`;
        } else if (selectedVideo) {
            format = selectedVideo;
        } else {
            format = selectedAudio;
        }
    }
    
    const url = document.getElementById('urlInput').value.trim();
    const filename = document.getElementById('filename').value.trim();
    const audioFormat = document.getElementById('audioFormat').value;
    
    const btn = document.getElementById('downloadBtn');
    const btnText = document.getElementById('downloadBtnText');
    const spinner = document.getElementById('downloadSpinner');
    
    btn.disabled = true;
    btnText.textContent = 'Downloading & Processing...';
    spinner.style.display = 'inline-block';
    
    try {
        const resp = await fetch('/download', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                url,
                format,
                filename,
                audio_format: audioFormat,
                is_audio_only: quickMode === 'bestaudio'
            })
        });
        
        if (!resp.ok) {
            const text = await resp.text();
            throw new Error(text);
        }
        
        const blob = await resp.blob();
        const cd = resp.headers.get('Content-Disposition') || '';
        let outName = 'download';
        const match = cd.match(/filename\*=UTF-8''(.+)$|filename="?([^";]+)"?/);
        if (match) {
            outName = decodeURIComponent(match[1] || match[2] || outName);
        }
        
        const urlBlob = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = urlBlob;
        a.download = outName;
        document.body.appendChild(a);
        a.click();
        a.remove();
        URL.revokeObjectURL(urlBlob);
        
        showDownloadStatus('✅ Download complete! Check your downloads folder.');
    } catch (err) {
        showError('Download failed: ' + err.message);
        console.error(err);
    } finally {
        btn.disabled = false;
        btnText.textContent = '⬇️ Download';
        spinner.style.display = 'none';
    }
});

// Allow Enter key to probe
document.getElementById('urlInput').addEventListener('keypress', (e) => {
    if (e.key === 'Enter') {
        document.getElementById('probeBtn').click();
    }
});
</script>
</body>
</html>
"""


def probe_info(url):
    """Use yt-dlp to fetch metadata and formats for a URL."""
    with YoutubeDL(YDL_PROBE_OPTS) as ydl:
        info = ydl.extract_info(url, download=False)
    return info


def classify_formats(formats):
    """Separate formats into video and audio categories."""
    video_formats = []
    audio_formats = []
    
    for fmt in formats:
        vcodec = fmt.get('vcodec', 'none')
        acodec = fmt.get('acodec', 'none')
        
        # Video format: has video codec and is not 'none'
        if vcodec and vcodec != 'none':
            # Mark if it actually has audio included
            fmt['has_audio'] = acodec and acodec != 'none'
            video_formats.append(fmt)
        # Audio-only format: has audio but no video
        elif acodec and acodec != 'none' and (not vcodec or vcodec == 'none'):
            audio_formats.append(fmt)
    
    return video_formats, audio_formats


@app.route('/')
def index():
    return render_template_string(INDEX_HTML)


@app.route('/probe', methods=['POST'])
def probe():
    data = request.get_json() or {}
    url = data.get('url')
    if not url:
        return 'Missing url', 400
    
    try:
        info = probe_info(url)
        formats = info.get('formats', [])
        
        video_formats, audio_formats = classify_formats(formats)
        
        return jsonify({
            'title': info.get('title'),
            'duration': info.get('duration'),
            'formats': formats,
            'video_formats': video_formats,
            'audio_formats': audio_formats,
        })
    except Exception as e:
        return f'Probe failed: {str(e)}', 500


@app.route('/download', methods=['POST'])
def download():
    data = request.get_json() or {}
    url = data.get('url')
    fmt = data.get('format')
    audio_format = data.get('audio_format', 'mp3')
    filename_hint = data.get('filename', '').strip()
    is_audio_only = data.get('is_audio_only', False)

    if not url or not fmt:
        return 'Missing url or format', 400

    tempdir = tempfile.mkdtemp(prefix='ydl_')
    
    try:
        # Base output template
        outtmpl = os.path.join(tempdir, '%(title)s.%(ext)s')
        
        opts = {
            'quiet': False,
            'no_warnings': False,
            'outtmpl': outtmpl,
        }
        
        # Check if this is audio-only based on format string or flag
        is_audio = is_audio_only or fmt == 'bestaudio' or ('+' not in fmt and 'audio' in fmt.lower())
        
        if is_audio:
            # Audio-only download with conversion
            opts['format'] = 'bestaudio/best'
            opts['postprocessors'] = [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': audio_format,
                'preferredquality': '192',
            }]
        else:
            # Video download - ALWAYS ensure audio is included
            # This is the critical fix
            if '+' in fmt:
                # User manually selected video+audio
                opts['format'] = fmt
            elif 'bestvideo' in fmt or 'best' in fmt:
                # Quick select options - already have proper format strings
                opts['format'] = fmt
            else:
                # Single video format selected - FORCE audio addition
                # Check if the format actually has audio
                format_has_audio = _check_format_has_audio(url, fmt)
                
                if format_has_audio:
                    # Format already includes audio
                    opts['format'] = fmt
                else:
                    # Video-only format - MUST add audio
                    opts['format'] = f"{fmt}+bestaudio/bestaudio*"
                    print(f"Selected format {fmt} has no audio, adding bestaudio")
            
            # Always merge to mp4 for maximum compatibility
            opts['merge_output_format'] = 'mp4'
            
            # Ensure proper merging and conversion
            opts['postprocessors'] = [
                {
                    'key': 'FFmpegVideoRemuxer',
                    'preferedformat': 'mp4',
                },
                {
                    'key': 'FFmpegMetadata',
                }
            ]
            
            # Additional options for better quality
            opts['prefer_ffmpeg'] = True
            opts['keepvideo'] = False
        
        print(f"Downloading with format: {opts['format']}")
        print(f"Options: {opts}")
        
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
        
        # Find the downloaded file
        files = list(Path(tempdir).glob('*'))
        if not files:
            return 'No file produced - download may have failed', 500
        
        # Get the largest file (the actual download)
        files_sorted = sorted(files, key=lambda p: p.stat().st_size, reverse=True)
        chosen = files_sorted[0]
        
        print(f"Downloaded file: {chosen.name} ({chosen.stat().st_size} bytes)")
        
        # Determine output filename
        if filename_hint:
            # Add appropriate extension
            if is_audio:
                out_name = f"{filename_hint}.{audio_format}"
            else:
                out_name = f"{filename_hint}.mp4"
        else:
            out_name = chosen.name
        
        return send_file(
            str(chosen),
            as_attachment=True,
            download_name=out_name,
            mimetype='application/octet-stream'
        )
        
    except Exception as e:
        print(f"Download error: {str(e)}")
        import traceback
        traceback.print_exc()
        return f'Download failed: {str(e)}', 500
    finally:
        # Clean up in background
        def cleanup(path):
            try:
                shutil.rmtree(path, ignore_errors=True)
            except:
                pass
        threading.Thread(target=cleanup, args=(tempdir,), daemon=True).start()


def _check_format_has_audio(url, fmt_id):
    """Check if a specific format actually has audio."""
    try:
        info = probe_info(url)
        for f in info.get('formats', []):
            if f.get('format_id') == str(fmt_id):
                acodec = f.get('acodec', 'none')
                has_audio = acodec and acodec != 'none'
                print(f"Format {fmt_id}: acodec={acodec}, has_audio={has_audio}")
                return has_audio
    except Exception as e:
        print(f"Error checking format audio: {e}")
    return False


if __name__ == '__main__':
    print("=" * 60)
    print("Universal Downloader Started")
    print("=" * 60)
    print("Open http://127.0.0.1:5000 in your browser")
    print("Make sure ffmpeg is installed and in your PATH")
    print("Press Ctrl+C to stop")
    print("=" * 60)
    app.run(host='127.0.0.1', port=5000, debug=True)