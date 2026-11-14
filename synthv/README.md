# Lyrics to Notes for Synthesizer V Studio

A Lua port of [`lyrics_to_midi.py`](../lyrics_to_midi.py). It turns lyric text
into a block of notes on a new note group and places that group at the playhead
on the current track (or on a new track).

The script uses a persistent **side panel UI**. Panel settings are saved inside
the project file, so they are restored when the project is reopened.

The script is intentionally a single file: Synthesizer V scripts are loaded
standalone, so `require` and multi-file layouts are avoided.

**Requires Synthesizer V Studio 2.1.2 or newer.**

## Installation

1. In Synthesizer V Studio, choose **Scripts > Open Scripts Folder**.
2. Copy `lyrics_to_notes.lua` into that folder.
3. Choose **Scripts > Rescan**.
4. Open the **Script Panel** from the sidebar. The **Lyrics to Notes** panel
   appears there (side panel scripts are not run from the Scripts menu).

The usual user script folder is:

- macOS: `~/Library/Application Support/Dreamtonics/Synthesizer V Studio/scripts/`
- Windows: `%APPDATA%\Dreamtonics\Synthesizer V Studio\scripts/`

## Usage

1. Put the playhead where the generated phrase should start.
2. Open the **Lyrics to Notes** panel in the Script Panel.
3. Paste or type lyrics, adjust the options, then click **Generate at Playhead**.

The generated notes are added as a new note group. Existing notes are never
modified. Tick **Create a new track** to put the group on a new track instead of
the current one; the current group's voice is copied to the new track when
possible. There is no completion popup: progress is shown in the panel's
**Status** field, and warnings are printed to the script console.

The first time the panel opens in a project, the lyric box is pre-filled from
the clipboard if the clipboard is not empty.

### Saved state

Panel options and lyrics are stored in the project using
`Project:setScriptData` and are written to the project file when it is saved.
Reopening the project restores the panel exactly as you left it. The generated
note group stores its generation settings too, so the settings travel with the
group when it is copied to another project.

**Reset Options** restores the default settings but keeps the current lyrics.

## Lyric input

- Each non-empty line is one musical bar.
- Blank lines separate blocks but do not create sections.
- In **fixed** rhythm mode every word/syllable gets the selected rhythm value.
- In **natural** rhythm mode note lengths follow word length (roughly eighth,
  quarter, half), with a small deterministic humanization.
- A word ending in `.` or `,` produces a short rest after its note. A trailing
  `-` behaves the same way unless `-` is selected as the split token.
- Lines starting with `#tag` (and containing only tags) are configuration, not
  lyrics. They start a new section; see below.

### Placeholders

Synthesizer V uses two special lyrics:

- `+` splits the previous word into another syllable.
- `-` continues the previous note's pronunciation.

The **Split / continuation token** option controls which character is emitted
for generated syllable splits (default `+`). Placeholder tokens followed by
punctuation (`+,`, `+.`) are normalized to the bare token so Synthesizer V
interprets them correctly, and the punctuation becomes a rest.

**Split words by syllable** splits a word into its first syllable plus one
placeholder per extra syllable. This is usually the best option for
Synthesizer V because the placeholders become additional syllables of the same
word.

**Split long words** mirrors the Python behavior: words longer than the split
length become a series of placeholder tokens. That behavior is useful for the
original MIDI workflow, but in Synthesizer V a run of bare `+` tokens is rarely
what you want. Prefer **Split words by syllable**.

## Options

| Option | Default | Meaning |
| --- | --- | --- |
| Pitch mode | `single` | Melody/pitch generation mode (see below). |
| Rhythm mode | `fixed` | `fixed` or `natural`. |
| Fixed rhythm | `quarter` | Whole, half, quarter, eighth, or sixteenth. |
| Chord | `C` | Root plus chord quality, e.g. `Am`, `C^7#11`, `Bb-7`. |
| Beats per bar | `4` | Bar grid used to align each lyric line. |
| Split words by syllable | off | Emit `+` per extra syllable. |
| Split long words | off | Emit placeholder notes for long words. |
| Long-word split length | `4` | Character threshold for long-word splitting. |
| Note length divisor | `1` | `2` halves every note duration. |
| Gap after each note | `0` | Beats after each note (slider); tags also accept a rhythm name such as `eighth`. |
| Timeline divisor | `1` | `2` halves the total timeline (notes and bar grid). |
| Random seed | `42` | Seed for `seeded_random` and natural humanization. |
| Split / continuation token | `+` | `+` or `-`. |
| Create a new track | off | Add a track and place the group there. |

`Note length divisor` and `Timeline divisor` compose: the first shortens notes
inside their slots, the second compresses the whole generated section.

In fixed mode, a gap shortens the sounding note and leaves silence before the
next one. In natural mode, the note keeps its duration and the gap is added
after it.

