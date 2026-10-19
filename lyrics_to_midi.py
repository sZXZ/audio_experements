# %%
import mido
import random
import hashlib

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
    Split a word by syllables: put the whole word first, then add placeholder
    tokens for each additional syllable, placing trailing punctuation on the
    last token. One token per syllable.
    """
    core = word.rstrip('.,-')
    trailing = word[len(core):]
    syll = count_syllables(word)
    if syll <= 1:
        return [word]
    tokens = [core] + [placeholder] * (syll - 1)
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
                 'third_up' (alternates A3 C4), or 'third_down' (alternates C4 A3).
                 In the interval modes, use '+' signs in the lyrics instead of words,
                 e.g. one '+' per note: "+ + + +".
    :param seed: Seed for the random generator (used in 'seeded_random' pitch mode or 'natural' rhythm mode).
    :param beats_per_bar: Number of beats per musical bar (default is 4 for 4/4 time).
    :param split_long_words: If True, words longer than 'split_length' characters are
                             automatically split into 2 or more placeholder notes.
    :param split_length: Target max characters per note when splitting
                         (e.g. 4 -> 'everything' becomes '+ + +').
    :param placeholder: The sign used for split/interval note tokens: '+' or '-'.
                         Note: in natural rhythm mode a lone '-' is a rest, so if you
                         choose '-' as the placeholder, use '.' or ',' for rests instead.
    :param split_by_syllables: If True, split each word into one token per syllable
                               with the whole word first followed by placeholder
                               tokens (e.g. 'Costume' -> ['Costume', '+']).
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

        for word in words:
            # --- 1. Determine the Note based on the selected Mode ---
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

            elif mode in interval_patterns:
                # Alternate between the two notes of the interval:
                note = interval_alt if interval_toggle else interval_start
                interval_toggle = not interval_toggle

            else:
                note = base_note

            # --- 2. Determine Rhythm and Punctuation (Rests) ---
            if rhythm_mode == "natural":
                clean_word = word
                rest_ticks = 0
                # When '-' is the chosen placeholder it marks a note, not a rest,
                # so only '.' and ',' can create rests in that case.
                rest_chars = '.,' if placeholder == '-' else '.,-'
                if word and word[-1] in rest_chars:
                    last_char = word[-1]
                    if last_char == '.':
                        rest_ticks = ppq
                    else:
                        rest_ticks = ppq // 2
                    clean_word = word.rstrip(rest_chars)
                
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
                track.append(mido.MetaMessage('lyrics', text=word, time=next_note_delay))
                track.append(mido.Message('note_on', note=note, velocity=100, time=0))
                track.append(mido.Message('note_off', note=note, velocity=100, time=ticks))
                
                # Update absolute tick time
                total_ticks += next_note_delay + ticks
                
                # Reset next_note_delay for subsequent words in fixed mode
                next_note_delay = 0

            bar_has_notes = True

        # --- 3. Align to Next Bar Boundary ---
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
# Example lyrics (English, Romaji, and Hiragana)
# Each new line represents a new bar. Each space represents a new note.
sample_lyrics = """

"""

print("Generating Single Note MIDI...")
generate_vocaloid_midi(
    lyrics=sample_lyrics, 
    output_file="01_single_note.mid", 
    tempo=120, 
    rhythm="quarter", 
    mode="single"
)

print("Generating Similar Words MIDI...")
generate_vocaloid_midi(
    lyrics=sample_lyrics, 
    output_file="02_similar_words.mid", 
    tempo=120, 
    rhythm="eighth", 
    mode="similar_words"
)

print("Generating Seeded Random MIDI...")
generate_vocaloid_midi(
    lyrics=sample_lyrics, 
    output_file="03_seeded_random.mid", 
    tempo=120, 
    rhythm="eighth", 
    mode="seeded_random",
    seed=101
)

print("Generating Natural Rhythm MIDI...")
generate_vocaloid_midi(
    lyrics=sample_lyrics, 
    output_file="04_natural_rhythm.mid", 
    tempo=80, 
    rhythm_mode="natural", 
    mode="similar_words",
    seed=102
)

print("Generating Natural Rhythm MIDI...")
generate_vocaloid_midi(
    lyrics=sample_lyrics, 
    output_file="04_natural_rhythm_2.mid", 
    tempo=120, 
    rhythm_mode="natural", 
    mode="seeded_random",
    seed=10
)


# %% 
# Example lyrics (English, Romaji, and Hiragana)
# Each new line represents a new bar. Each space represents a new note.
sample_lyrics = """

"""

print("Generating Natural Rhythm MIDI...")
generate_vocaloid_midi(
    lyrics=sample_lyrics, 
    output_file="04_single.mid", 
    tempo=120, 
    rhythm_mode="natural", 
    mode="single",
    seed=0
)

print("Generating Natural Rhythm MIDI...")
generate_vocaloid_midi(
    lyrics=sample_lyrics, 
    output_file="04_natural_rhythm.mid", 
    tempo=120, 
    rhythm_mode="natural", 
    mode="similar_words",
    seed=102
)

print("Generating Natural Rhythm MIDI...")
generate_vocaloid_midi(
    lyrics=sample_lyrics, 
    output_file="04_natural_rhythm_2.mid", 
    tempo=120, 
    rhythm_mode="natural", 
    mode="seeded_random",
    seed=10
)

# %% 
# Fifth-mode variation: alternate C4 <-> G4 (or C4 <-> G3).
# Each '+' is a note placeholder instead of a word; the '+' becomes the lyric text.
fifth_lyrics = """
  Skull -
 Coffin +
 Cobweb +
 Costume +
 Mask -
 Candy +
 Knife +
 Axe +
 Scary +
 Creepy +
"""

print("Generating Fifths Up (C4 G4) MIDI...")
generate_vocaloid_midi(
    lyrics=fifth_lyrics,
    output_file="05_fifth_up.mid",
    tempo=120,
    rhythm="quarter",
    mode="fifth_up"
)

print("Generating Fifths Down (C4 G3) MIDI...")
generate_vocaloid_midi(
    lyrics=fifth_lyrics,
    output_file="05_fifth_down.mid",
    tempo=120,
    rhythm="quarter",
    mode="fifth_down"
)

print("Generating Thirds Up (A3 C4) MIDI...")
generate_vocaloid_midi(
    lyrics=fifth_lyrics,
    output_file="06_third_up.mid",
    tempo=120,
    rhythm="quarter",
    mode="third_up"
)

print("Generating Thirds Down (C4 A3) MIDI...")
generate_vocaloid_midi(
    lyrics=fifth_lyrics,
    output_file="06_third_down.mid",
    tempo=120,
    rhythm="quarter",
    mode="third_down"
)

# %% 
# Auto-split: words longer than 'split_length' characters become 2 or more
# placeholder notes ('+' or '-', set with the 'placeholder' parameter).
# e.g. with split_length=4: 'Costume' -> '+ +', 'everything' -> '+ + +'
split_lyrics = """

"""

print("Generating Auto-Split Long Words MIDI...")
generate_vocaloid_midi(
    lyrics=split_lyrics,
    output_file="07_split_long_words.mid",
    tempo=120,
    rhythm="quarter",
    mode="fifth_up",
    split_long_words=True,
    split_length=4,
    placeholder="+"
)

print("Generating Auto-Split ('-' placeholder, natural rhythm) MIDI...")
generate_vocaloid_midi(
    lyrics=split_lyrics,
    output_file="08_split_long_words_minus.mid",
    tempo=80,
    rhythm_mode="natural",
    mode="third_down",
    split_long_words=True,
    split_length=4,
    placeholder="-"
)