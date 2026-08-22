#!/usr/bin/env python3
"""
ZOOM L6Max .prj file parser
Reads L6MAXPRJDATA.prj and determines which tracks were enabled/recorded.
Also analyses WAV file content to detect empty (noise-floor-only) tracks.

File layout (observed via reverse-engineering):
  0x0000 – 0x002F : 48-byte ASCII header "ZOOM L6MAX   PROJECT DATA VER0001 ..."
  0x0030 – 0x014F : 12 x 24-byte channel-strip blocks (CH01-CH12)
  0x0150 – 0x027F : global / mixer section
  0x0298 – 0x03AF : second set of 12 x 24-byte channel-strip blocks
  0x03B0 – end   : master / default template data

SD-CARD FRIENDLY DESIGN
  The PRJ file is only ~3 KB and is read in full (instant).
  WAV files are NEVER read in full. Total I/O per WAV: < 8 KB.
"""

#%% Parameters and Imports
import os
import re
import struct
import math
from pathlib import Path
import shutil


# Default session path (modify as needed for interactive runs)
PRJ_PATH = "/Users/alex/Music/ZOOM_L6Max/260719_141521/L6MAXPRJDATA.prj"

# ---------------------------------------------------------------------------
# Audio silence-detection thresholds
# ---------------------------------------------------------------------------
SILENCE_PEAK_DB   = -48.0   # if peak below this  -> candidate for silence
NOISE_FLOOR_DB    = -48.0   # per-sample threshold for "above noise floor"
NOISE_PCT_MAX     = 0.5     # if < this % of samples exceed noise floor -> empty

# ---------------------------------------------------------------------------
# SD-card optimised I/O limits  (tune if needed)
# ---------------------------------------------------------------------------
HEADER_PROBE      = 512     # bytes read from start of WAV to locate chunks
AUDIO_PROBE_BYTES = 4096    # bytes of audio data sampled (~5 ms @ 48 kHz/32-bit stereo)

# ---------------------------------------------------------------------------
# PRJ constants
# ---------------------------------------------------------------------------
HEADER_MAGIC = b"ZOOM L6MAX"
HEADER_SIZE  = 0x30
CH_BLOCK     = 24
NUM_CH       = 12
CH_OFFSET    = HEADER_SIZE
DEFAULT_PAN  = 0x40

# Mapping from WAV track name -> PRJ channel index (0-based)
TRACK_CH_MAP = {
    "TRACK01":    [0],
    "TRACK02":    [1],
    "TRACK03":    [2],
    "TRACK04":    [3],
    "TRACK05_ST": [4],
    "TRACK06_ST": [5],
    "TRACK07_ST": [6],
    "TRACK08_ST": [7],
}

#%% Functions

def parse_prj(path):
    """Read the PRJ file (~3 KB) and return channel-strip info."""
    with open(path, "rb") as f:
        data = f.read()

    if not data.startswith(HEADER_MAGIC):
        raise ValueError(f"Not a ZOOM L6MAX project file: {path!r}")

    header = data[:HEADER_SIZE].rstrip(b"\x00").decode("ascii", errors="replace").strip()

    channels = []
    for i in range(NUM_CH):
        off          = CH_OFFSET + i * CH_BLOCK
        block        = data[off : off + CH_BLOCK]
        pan          = block[8]
        routing_flag = block[21]
        ch_on        = block[22]
        channels.append(dict(
            index        = i,
            name         = f"CH{i+1:02d}",
            pan          = pan,
            pan_adjusted = pan != DEFAULT_PAN,
            routing_flag = routing_flag,
            ch_on        = ch_on,
            raw          = block.hex(),
        ))

    return dict(header=header, channels=channels, raw_size=len(data))


def find_wav_files(session_dir):
    """
    Return sorted list of (track_name, filename) for all non-MASTER WAV files
    in the session directory. Does NOT open any WAV files.
    """
    wav_re = re.compile(r"^s?([A-Z0-9_]+?)(?:_\d+)?\.wav$", re.IGNORECASE)
    tracks = {}
    if not os.path.isdir(session_dir):
        return []
    for fname in os.listdir(session_dir):
        m = wav_re.match(fname)
        if not m:
            continue
        name = m.group(1).upper()
        if name == "MASTER":
            continue
        tracks[name] = fname
    return sorted(tracks.items())