## Pitch modes

| Mode | Behavior |
| --- | --- |
| `single` | Middle C for every note. |
| `similar_words` | Hashes each word to a pitch in the octave starting at middle C; the same word always gets the same pitch. |
| `seeded_random` | Reproducible pseudo-random pitch in that octave. |
| `fifth_up` / `fifth_down` | Alternates C4 with G4 / G3. |
| `third_up` / `third_down` | Alternates A3/C4 or C4/A3. |
| `arp` | Walks the chord tones in order, restarting on each bar. |

The first note of every bar is the chord root. Pitches are clamped to the MIDI
range used by the Python original.

### Chords

Roots support `#`/`b` accidentals: `C`, `F#`, `Bb`, etc. Supported qualities
include the common triad, sixth, seventh, ninth, eleventh, thirteenth,
suspended, diminished, augmented, altered, and `M`/`m` spellings listed in
`CHORD_INTERVALS` in the script, for example:

```
C   Cm   C7   C^7   C-7   Cm7b5   C7alt   C13#11   Csus   Caug
```

Unknown chords produce a warning and fall back to `C`.

## Tags

A line consisting only of `#tag` tokens changes settings for the following
lyrics. Tags can be stacked on one line or spread across several lines.

```text
#mode-arp #chord-Am #rhythm-eighth #beats-per-bar-3
you can dance
you can jive
```

Supported tags, with underscore and hyphen forms both accepted:

```
#tempo-120            (parsed but ignored; see below)
#mode-single          #mode-similar_words     #mode-seeded_random
#mode-fifth_up        #mode-fifth_down        #mode-third_up
#mode-third_down      #mode-arp
#rhythm_mode-fixed    #rhythm-mode-natural    #rythm-natural
#rhythm-quarter       #rhythm-eighth          #rhythm-sixteenth
#chord-Am             #beats-per-bar-3
#split-by-syllables   #split-long-words
#split-length-4
#note-length-2        #gap-eighth            #gap-0.25
#scale-2              #seed-7
```

Boolean tags can be written bare (`#split-by-syllables` enables it) or with a
value (`#split-by-syllables-0` disables it; `false`, `no`, and `0` also
disable).

### Multiple sections

Tags split the text into sections. Each section starts its own bar grid and can
use entirely different settings. Later sections are aligned so they begin on
the next bar boundary after the previous section, matching the Python script.

```text
#mode-single #chord-C
la la la la

#mode-arp #chord-Am #rhythm-eighth
do re mi fa sol la ti do
```

## Tempo

`#tempo-*` tags are parsed for compatibility with the Python input format, but
they do not change the project tempo. Playback tempo in Synthesizer V is
controlled by the project, so set it there.

## Differences from `lyrics_to_midi.py`

The note generation, rhythms, chords, splitting, tag parsing, and multi-section
alignment are ported directly. Remaining differences are deliberate:

- **Output target:** notes are written into Synthesizer V rather than a `.mid`
  file. The group is placed at the playhead instead of starting at time zero.
- **Tempo tags:** ignored; the project tempo is used.
- **`similar_words` hash:** Python uses MD5, which Lua does not expose; this
  port uses deterministic djb2. Results are stable per word but the pitch
  mapping differs from the Python output.
- **Randomness:** Python's Mersenne Twister is replaced by a deterministic
  Park–Miller LCG. `seeded_random` is reproducible, but its sequence differs
  from Python's.
- **Placeholder punctuation:** `+,` becomes the bare `+` plus a rest, because
  Synthesizer V requires a bare token. The Python version leaves the comma on
  the lyric.
- **`split_long_words`:** preserved for parity, but it produces only placeholder
  tokens. Use `split_by_syllables` for musical results in Synthesizer V.
- **Rounding:** Python-style half-to-even rounding is implemented for timing
  fidelity.
- **No file discovery:** unlike the Python script's `process_songs()` batch
  mode, this script only processes text entered in (or pasted into) the panel.
- **UI and state:** the Python script is command-line/batch oriented. This port
  adds a persistent side panel and stores panel settings in the project file.

## Development notes

- `luajit` is a convenient syntax check: `luajit -bl synthv/lyrics_to_notes.lua /dev/null`.
- The file exposes a `LyricsToNotes` table (`generate_song`,
  `parse_song_sections`, `parse_chord`, etc.) so the generator can be tested
  outside Synthesizer V. The host calls `getClientInfo()` and
  `getSidePanelSectionState()`, then invokes widget callbacks.
- Panel state is stored under the project script-data key
  `lyrics_to_notes.settings`. Generated note groups store their settings under
  the group script-data key `lyrics_to_notes`.
- The internal grid is 480 ticks per quarter note and is converted to
  Synthesizer V blicks with `SV.QUARTER / 480`.
