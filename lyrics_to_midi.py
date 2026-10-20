# %%
import mido
import random
import hashlib
import os
import re
import tempfile
from pathlib import Path

def count_syllables(word: str) -> int:
    """
    A simple English syllable counter (heuristic).
    Works for many common words; returns at least 1.
    """
    core = word.lower().rstrip('.,-')
    import re
    core = re.sub(r'[^a-z]', '', core)
    if not core or len(core) <= 3:
        return 1
    vowels = 'aeiouy'
    count = 0
    prev_vowel = False
    for c in core:
        is_v = c in vowels
        if is_v and not prev_vowel:
            count += 1
        prev_vowel = is_v
    # Adjustments
    if core.endswith('e') and count > 1:
        count -= 1
    if core.endswith('le') and len(core) > 2 and core[-3] not in vowels:
        count += 1
    return max(1, count)

def split_word_by_syllables(word: str, placeholder: str = "+") -> list[str]:
    """
    Split a word into one token per syllable.

    The whole (singable) word always comes first, followed by placeholder
    tokens ('+' or '-') for each extra syllable, since a placeholder alone is
    not something we can sing. Trailing punctuation (., -) is kept only on the
    very last token so it still marks a rest in natural rhythm mode.

    Examples (placeholder '+'):
        'rings'      (1 syllable) -> ['rings']
        'Costume,'   (2 syllables) -> ['Costume', '+,']  (or ['Costume', '+,']
        'everything' (4 syllables) -> ['everything', '+', '+', '+']
    """
    syll = count_syllables(word)
    if syll <= 1:
        return [word]
    core = word.rstrip('.,-')
    trailing = word[len(core):]
    tokens = [core] + [placeholder] * (syll - 1)
    if trailing:
        tokens[-1] += trailing
    return tokens