def probe_wav(wav_path):
    """
    Probe a WAV file using only two small reads:
      1. First HEADER_PROBE bytes  -> locate fmt / data chunks, get format params.
      2. First AUDIO_PROBE_BYTES of the data chunk -> measure peak & noise %.

    Returns dict with keys:
        file_bytes, n_channels, sample_rate, bits, duration_s,
        peak_db, pct_above_noise, is_empty
    Or None if the header cannot be parsed.
    """
    try:
        file_bytes = os.path.getsize(wav_path)

        with open(wav_path, "rb") as f:
            # ---- Read 1: header probe ----
            header_buf = f.read(HEADER_PROBE)

            fmt_pos  = header_buf.find(b"fmt ")
            data_pos = header_buf.find(b"data")

            if fmt_pos == -1:
                return None  # can't find fmt chunk in first 512 bytes

            # Parse fmt chunk (16 bytes minimum)
            fc = header_buf[fmt_pos + 8 : fmt_pos + 24]
            if len(fc) < 16:
                return None
            audio_fmt, n_ch, sr, _, _, bits = struct.unpack("<HHIIHH", fc)

            if data_pos == -1:
                # data chunk starts beyond HEADER_PROBE – scan a bit more
                extra    = f.read(512)
                combined = header_buf + extra
                data_pos = combined.find(b"data")
                if data_pos == -1:
                    return None
                header_buf = combined

            data_chunk_size = struct.unpack("<I", header_buf[data_pos + 4 : data_pos + 8])[0]
            audio_offset    = data_pos + 8   # absolute byte offset within the file

            # Derive duration from chunk size
            bytes_per_frame = n_ch * (bits // 8)
            n_frames  = data_chunk_size // bytes_per_frame if bytes_per_frame else 0
            duration  = n_frames / sr if sr > 0 else 0

            # ---- Read 2: multi-spot audio probe ----
            num_probes = 5
            max_offset = max(audio_offset, audio_offset + data_chunk_size - AUDIO_PROBE_BYTES)
            
            probe_offsets = []
            if max_offset > audio_offset:
                step = (max_offset - audio_offset) // (num_probes - 1)
                probe_offsets = [audio_offset + i * step for i in range(num_probes)]
            else:
                probe_offsets = [audio_offset]

            probe_bufs = []
            for offset in probe_offsets:
                f.seek(offset)
                probe_bufs.append(f.read(AUDIO_PROBE_BYTES))

        # Analyse the probe buffers
        bytes_per_sample = max(1, bits // 8)
        fmt_char = "f" if (bits == 32 and audio_fmt == 3) else ("h" if bits == 16 else "i")
        scale    = 1.0
        if bits == 16:
            scale = 1.0 / 32768.0
        elif bits == 32 and audio_fmt == 1:   # int32 PCM
            scale = 1.0 / 2147483648.0

        max_peak_db = -999.0
        max_pct = 0.0
        any_active = False

        for probe_buf in probe_bufs:
            if not probe_buf:
                continue
                
            max_val         = 0.0
            rms_sum         = 0.0
            count           = 0
            above_noise     = 0
            noise_threshold = 10 ** (NOISE_FLOOR_DB / 20.0)

            pos = 0
            while pos + bytes_per_sample <= len(probe_buf):
                s = abs(struct.unpack(f"<{fmt_char}", probe_buf[pos : pos + bytes_per_sample])[0]) * scale
                if s > max_val:
                    max_val = s
                rms_sum += s * s
                count   += 1
                if s > noise_threshold:
                    above_noise += 1
                pos += bytes_per_sample

            if count == 0:
                peak_db = -999.0
                pct     = 0.0
            else:
                peak_db = 20 * math.log10(max_val) if max_val > 1e-12 else -999.0
                pct     = above_noise / count * 100.0

            if peak_db > max_peak_db:
                max_peak_db = peak_db
            if pct > max_pct:
                max_pct = pct

            spot_empty = (peak_db < SILENCE_PEAK_DB) or (pct < NOISE_PCT_MAX)
            if not spot_empty:
                any_active = True

        is_empty = not any_active

        return dict(
            file_bytes      = file_bytes,
            n_channels      = n_ch,
            sample_rate     = sr,
            bits            = bits,
            duration_s      = duration,
            peak_db         = max_peak_db,
            pct_above_noise = max_pct,
            is_empty        = is_empty,
        )

    except Exception:
        return None


def print_report(prj_path):
    session_dir  = os.path.dirname(prj_path)
    session_name = os.path.basename(session_dir)

    print("=" * 70)
    print(f"  Session : {session_name}")
    print(f"  PRJ     : {prj_path}")
    print("=" * 70)

    # Parse PRJ (full read, ~3 KB, instant)
    try:
        prj = parse_prj(prj_path)
    except (ValueError, IndexError) as exc:
        print(f"ERROR: {exc}")
        return

    print(f"  Header  : {prj['header']}")
    print(f"  PRJ size: {prj['raw_size']} bytes  (header probe only)")
    print()

    # --- 1. WAV discovery + tiny probe ---
    wav_files = find_wav_files(session_dir)

    print("Tracks  (WAV header + ~4 KB audio probe — SD-card safe, no full read)")
    print("-" * 70)
    print(f"  {'Track':<14} {'File':<28} {'Size':>8}  {'Peak':>7}  {'>noise':>6}  Result")
    print(f"  {'-'*14} {'-'*28} {'-'*8}  {'-'*7}  {'-'*6}  {'-'*14}")

    copy_list = []   # (track_name, filename, bytes)
    skip_list = []

    if wav_files:
        for track_name, wav_fname in wav_files:
            wav_path = os.path.join(session_dir, wav_fname)
            info     = probe_wav(wav_path)
            if info:
                mb       = info["file_bytes"] / 1_048_576
                peak_str = f"{info['peak_db']:+.1f}dB"
                pct_str  = f"{info['pct_above_noise']:.1f}%"
                result   = "SKIP (empty)" if info["is_empty"] else "COPY  ✓"
                print(f"  {track_name:<14} {wav_fname:<28} {mb:>6.1f}MB  {peak_str:>7}  {pct_str:>6}  {result}")
                if info["is_empty"]:
                    skip_list.append((track_name, wav_fname, info["file_bytes"]))
                else:
                    copy_list.append((track_name, wav_fname, info["file_bytes"]))
            else:
                print(f"  {track_name:<14} {wav_fname:<28} {'?':>8}  {'?':>7}  {'?':>6}  (unreadable header)")
    else:
        print("  No WAV files found in session directory.")
    print()

    # --- 2. PRJ channel-strip analysis ---
    print("Channel-strip analysis  (PRJ binary only — zero WAV I/O)")
    print("-" * 70)
    print(f"  {'Channel':<8} {'Pan':<14} {'Moved?':<8} {'Route flag':<12} ch_on")
    print(f"  {'-'*8} {'-'*14} {'-'*8} {'-'*12} {'-'*5}")

    active_ch = []
    for ch in prj["channels"]:
        pan_hex = f"0x{ch['pan']:02X}"
        if ch["pan"] < DEFAULT_PAN:
            pan_note = f"{pan_hex} (L,{ch['pan']})"
        elif ch["pan"] > DEFAULT_PAN:
            pan_note = f"{pan_hex} (R,{ch['pan']})"
        else:
            pan_note = f"{pan_hex} (centre)"
        adj    = "YES" if ch["pan_adjusted"] else "no"
        flag   = ch["routing_flag"]
        marker = " ◀" if ch["pan_adjusted"] or flag else ""
        if ch["pan_adjusted"] or flag:
            active_ch.append(ch["name"])
        print(f"  {ch['name']:<8} {pan_note:<14} {adj:<8} {str(flag):<12} {ch['ch_on']}{marker}")

    print()
    if active_ch:
        print(f"  Non-default channels in PRJ: {', '.join(active_ch)}")
    else:
        print("  All channels at default settings in PRJ.")
    print()

    # --- 3. Copy / skip summary ---
    print("=" * 70)
    print("COPY / SKIP SUMMARY")
    print("=" * 70)

    # Always-copy project files
    always = sorted(f for f in os.listdir(session_dir)
                    if f.upper() in ("L6MAXPRJDATA.PRJ", "MASTER_01.WAV"))
    if always:
        print(f"  Always copy  : {', '.join(always)}")

    if copy_list:
        copy_bytes = sum(b for _, _, b in copy_list)
        print(f"  Copy ({len(copy_list)} track files, {copy_bytes / 1_048_576:.1f} MB):")
        for _, fname, sz in copy_list:
            print(f"    {fname:<36}  {sz / 1_048_576:.1f} MB")
    else:
        print("  No tracks with real audio detected.")

    print()

    if skip_list:
        skip_bytes = sum(b for _, _, b in skip_list)
        print(f"  Skip — empty/noise ({len(skip_list)} files, saves {skip_bytes / 1_048_576:.1f} MB):")
        for _, fname, sz in skip_list:
            print(f"    {fname:<36}  {sz / 1_048_576:.1f} MB")
    else:
        print("  All WAV files contain audio — copy everything.")

    print()


#%% Execution
path_to_audio = "/Volumes/L6max/RECORDER"
destination_folder = "/Users/alex/Music/ZOOM_L6Max"

source_path = Path(path_to_audio)
dest_dir = Path(destination_folder)

# If path_to_audio is a file (like the .prj), use its parent's parent to loop over all sessions
if source_path.is_file():
    base_dir = source_path.parent.parent
else:
    base_dir = source_path

if not base_dir.exists():
    print(f"Directory not found: {base_dir}")
else:
    # Loop over folders in base directory
    for session_dir in base_dir.iterdir():
        if not session_dir.is_dir():
            continue
            
        # Check for PRJ file (case-insensitive)
        prj_files = list(session_dir.glob("L6MAXPRJDATA.*"))
        if not prj_files:
            continue
        prj_file = prj_files[0]
                
        session_name = session_dir.name
        
        # Skip if somehow the destination folder is inside the base_dir and we hit it
        if session_dir.resolve() == dest_dir.resolve():
            continue
            
        print(f"Processing session: {session_name}...")
        
        # Parse PRJ
        try:
            prj = parse_prj(str(prj_file))
        except Exception as e:
            print(f"  Skipping {session_name}: could not parse PRJ ({e})")
            continue
            
        wav_files = find_wav_files(str(session_dir))
        
        # Determine active channels from PRJ (pan moved or aux sends via routing_flag)
        active_channels = set()
        for ch in prj["channels"]:
            if ch["routing_flag"] != 0 or ch["pan_adjusted"]:
                active_channels.add(ch["name"])
        
        files_to_copy = []
        
        # Build Markdown summary
        md_lines = [
            f"# Session: {session_name}\n",
            f"**PRJ File:** `{prj_file.name}`  \n",
            f"**Header:** `{prj['header']}`\n\n",
            "## Channel Strip Settings\n",
            "| Channel | Pan | Moved? | Route Flag (Aux) | CH On |\n",
            "|---|---|---|---|---|\n"
        ]
        
        for ch in prj["channels"]:
            pan_hex = f"0x{ch['pan']:02X}"
            pan_note = f"{pan_hex} (ctr)"
            if ch["pan"] < DEFAULT_PAN: pan_note = f"{pan_hex} (L,{ch['pan']})"
            elif ch["pan"] > DEFAULT_PAN: pan_note = f"{pan_hex} (R,{ch['pan']})"
            
            adj = "YES" if ch["pan_adjusted"] else "no"
            md_lines.append(f"| {ch['name']} | {pan_note} | {adj} | {ch['routing_flag']} | {ch['ch_on']} |\n")
            
        md_lines.extend([
            "\n## Audio Tracks\n",
            "| Track | File | Size (MB) | Peak (dBFS) | >Noise | Action |\n",
            "|---|---|---|---|---|---|\n"
        ])
        
        for track_name, wav_fname in wav_files:
            wav_path = session_dir / wav_fname
            info = probe_wav(str(wav_path))
            
            if not info:
                md_lines.append(f"| {track_name} | {wav_fname} | ? | ? | ? | unreadable |\n")
                continue
                
            mb = info["file_bytes"] / 1_048_576
            peak_str = f"{info['peak_db']:+.1f}"
            pct_str  = f"{info['pct_above_noise']:.1f}%"
            
            # Condition to copy: has audio signal OR has aux sends/pan configured
            chs = [f"CH{i+1:02d}" for i in TRACK_CH_MAP.get(track_name, [])]
            has_aux_or_pan = any(ch in active_channels for ch in chs)
            has_signal = not info["is_empty"]
            
            if has_signal or has_aux_or_pan:
                files_to_copy.append(wav_path)
                action = "COPY"
            else:
                action = "SKIP (empty)"
                
            md_lines.append(f"| {track_name} | {wav_fname} | {mb:.1f} | {peak_str} | {pct_str} | {action} |\n")
            
        # Always copy PRJ and MASTER
        files_to_copy.append(prj_file)
        master_files = list(session_dir.glob("MASTER_01.*"))
        if master_files:
            files_to_copy.append(master_files[0])
            
        # Ensure destination exists
        session_dest = dest_dir / session_name
        
        # Don't copy if source and destination are exactly the same folder (e.g. testing in-place)
        if session_dest.resolve() == session_dir.resolve():
            print(f"  Source and destination are the same ({session_dest}). Writing summary only.")
            summary_path = session_dest / "summary.md"
            summary_path.write_text("".join(md_lines), encoding="utf-8")
        else:
            session_dest.mkdir(parents=True, exist_ok=True)
            
            # Write summary
            summary_path = session_dest / "summary.md"
            summary_path.write_text("".join(md_lines), encoding="utf-8")
            
            # Copy files
            for f in files_to_copy:
                dest_file = session_dest / f.name
                if not dest_file.exists():
                    shutil.copy2(f, dest_file)
                    
    print("Done processing all sessions.")
