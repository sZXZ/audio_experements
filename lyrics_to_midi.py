# %%
import mido
import random
import hashlib

def generate_vocaloid_midi(
    lyrics: str, 
    output_file: str = "openutau_track.mid", 
    tempo: int = 120, 
    rhythm: str = "quarter", 
    rhythm_mode: str = "fixed",
    mode: str = "single", 
    seed: int = 42
):
    """
    Converts lyrics into a MIDI file mapped for OpenUtau.
    
    :param lyrics: A string of lyrics (English, Hiragana, or Romaji). Bars separated by new lines.
    :param output_file: Output MIDI file name.
    :param tempo: Tempo in BPM.
    :param rhythm: Note duration ('whole', 'half', 'quarter', 'eighth', 'sixteenth') used in fixed mode.
    :param rhythm_mode: Rhythm mapping mode ('fixed' or 'natural').
    :param mode: 'single', 'similar_words', or 'seeded_random'.
    :param seed: Seed for the random generator (used in 'seeded_random' pitch mode or 'natural' rhythm mode).
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

    # Initialize timing offset for rests
    next_note_delay = 0

    for bar in bars:
        # Split each bar by spaces to isolate individual words/syllables
        words = bar.strip().split()
        if not words:
            continue

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
                
            else:
                note = base_note

            # --- 2. Determine Rhythm and Punctuation (Rests) ---
            if rhythm_mode == "natural":
                clean_word = word
                rest_ticks = 0
                if word and word[-1] in ('.', ',', '-'):
                    last_char = word[-1]
                    if last_char == '.':
                        rest_ticks = ppq
                    elif last_char == ',':
                        rest_ticks = ppq // 2
                    elif last_char == '-':
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
                track.append(mido.MetaMessage('lyrics', text=clean_word, time=next_note_delay))
                track.append(mido.Message('note_on', note=note, velocity=100, time=0))
                
                # Note Off ends after note_duration
                track.append(mido.Message('note_off', note=note, velocity=100, time=note_duration))
                
                # The next note starts after the rest ticks (if any)
                next_note_delay = rest_ticks
            else:
                # Fixed mode
                track.append(mido.MetaMessage('lyrics', text=word, time=0))
                track.append(mido.Message('note_on', note=note, velocity=100, time=0))
                track.append(mido.Message('note_off', note=note, velocity=100, time=ticks))

    # Save out the generated sequence
    mid.save(output_file)
    print(f"Success! MIDI saved to '{output_file}'.")

# %% 
# Example lyrics (English, Romaji, and Hiragana)
# Each new line represents a new bar. Each space represents a new note.
sample_lyrics = """
You're the kind of girl,
that fits in with my world.  
I'll give you- anything, everything
if you want things.
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