def split_word_into_notes(word: str, max_length: int = 4, placeholder: str = "+"):
    """
    Character-based splitting (backward compatible).
    """
    core = word.rstrip('.,-')
    trailing = word[len(core):]
    max_length = max(1, max_length)
    if len(core) <= max_length:
        return [word]
    parts = max(2, -(-len(core) // max_length))
    tokens = [placeholder] * parts
    tokens[-1] += trailing
    return tokens

# --- Chord vocabulary --------------------------------------------------------
# Chord quality suffixes mapped to semitone offsets from the chord root.
# The suffixes are listed with a 'C' root in the song tags (e.g. '#chord-C^7#11'
# -> '^7#11'), but every chord works with any root: '#chord-Am' is 'm' on A.
CHORD_INTERVALS = {
    # Triads / power chords / basic sevenths
    "":      (0, 4, 7),
    "2":     (0, 2, 7),
    "5":     (0, 7),
    "6":     (0, 4, 7, 9),
    "7":     (0, 4, 7, 10),
    "9":     (0, 2, 4, 7, 10),
    "11":    (0, 2, 4, 5, 7, 10),
    "13":    (0, 2, 4, 7, 9, 10),
    "69":    (0, 2, 4, 7, 9),
    "add9":  (0, 2, 4, 7),
    "o":     (0, 3, 6),
    "h":     (0, 3, 6, 10),
    "sus":   (0, 5, 7),
    "^":     (0, 4, 7, 11),
    "-":     (0, 3, 7),
    "^7":    (0, 4, 7, 11),
    "-7":    (0, 3, 7, 10),
    "7sus":  (0, 5, 7, 10),
    "h7":    (0, 3, 6, 10),
    "o7":    (0, 3, 6, 9),
    "^9":    (0, 2, 4, 7, 11),
    "^13":   (0, 2, 4, 7, 9, 11),
    # Major extensions / alterations
    "^7#11": (0, 4, 6, 7, 11),
    "^9#11": (0, 2, 4, 6, 7, 11),
    "^7#5":  (0, 4, 8, 11),
    # Minor extensions / alterations
    "-6":     (0, 3, 7, 9),
    "-69":    (0, 2, 3, 7, 9),
    "-^7":    (0, 3, 7, 11),
    "-^9":    (0, 2, 3, 7, 11),
    "-9":     (0, 2, 3, 7, 10),
    "-add9":  (0, 2, 3, 7),
    "-11":    (0, 2, 3, 5, 7, 10),
    "-7b5":   (0, 3, 6, 10),
    "h9":     (0, 2, 3, 6, 10),
    "-b6":    (0, 3, 7, 8),
    "-#5":    (0, 3, 8),
    # Dominant extensions / alterations
    "7b9":      (0, 1, 4, 7, 10),
    "7#9":      (0, 3, 4, 7, 10),
    "7#11":     (0, 4, 6, 7, 10),
    "7b5":      (0, 4, 6, 10),
    "7#5":      (0, 4, 8, 10),
    "9#11":     (0, 2, 4, 6, 7, 10),
    "9b5":      (0, 2, 4, 6, 10),
    "9#5":      (0, 2, 4, 8, 10),
    "7b13":     (0, 4, 7, 8, 10),
    "7#9#5":    (0, 3, 4, 8, 10),
    "7#9b5":    (0, 3, 4, 6, 10),
    "7#9#11":   (0, 3, 4, 6, 7, 10),
    "7b9#11":   (0, 1, 4, 6, 7, 10),
    "7b9b5":    (0, 1, 4, 6, 10),
    "7b9#5":    (0, 1, 4, 8, 10),
    "7b9#9":    (0, 1, 3, 4, 7, 10),
    "7b9b13":   (0, 1, 4, 7, 8, 10),
    "7alt":     (0, 1, 3, 4, 6, 8, 10),
    "13#11":    (0, 2, 4, 6, 7, 9, 10),
    "13b9":     (0, 1, 2, 4, 7, 9, 10),
    "13#9":     (0, 2, 3, 4, 7, 9, 10),
    "7b9sus":   (0, 1, 5, 7, 10),
    "7susadd3": (0, 4, 5, 7, 10),
    "9sus":     (0, 2, 5, 7, 10),
    "13sus":    (0, 2, 5, 7, 9, 10),
    "7b13sus":  (0, 5, 7, 8, 10),
    "aug":      (0, 4, 8),
    # Explicit major / minor spellings
    "M":     (0, 4, 7),
    "m":     (0, 3, 7),
    "M7":    (0, 4, 7, 11),
    "m7":    (0, 3, 7, 10),
    "M9":    (0, 2, 4, 7, 11),
    "M13":   (0, 2, 4, 7, 9, 11),
    "M7#11": (0, 4, 6, 7, 11),
    "M9#11": (0, 2, 4, 6, 7, 11),
    "M7#5":  (0, 4, 8, 11),
    "m6":    (0, 3, 7, 9),
    "m69":   (0, 2, 3, 7, 9),
    "m^7":   (0, 3, 7, 11),
    "-M7":   (0, 3, 7, 11),
    "m^9":   (0, 2, 3, 7, 11),
    "-M9":   (0, 2, 3, 7, 11),
    "m9":    (0, 2, 3, 7, 10),
    "madd9": (0, 2, 3, 7),
    "m11":   (0, 2, 3, 5, 7, 10),
    "m7b5":  (0, 3, 6, 10),
    "mb6":   (0, 3, 7, 8),
    "m#5":   (0, 3, 8),
}

_NOTE_PITCH_CLASSES = {
    "C": 0, "C#": 1, "Db": 1, "D": 2, "D#": 3, "Eb": 3, "E": 4,
    "F": 5, "F#": 6, "Gb": 6, "G": 7, "G#": 8, "Ab": 8, "A": 9,
    "A#": 10, "Bb": 10, "B": 11,
}

_CHORD_SYMBOL_RE = re.compile(r'^([A-G][#b]?)(.*)$')


def _parse_chord(symbol):
    """
    Parse a chord symbol such as 'C', 'Am' or 'C^7#11'.

    Returns (root_pitch_class, tuple_of_semitone_offsets) or None when the
    root or the chord quality suffix is unknown.
    """
    match = _CHORD_SYMBOL_RE.match((symbol or "").strip())
    if not match:
        return None
    root, suffix = match.group(1), match.group(2)
    if root not in _NOTE_PITCH_CLASSES or suffix not in CHORD_INTERVALS:
        return None
    return _NOTE_PITCH_CLASSES[root], CHORD_INTERVALS[suffix]


def generate_vocaloid_midi(
    lyrics: str, 
    output_file: str = "openutau_track.mid", 
    tempo: int = 120, 
    rhythm: str = "quarter", 
    rhythm_mode: str = "fixed",
    mode: str = "single", 
    seed: int = 42,
    beats_per_bar: int = 4,
    split_long_words: bool = False,
    split_length: int = 4,
    placeholder: str = "+",
    split_by_syllables: bool = False,
    chord: str = "C",
):
    """
    Converts lyrics into a MIDI file mapped for OpenUtau.
    
    :param lyrics: A string of lyrics (English, Hiragana, or Romaji). Bars separated by new lines.
    :param output_file: Output MIDI file name.
    :param tempo: Tempo in BPM.
    :param rhythm: Note duration ('whole', 'half', 'quarter', 'eighth', 'sixteenth') used in fixed mode.
    :param rhythm_mode: Rhythm mapping mode ('fixed' or 'natural').
    :param mode: 'single', 'similar_words', 'seeded_random',
                 'fifth_up' (alternates C4 G4), 'fifth_down' (alternates C4 G3),
                 'third_up' (alternates A3 C4), 'third_down' (alternates C4 A3),
                 or 'arp' (arpeggiates the current chord, one chord tone per note).
                 In the interval modes, use '+' signs in the lyrics instead of words,
                 e.g. one '+' per note: "+ + + +".
    :param seed: Seed for the random generator (used in 'seeded_random' pitch mode or 'natural' rhythm mode).
    :param beats_per_bar: Number of beats per musical bar (default is 4 for 4/4 time).
    :param split_long_words: If True, words longer than 'split_length' characters are
                             automatically split into 2 or more placeholder notes.
    :param split_length: Target max characters per note when splitting
                         (e.g. 4 -> 'everything' becomes 'everything + +').
    :param placeholder: The sign used for split/interval note tokens: '+' or '-'.
                         Note: in natural rhythm mode a lone '-' is a rest, so if you
                         choose '-' as the placeholder, use '.' or ',' for rests instead.
    :param split_by_syllables: If True, split each word into one token per syllable
                               with the whole word first followed by placeholder
                               tokens (e.g. 'Costume' -> ['Costume', '+']).
    :param chord: Chord symbol of this section (e.g. 'C', 'Am', 'C^7#11').
                  Exactly one note per bar - the first one - is anchored to the
                  chord root so every bar starts in key; all other notes follow
                  the selected mode. Mode 'arp' cycles through the tones of this
                  chord. Unknown or missing chords fall back to 'C'.
    """
    
    # Standard MIDI resolution (Ticks Per Quarter Note)
    ppq = 480  
    
    # Map rhythm strings to MIDI tick durations
    rhythm_map = {
        "whole": ppq * 4,
        "half": ppq * 2,
        "quarter": ppq,
        "eighth": ppq // 2,
        "sixteenth": ppq // 4
    }
    
    # Default to quarter notes if an invalid rhythm is passed
    ticks = rhythm_map.get(rhythm.lower(), ppq)

    # Initialize MIDI file and Track
    mid = mido.MidiFile(ticks_per_beat=ppq)
    track = mido.MidiTrack()
    mid.tracks.append(track)

    # Set Tempo
    track.append(mido.MetaMessage('set_tempo', tempo=mido.bpm2tempo(tempo), time=0))

    # Initialize Seed for Pure Random Mode or Humanization
    if mode == "seeded_random" or rhythm_mode == "natural":
        random.seed(seed)

    # Vocal Range settings (C4 = 60 to B4 = 71)
    base_note = 60
    range_notes = 12

    # Split the lyrics into bars (lines)
    bars = lyrics.strip().split('\n')

    # Initialize timing offset for rests and bar alignment
    next_note_delay = 0
    total_ticks = 0
    bar_ticks = ppq * beats_per_bar

    # Interval-mode state: alternate between a start note and a second note.
    # 'fifth_up':   C4 (60) G4 (67), starting on C4 going up
    # 'fifth_down': C4 (60) G3 (55), starting on C4 going down
    # 'third_up':   A3 (57) C4 (60), starting on A3 going up
    # 'third_down': C4 (60) A3 (57), starting on C4 going down
    interval_patterns = {
        "fifth_up":   (60, 67),
        "fifth_down": (60, 55),
        "third_up":   (57, 60),
        "third_down": (60, 57),
    }
    interval_start, interval_alt = interval_patterns.get(mode, (base_note, base_note))
    interval_toggle = False

    # --- Chord state --------------------------------------------------------
    # The chord anchors exactly one note per bar - the first one - to the chord
    # root, so every bar starts in key. Everything else is left to the mode.
    # Mode 'arp' walks through the chord tones of this chord instead.
    parsed_chord = _parse_chord(chord)
    if parsed_chord is None:
        print(f"  Unknown chord '{chord}' - using 'C'.")
        parsed_chord = _parse_chord("C")
    chord_root, chord_intervals = parsed_chord

    # Chord root inside the vocal range: C4 (60) .. B4 (71).
    chord_root_note = base_note + chord_root

    # Arpeggio notes for mode 'arp': the chord tones of one octave starting on
    # the root, folded back into the vocal range (60..71) when they go above it,
    # so the sequence always starts on the root and stays singable.
    arp_notes = []
    for offset in chord_intervals:
        arp_note = chord_root_note + offset
        while arp_note > 71:
            arp_note -= 12
        arp_notes.append(arp_note)

    # Per-bar pitch state (reset at the start of every bar below).
    arp_index = 0
    bar_first_note = True

    def _pick_note(word: str) -> int:
        """
        Pick the pitch for the next note that is actually written.

        The first note of a bar is forced onto the chord root ('in key');
        every following note is chosen by the selected mode.
        """
        nonlocal interval_toggle, arp_index, bar_first_note

        if mode == "single":
            # Monotone pitch (C4)
            note = base_note

        elif mode == "similar_words":
            # Hash the string so the same word always gets the exact same note
            # e.g., every "la" gets D4, every "mi" gets E4
            word_hash = int(hashlib.md5(word.encode('utf-8')).hexdigest(), 16)
            note = base_note + (word_hash % range_notes)

        elif mode == "seeded_random":
            # Pure randomized note within the octave
            note = base_note + random.randint(0, range_notes - 1)

        elif mode == "arp":
            # Cycle through the tones of the current chord, starting on the root
            note = arp_notes[arp_index % len(arp_notes)]
            arp_index += 1

        elif mode in interval_patterns:
            # Alternate between the two notes of the interval:
            note = interval_alt if interval_toggle else interval_start
            interval_toggle = not interval_toggle

        else:
            note = base_note

        if bar_first_note:
            # One note per bar (the first) is anchored to the chord root.
            note = chord_root_note
            bar_first_note = False

        return note

    for bar in bars:
        # Split each bar by spaces to isolate individual words/syllables
        words = bar.strip().split()
        if not words:
            continue

        # Optionally split long words into 2 or more placeholder notes,
        # e.g. with split_length=4: "everything" -> '+ + +' (sung across 3 notes)
        if split_by_syllables:
            words = [
                token
                for word in words
                for token in split_word_by_syllables(word, placeholder)
            ]
        elif split_long_words:
            words = [
                token
                for word in words
                for token in split_word_into_notes(word, split_length, placeholder)
            ]

        bar_has_notes = False
        # A new bar restarts the chord anchor and the arpeggio on the root.
        bar_first_note = True
        arp_index = 0

        for word in words:
            # --- 1. Determine Rhythm and Punctuation (Rests) ---
            if rhythm_mode == "natural":
                clean_word = word
                rest_ticks = 0

                # A placeholder token ('+' or '-') is a note we intend to sing,
                # so it must never be swallowed as a rest.
                is_placeholder_token = bool(word) and word[0] == placeholder and all(
                    c == placeholder or c in '.,-' for c in word
                )
                if not is_placeholder_token and word and word[-1] in '.,-':
                    last_char = word[-1]
                    if last_char == '.':
                        rest_ticks = ppq
                    else:
                        rest_ticks = ppq // 2
                    clean_word = word.rstrip('.,-')
                
                # If the word was entirely punctuation, accumulate the rest duration and skip note creation
                if not clean_word:
                    next_note_delay += rest_ticks
                    continue
                
                # Map length of the clean word/syllable
                clean_len = len(clean_word)
                if clean_len <= 2:
                    note_duration = rhythm_map["eighth"]
                elif clean_len <= 4:
                    note_duration = rhythm_map["quarter"]
                else:
                    note_duration = rhythm_map["half"]
                
                # Humanization: add randomization to the note duration (+/- 10 ticks)
                random_offset = random.randint(-10, 10)
                note_duration = max(1, note_duration + random_offset)
                
                # Write events: Lyric and Note On start at next_note_delay
                note = _pick_note(word)
                track.append(mido.MetaMessage('lyrics', text=clean_word, time=next_note_delay))
                track.append(mido.Message('note_on', note=note, velocity=100, time=0))
                
                # Note Off ends after note_duration
                track.append(mido.Message('note_off', note=note, velocity=100, time=note_duration))
                
                # Update absolute tick time
                total_ticks += next_note_delay + note_duration
                
                # The next note starts after the rest ticks (if any)
                next_note_delay = rest_ticks
            else:
                # Fixed mode
                note = _pick_note(word)
                track.append(mido.MetaMessage('lyrics', text=word, time=next_note_delay))
                track.append(mido.Message('note_on', note=note, velocity=100, time=0))
                track.append(mido.Message('note_off', note=note, velocity=100, time=ticks))
                
                # Update absolute tick time
                total_ticks += next_note_delay + ticks
                
                # Reset next_note_delay for subsequent words in fixed mode
                next_note_delay = 0

            bar_has_notes = True

        # --- 2. Align to Next Bar Boundary ---
        if bar_has_notes:
            bar_end_ticks = total_ticks + next_note_delay
            next_bar_ticks = ((bar_end_ticks + bar_ticks - 1) // bar_ticks) * bar_ticks
            padding = next_bar_ticks - bar_end_ticks
            next_note_delay += padding
            total_ticks = next_bar_ticks - next_note_delay

    # Save out the generated sequence
    mid.save(output_file)
    print(f"Success! MIDI saved to '{output_file}'.")

# %% 
# --- Obsidian song processing ------------------------------------------------
# Every .md file in the Songs folder describes exactly one MIDI file.
# '#' tag lines (e.g. #tempo-120, #rythm-natural, #mode-similar_words,
# #mode-arp, #chord-C, #chord-Am, #seed-102, #split_by_syllables) configure
# generate_vocaloid_midi() and are removed from the lyrics. '#chord-X' sets the
# chord of the section: its root is the one note per bar that always stays in
# key, and mode 'arp' arpeggiates its tones (default chord when the tag is
# missing: C). A tag block in the middle of the lyrics starts a
# new section with the updated settings (earlier settings carry over); all
# sections are merged into a single .mid file written next to the .md file.

SONG_TAG_RE = re.compile(r'^#([A-Za-z_][A-Za-z0-9_]*)(?:-(.*))?$')

SONG_DEFAULT_SETTINGS = {
    "tempo": 120,
    "rhythm": "quarter",
    "rhythm_mode": "fixed",
    "mode": "single",
    "seed": 42,
    "beats_per_bar": 4,
    "split_long_words": False,
    "split_length": 4,
    "placeholder": "+",
    "split_by_syllables": False,
    "chord": "C",
}

_SONG_RHYTHMS = ("whole", "half", "quarter", "eighth", "sixteenth")
_SONG_RHYTHM_MODES = ("fixed", "natural")
_SONG_MODES = (
    "single", "similar_words", "seeded_random",
    "fifth_up", "fifth_down", "third_up", "third_down",
    "arp",
)
_SONG_INT_SETTINGS = ("tempo", "seed", "beats_per_bar", "split_length")
_SONG_BOOL_SETTINGS = ("split_long_words", "split_by_syllables")


def _apply_song_tag(settings: dict, key: str, value: str = None) -> None:
    """
    Apply one '#tag' (or '#tag-value') to the settings dict in place.
    """
    key = {"rythm": "rhythm"}.get(key, key)  # accept the common typo

    if key not in SONG_DEFAULT_SETTINGS:
        print(f"  Unknown tag '#{key}' - ignored.")
        return

    # Bare flags like '#split_by_syllables' turn a boolean setting on.
    if key in _SONG_BOOL_SETTINGS:
        if value is None:
            settings[key] = True
        else:
            settings[key] = value.strip().lower() not in ("false", "no", "0")
        return

    if value is None:
        print(f"  Tag '#{key}' is missing a value - ignored.")
        return
    value = value.strip()

    if key in _SONG_INT_SETTINGS:
        try:
            settings[key] = int(value)
        except ValueError:
            print(f"  Tag '#{key}-{value}' is not a number - ignored.")
        return

    # '#chord-C', '#chord-Am', '#chord-C^7#11', ... select the chord of the
    # section: it anchors the first note of every bar and feeds mode 'arp'.
    if key == "chord":
        if _parse_chord(value) is None:
            print(f"  Unknown chord '{value}' - ignored.")
            return
        settings[key] = value
        return

    # '#rythm-natural' / '#rythm-fixed' set rhythm_mode, e.g. '#rythm-quarter'
    # (whole/half/quarter/eighth/sixteenth) sets the fixed-note rhythm.
    if key == "rhythm" and value in _SONG_RHYTHM_MODES:
        settings["rhythm_mode"] = value
        return
    if key == "rhythm" and value not in _SONG_RHYTHMS:
        print(f"  Unknown rhythm '{value}' - ignored.")
        return
    if key == "rhythm_mode" and value not in _SONG_RHYTHM_MODES:
        print(f"  Unknown rhythm_mode '{value}' - ignored.")
        return
    if key == "mode" and value not in _SONG_MODES:
        print(f"  Unknown mode '{value}' - ignored.")
        return

    settings[key] = value


def _parse_song_sections(text: str) -> list:
    """
    Split md text into a list of (lyric_lines, settings) sections.

    Tag lines are stripped from the lyrics. Settings accumulate, so a tag
    block only affects the lyrics that follow it.
    """
    settings = dict(SONG_DEFAULT_SETTINGS)
    sections = []
    current_lines = []

    for line in text.splitlines():
        match = SONG_TAG_RE.match(line.strip())
        if match:
            if any(l.strip() for l in current_lines):
                sections.append((current_lines, dict(settings)))
                current_lines = []
            _apply_song_tag(settings, match.group(1), match.group(2))
        else:
            current_lines.append(line)

    if any(l.strip() for l in current_lines):
        sections.append((current_lines, dict(settings)))

    return sections


def _generate_song_midi(sections: list, output_file: Path) -> None:
    """
    Generate the sections and merge them into a single midi file.
    A single-section song is generated directly (no merging needed).
    """
    if len(sections) == 1:
        lines, settings = sections[0]
        generate_vocaloid_midi(
            lyrics="\n".join(lines),
            output_file=str(output_file),
            **settings,
        )
        return

    ppq = 480
    merged = mido.MidiFile(ticks_per_beat=ppq)
    merged_track = mido.MidiTrack()
    merged.tracks.append(merged_track)

    for index, (lines, settings) in enumerate(sections):
        # Pad the junction to the next bar boundary of the upcoming section's
        # grid, so its internal bar alignment stays valid in the merged file.
        pad = 0
        if index > 0:
            bar_ticks = ppq * settings["beats_per_bar"]
            written = sum(msg.time for msg in merged_track)
            pad = (bar_ticks - (written % bar_ticks)) % bar_ticks

        with tempfile.NamedTemporaryFile(suffix=".mid", delete=False) as tmp:
            tmp_path = tmp.name
        try:
            generate_vocaloid_midi(
                lyrics="\n".join(lines),
                output_file=tmp_path,
                **settings,
            )
            section = mido.MidiFile(tmp_path)
        finally:
            os.remove(tmp_path)

        for i, msg in enumerate(section.tracks[0]):
            if i == 0:  # the section's 'set_tempo' carries the junction pad
                msg = msg.copy(time=msg.time + pad)
            merged_track.append(msg)

    merged.save(str(output_file))
    print(f"Success! MIDI saved to '{output_file}'.")


def process_songs(path: str = "/Users/alex/Documents/Music/Songs") -> list:
    """
    Generate one .mid file per .md file found in 'path'.

    Each song's '#' tags configure the generator; output is written next to
    the .md file (same name, '.mid' extension), replacing existing files.
    Returns the list of created midi file paths.
    """
    outputs = []
    for md_file in sorted(Path(path).glob("*.md")):
        print(f"Processing '{md_file.name}'...")
        sections = _parse_song_sections(md_file.read_text(encoding="utf-8"))
        if not sections:
            print("  No lyrics found - skipped.")
            continue
        output_file = md_file.with_suffix(".mid")
        _generate_song_midi(sections, output_file)
        outputs.append(str(output_file))
    return outputs


process_songs()