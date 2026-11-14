-- Lyrics to Notes for Synthesizer V Studio
--
-- Lua port of ../lyrics_to_midi.py.  Instead of writing a MIDI file it creates
-- a NoteGroup and places it at the playhead on the current track (or on a new
-- track).  Paste the same lyric text you would put in an Obsidian song file;
-- the generator's #tags are supported and override the dialog defaults.
--
-- The musical generation is done in 480 ticks per quarter note, exactly like
-- the Python version, and converted to Synthesizer V blicks when the notes are
-- created.  Tempo tags are parsed but not applied: playback always follows the
-- project tempo.

local PPQ = 480
local BASE_NOTE = 60
local RANGE_NOTES = 12
local HIGHEST_NOTE = 71

local RHYTHM_TICKS = {
  whole = PPQ * 4,
  half = PPQ * 2,
  quarter = PPQ,
  eighth = PPQ / 2,
  sixteenth = PPQ / 4,
}

local RHYTHM_BEATS = {
  whole = 4.0,
  half = 2.0,
  quarter = 1.0,
  eighth = 0.5,
  sixteenth = 0.25,
}

local RHYTHM_CHOICES = {"whole", "half", "quarter", "eighth", "sixteenth"}
local RHYTHM_MODE_CHOICES = {"fixed", "natural"}
local MODE_CHOICES = {
  "single", "similar_words", "seeded_random",
  "fifth_up", "fifth_down", "third_up", "third_down", "arp",
}
local PLACEHOLDER_CHOICES = {"+", "-"}

local DEFAULT_SETTINGS = {
  tempo = 120,
  rhythm = "quarter",
  rhythm_mode = "fixed",
  mode = "single",
  seed = 42,
  beats_per_bar = 4,
  split_long_words = false,
  split_length = 4,
  placeholder = "+",
  split_by_syllables = false,
  chord = "C",
  note_length = 1.0,
  gap = 0.0,
  scale = 1.0,
}

local INT_SETTINGS = {
  tempo = true,
  seed = true,
  beats_per_bar = true,
  split_length = true,
}

local BOOL_SETTINGS = {
  split_long_words = true,
  split_by_syllables = true,
}

local RHYTHM_SET = {}
for _, name in ipairs(RHYTHM_CHOICES) do RHYTHM_SET[name] = true end
local RHYTHM_MODE_SET = {}
for _, name in ipairs(RHYTHM_MODE_CHOICES) do RHYTHM_MODE_SET[name] = true end
local MODE_SET = {}
for _, name in ipairs(MODE_CHOICES) do MODE_SET[name] = true end

-- --- Utility ----------------------------------------------------------------

local function trim(s)
  return (tostring(s):gsub("^%s+", ""):gsub("%s+$", ""))
end

local function split_lines(text)
  text = tostring(text):gsub("\r\n", "\n"):gsub("\r", "\n")
  local lines = {}
  if text == "" then return lines end
  local pos = 1
  while true do
    local nl = text:find("\n", pos, true)
    if nl then
      lines[#lines + 1] = text:sub(pos, nl - 1)
      pos = nl + 1
      if pos > #text then break end
    else
      lines[#lines + 1] = text:sub(pos)
      break
    end
  end
  return lines
end

local function split_whitespace(s)
  local out = {}
  for tok in tostring(s):gmatch("%S+") do
    out[#out + 1] = tok
  end
  return out
end

local function strip_trailing_punct(s)
  return (tostring(s):gsub("[%.,%-]+$", ""))
end

-- Strip punctuation from a placeholder token without stripping the
-- placeholder itself.  With the '-' token, '-' is a placeholder, not a rest.
local function strip_placeholder_trailing(word, placeholder)
  local i = #word
  while i >= 1 do
    local c = word:sub(i, i)
    if c == "." or c == "," or (c == "-" and placeholder ~= "-") then
      i = i - 1
    else
      break
    end
  end
  return word:sub(1, i)
end

local function utf8_len(s)
  local count, i, n = 0, 1, #s
  while i <= n do
    local b = s:byte(i)
    local step = 1
    if b >= 240 then
      step = 4
    elseif b >= 224 then
      step = 3
    elseif b >= 192 then
      step = 2
    end
    count = count + 1
    i = i + step
  end
  return count
end

-- Python's round() rounds halves to even.  The Python generator uses
-- int(round(...)) for note lengths and for scaling the finished timeline.
local function pyround(x)
  local f = math.floor(x)
  local diff = x - f
  if diff > 0.5 then
    return f + 1
  elseif diff < 0.5 then
    return f
  end
  if f % 2 == 0 then
    return f
  end
  return f + 1
end

local function parse_int_string(s)
  s = trim(s)
  if not s:match("^[+-]?%d+$") then return nil end
  return tonumber(s)
end

local function parse_float_string(s)
  s = trim(s)
  local n = tonumber(s)
  if n == nil or n ~= n or n == math.huge or n == -math.huge then
    return nil
  end
  return n
end

local function add_warning(warnings, msg)
  for _, existing in ipairs(warnings) do
    if existing == msg then return end
  end
  warnings[#warnings + 1] = msg
end

local function copy_table(t)
  local out = {}
  for k, v in pairs(t) do out[k] = v end
  return out
end

local function make_settings(base)
  local settings = copy_table(DEFAULT_SETTINGS)
  if base then
    for k, v in pairs(base) do
      if DEFAULT_SETTINGS[k] ~= nil then settings[k] = v end
    end
  end
  return settings
end

-- --- Lyrics helpers ---------------------------------------------------------

local function count_syllables(word)
  local core = tostring(word):lower():gsub("[%.,%-]+$", "")
  core = core:gsub("[^a-z]", "")
  if core == "" or #core <= 3 then return 1 end

  local vowels = "aeiouy"
  local count = 0
  local prev_vowel = false
  for i = 1, #core do
    local is_vowel = vowels:find(core:sub(i, i), 1, true) ~= nil
    if is_vowel and not prev_vowel then count = count + 1 end
    prev_vowel = is_vowel
  end

  if core:sub(-1) == "e" and count > 1 then count = count - 1 end
  if core:sub(-2) == "le" and #core > 2
      and vowels:find(core:sub(-3, -3), 1, true) == nil then
    count = count + 1
  end
  if count < 1 then count = 1 end
  return count
end

local function split_word_by_syllables(word, placeholder)
  local syll = count_syllables(word)
  if syll <= 1 then return {word} end

  local core = strip_trailing_punct(word)
  local trailing = word:sub(#core + 1)
  local tokens = {core}
  for i = 2, syll do tokens[i] = placeholder end
  if trailing ~= "" then
    tokens[#tokens] = tokens[#tokens] .. trailing
  end
  return tokens
end

local function split_word_into_notes(word, max_length, placeholder)
  local core = strip_trailing_punct(word)
  local trailing = word:sub(#core + 1)
  max_length = math.max(1, math.floor(tonumber(max_length) or 4))
  local core_len = utf8_len(core)
  if core_len <= max_length then return {word} end

  local parts = math.max(2, math.floor((core_len + max_length - 1) / max_length))
  local tokens = {}
  for i = 1, parts do tokens[i] = placeholder end
  tokens[#tokens] = tokens[#tokens] .. trailing
  return tokens
end

local function is_placeholder_token(word, placeholder)
  if word == nil or word == "" or word:sub(1, 1) ~= placeholder then
    return false
  end
  for i = 1, #word do
    local c = word:sub(i, i)
    if c ~= placeholder and c ~= "." and c ~= "," and c ~= "-" then
      return false
    end
  end
  return true
end

local function prepare_natural_word(word, placeholder)
  local lyric, rest_ticks, length_source = word, 0, word
  local placeholder_token = is_placeholder_token(word, placeholder)

  if placeholder_token then
    -- The Python version leaves punctuation on placeholder tokens ("+,").
    -- Synthesizer V needs a bare "+" (split syllable) or "-" (continue), so
    -- keep the token and turn its trailing punctuation into a rest.
    local stripped = strip_placeholder_trailing(word, placeholder)
    if stripped ~= word then
      local last = word:sub(-1)
      rest_ticks = (last == ".") and PPQ or math.floor(PPQ / 2)
      lyric = stripped
    end
  elseif word ~= "" and word:sub(-1):match("[%.,%-]") then
    local last = word:sub(-1)
    rest_ticks = (last == ".") and PPQ or math.floor(PPQ / 2)
    lyric = strip_trailing_punct(word)
    length_source = lyric
  end

  if lyric == "" then return nil, rest_ticks end
  return lyric, rest_ticks, length_source
end

local function prepare_fixed_word(word, placeholder)
  -- Only placeholder tokens need normalizing for Synthesizer V: "+," would
  -- otherwise be interpreted as a lyric instead of a syllable split.
  if is_placeholder_token(word, placeholder) then
    local stripped = strip_placeholder_trailing(word, placeholder)
    if stripped ~= "" then return stripped end
  end
  return word
end

-- --- Chords -----------------------------------------------------------------

local CHORD_INTERVALS = {
  [""]        = {0, 4, 7},
  ["2"]       = {0, 2, 7},
  ["5"]       = {0, 7},
  ["6"]       = {0, 4, 7, 9},
  ["7"]       = {0, 4, 7, 10},
  ["9"]       = {0, 2, 4, 7, 10},
  ["11"]      = {0, 2, 4, 5, 7, 10},
  ["13"]      = {0, 2, 4, 7, 9, 10},
  ["69"]      = {0, 2, 4, 7, 9},
  ["add9"]    = {0, 2, 4, 7},
  ["o"]       = {0, 3, 6},
  ["h"]       = {0, 3, 6, 10},
  ["sus"]     = {0, 5, 7},
  ["^"]       = {0, 4, 7, 11},
  ["-"]       = {0, 3, 7},
  ["^7"]      = {0, 4, 7, 11},
  ["-7"]      = {0, 3, 7, 10},
  ["7sus"]    = {0, 5, 7, 10},
  ["h7"]      = {0, 3, 6, 10},
  ["o7"]      = {0, 3, 6, 9},
  ["^9"]      = {0, 2, 4, 7, 11},
  ["^13"]     = {0, 2, 4, 7, 9, 11},
  ["^7#11"]   = {0, 4, 6, 7, 11},
  ["^9#11"]   = {0, 2, 4, 6, 7, 11},
  ["^7#5"]    = {0, 4, 8, 11},
  ["-6"]      = {0, 3, 7, 9},
  ["-69"]     = {0, 2, 3, 7, 9},
  ["-^7"]     = {0, 3, 7, 11},
  ["-^9"]     = {0, 2, 3, 7, 11},
  ["-9"]      = {0, 2, 3, 7, 10},
  ["-add9"]   = {0, 2, 3, 7},
  ["-11"]     = {0, 2, 3, 5, 7, 10},
  ["-7b5"]    = {0, 3, 6, 10},
  ["h9"]      = {0, 2, 3, 6, 10},
  ["-b6"]     = {0, 3, 7, 8},
  ["-#5"]     = {0, 3, 8},
  ["7b9"]     = {0, 1, 4, 7, 10},
  ["7#9"]     = {0, 3, 4, 7, 10},
  ["7#11"]    = {0, 4, 6, 7, 10},
  ["7b5"]     = {0, 4, 6, 10},
  ["7#5"]     = {0, 4, 8, 10},
  ["9#11"]    = {0, 2, 4, 6, 7, 10},
  ["9b5"]     = {0, 2, 4, 6, 10},
  ["9#5"]     = {0, 2, 4, 8, 10},
  ["7b13"]    = {0, 4, 7, 8, 10},
  ["7#9#5"]   = {0, 3, 4, 8, 10},
  ["7#9b5"]   = {0, 3, 4, 6, 10},
  ["7#9#11"]  = {0, 3, 4, 6, 7, 10},
  ["7b9#11"]  = {0, 1, 4, 6, 7, 10},
  ["7b9b5"]   = {0, 1, 4, 6, 10},
  ["7b9#5"]   = {0, 1, 4, 8, 10},
  ["7b9#9"]   = {0, 1, 3, 4, 7, 10},
  ["7b9b13"]  = {0, 1, 4, 7, 8, 10},
  ["7alt"]    = {0, 1, 3, 4, 6, 8, 10},
  ["13#11"]   = {0, 2, 4, 6, 7, 9, 10},
  ["13b9"]    = {0, 1, 2, 4, 7, 9, 10},
  ["13#9"]    = {0, 2, 3, 4, 7, 9, 10},
  ["7b9sus"]  = {0, 1, 5, 7, 10},
  ["7susadd3"] = {0, 4, 5, 7, 10},
  ["9sus"]    = {0, 2, 5, 7, 10},
  ["13sus"]   = {0, 2, 5, 7, 9, 10},
  ["7b13sus"] = {0, 5, 7, 8, 10},
  ["aug"]     = {0, 4, 8},
  ["M"]       = {0, 4, 7},
  ["m"]       = {0, 3, 7},
  ["M7"]      = {0, 4, 7, 11},
  ["m7"]      = {0, 3, 7, 10},
  ["M9"]      = {0, 2, 4, 7, 11},
  ["M13"]     = {0, 2, 4, 7, 9, 11},
  ["M7#11"]   = {0, 4, 6, 7, 11},
  ["M9#11"]   = {0, 2, 4, 6, 7, 11},
  ["M7#5"]    = {0, 4, 8, 11},
  ["m6"]      = {0, 3, 7, 9},
  ["m69"]     = {0, 2, 3, 7, 9},
  ["m^7"]     = {0, 3, 7, 11},
  ["-M7"]     = {0, 3, 7, 11},
  ["m^9"]     = {0, 2, 3, 7, 11},
  ["-M9"]     = {0, 2, 3, 7, 11},
  ["m9"]      = {0, 2, 3, 7, 10},
  ["madd9"]   = {0, 2, 3, 7},
  ["m11"]     = {0, 2, 3, 5, 7, 10},
  ["m7b5"]    = {0, 3, 6, 10},
  ["mb6"]     = {0, 3, 7, 8},
  ["m#5"]     = {0, 3, 8},
}

local NOTE_PITCH_CLASSES = {
  C = 0, ["C#"] = 1, Db = 1, D = 2, ["D#"] = 3, Eb = 3, E = 4,
  F = 5, ["F#"] = 6, Gb = 6, G = 7, ["G#"] = 8, Ab = 8, A = 9,
  ["A#"] = 10, Bb = 10, B = 11,
}

local function parse_chord(symbol)
  symbol = trim(symbol or "")
  local root, suffix = symbol:match("^([A-G][#b]?)(.*)$")
  if root == nil then return nil end
  local root_class = NOTE_PITCH_CLASSES[root]
  local intervals = CHORD_INTERVALS[suffix]
  if root_class == nil or intervals == nil then return nil end
  return root_class, intervals
end

-- --- Tag parsing ------------------------------------------------------------

local TAG_ALIASES = {rythm = "rhythm"}
for key in pairs(DEFAULT_SETTINGS) do
  if key:find("_", 1, true) then
    TAG_ALIASES[key:gsub("_", "-")] = key
  end
end

local TAG_KEYS = {}
for key in pairs(DEFAULT_SETTINGS) do TAG_KEYS[#TAG_KEYS + 1] = key end
for key in pairs(TAG_ALIASES) do
  if DEFAULT_SETTINGS[key] == nil then TAG_KEYS[#TAG_KEYS + 1] = key end
end
table.sort(TAG_KEYS, function(a, b)
  if #a == #b then return a < b end
  return #a > #b
end)

local function is_tag_token(token)
  return token:match("^#[A-Za-z_][A-Za-z0-9_]*$") ~= nil
      or token:match("^#[A-Za-z_][A-Za-z0-9_]*%-%S*$") ~= nil
end

local function split_song_tags(line)
  local tokens = split_whitespace(line)
  if #tokens == 0 then return {} end
  for _, token in ipairs(tokens) do
    if not is_tag_token(token) then return {} end
  end
  return tokens
end

local function parse_song_tag(tag)
  local body = tag:gsub("^#", "")
  for _, key in ipairs(TAG_KEYS) do
    if body == key then
      return TAG_ALIASES[key] or key, nil
    end
    if body:sub(1, #key + 1) == key .. "-" then
      return TAG_ALIASES[key] or key, body:sub(#key + 2)
    end
  end

  -- Unknown tag: keep Python's first-hyphen split so the warning names it.
  local dash = body:find("-", 1, true)
  if dash then
    local value = body:sub(dash + 1)
    if value == "" then value = nil end
    return body:sub(1, dash - 1), value
  end
  return body, nil
end

local function apply_song_tag(settings, key, value, warnings)
  key = TAG_ALIASES[key] or key

  if DEFAULT_SETTINGS[key] == nil then
    add_warning(warnings, "Unknown tag '#" .. tostring(key) .. "' - ignored.")
    return
  end

  if BOOL_SETTINGS[key] then
    if value == nil then
      settings[key] = true
    else
      local lowered = trim(value):lower()
      settings[key] = not (lowered == "false" or lowered == "no" or lowered == "0")
    end
    return
  end

  if value == nil then
    add_warning(warnings, "Tag '#" .. key .. "' is missing a value - ignored.")
    return
  end
  value = trim(value)

  if INT_SETTINGS[key] then
    local parsed = parse_int_string(value)
    if parsed == nil then
      add_warning(warnings, "Tag '#" .. key .. "-" .. value .. "' is not a number - ignored.")
      return
    end
    if key == "beats_per_bar" and parsed < 1 then
      parsed = 1
      add_warning(warnings, "Tag '#beats_per_bar' must be at least 1 - using 1.")
    end
    if key == "tempo" then
      add_warning(warnings, "Tempo tags are ignored; the Synthesizer V project tempo governs playback.")
    end
    settings[key] = parsed
    return
  end

  if key == "note_length" or key == "scale" then
    local parsed = parse_float_string(value)
    if parsed == nil then
      add_warning(warnings, "Tag '#" .. key .. "-" .. value .. "' is not a number - ignored.")
      return
    end
    if parsed <= 0 then
      add_warning(warnings, "Tag '#" .. key .. "-" .. value .. "' must be greater than 0 - ignored.")
      return
    end
    settings[key] = parsed
    return
  end

  if key == "gap" then
    if RHYTHM_BEATS[value] ~= nil then
      settings[key] = RHYTHM_BEATS[value]
      return
    end
    local parsed = parse_float_string(value)
    if parsed == nil then
      add_warning(warnings, "Unknown gap '#" .. value .. "' - ignored.")
      return
    end
    if parsed < 0 then
      add_warning(warnings, "Tag '#gap-" .. value .. "' must not be negative - ignored.")
      return
    end
    settings[key] = parsed
    return
  end

  if key == "chord" then
    if parse_chord(value) == nil then
      add_warning(warnings, "Unknown chord '" .. value .. "' - ignored.")
      return
    end
    settings[key] = value
    return
  end

  if key == "rhythm" and RHYTHM_MODE_SET[value] then
    settings["rhythm_mode"] = value
    return
  end
  if key == "rhythm" and RHYTHM_SET[value] == nil then
    add_warning(warnings, "Unknown rhythm '" .. value .. "' - ignored.")
    return
  end
  if key == "rhythm_mode" and RHYTHM_MODE_SET[value] == nil then
    add_warning(warnings, "Unknown rhythm_mode '" .. value .. "' - ignored.")
    return
  end
  if key == "mode" and MODE_SET[value] == nil then
    add_warning(warnings, "Unknown mode '" .. value .. "' - ignored.")
    return
  end

  settings[key] = value
end

local function parse_song_sections(text, base_settings, warnings)
  local settings = make_settings(base_settings)
  local sections = {}
  local current_lines = {}

  local function flush()
    local has_content = false
    for _, line in ipairs(current_lines) do
      if trim(line) ~= "" then
        has_content = true
        break
      end
    end
    if has_content then
      sections[#sections + 1] = {
        lines = copy_table(current_lines),
        settings = copy_table(settings),
      }
    end
    current_lines = {}
  end

  for _, line in ipairs(split_lines(text)) do
    local tags = split_song_tags(line)
    if #tags > 0 then
      flush()
      for _, tag in ipairs(tags) do
        local key, value = parse_song_tag(tag)
        apply_song_tag(settings, key, value, warnings)
      end
    else
      current_lines[#current_lines + 1] = line
    end
  end
  flush()

  return sections
end

-- --- Deterministic randomness ----------------------------------------------

-- Park-Miller minimal standard LCG: deterministic and exact in doubles.
local RNG = {}
RNG.__index = RNG

local function new_rng(seed)
  local state = math.floor(tonumber(seed) or 42) % 2147483647
  if state <= 0 then state = state + 2147483646 end
  return setmetatable({state = state}, RNG)
end

function RNG:next()
  self.state = (self.state * 16807) % 2147483647
  return self.state
end

function RNG:random_int(low, high)
  local r = (self:next() - 1) / 2147483646
  return low + math.floor(r * (high - low + 1))
end

-- djb2.  The Python version uses MD5, which Lua does not provide.  The result
-- is still stable for a given word, but the pitch mapping is not identical.
local function hash_string(s)
  local h = 5381
  for i = 1, #s do
    h = (h * 33 + s:byte(i)) % 2147483647
  end
  return h
end

-- --- Generation -------------------------------------------------------------

local function generate_section(lines, settings, warnings)
  local mode = settings.mode
  local rhythm_mode = settings.rhythm_mode
  local placeholder = tostring(settings.placeholder or "+")

  local rhythm = tostring(settings.rhythm or "quarter"):lower()
  local ticks = RHYTHM_TICKS[rhythm] or PPQ
  local note_length = math.max(0.001, tonumber(settings.note_length) or 1.0)
  local gap_ticks = math.max(0, pyround(PPQ * (tonumber(settings.gap) or 0.0)))
  local scale = math.max(0.001, tonumber(settings.scale) or 1.0)
  local beats_per_bar = math.max(1, math.floor(tonumber(settings.beats_per_bar) or 4))
  local bar_ticks = PPQ * beats_per_bar
  local split_by_syllables = settings.split_by_syllables and true or false
  local split_long_words = settings.split_long_words and true or false
  local split_length = math.max(1, math.floor(tonumber(settings.split_length) or 4))

  local rng = new_rng(settings.seed)

  local chord_root, chord_intervals = parse_chord(settings.chord)
  if chord_root == nil then
    add_warning(warnings, "Unknown chord '" .. tostring(settings.chord) .. "' - using 'C'.")
    chord_root, chord_intervals = parse_chord("C")
  end
  local chord_root_note = BASE_NOTE + chord_root

  local arp_notes = {}
  for i = 1, #chord_intervals do
    local arp_note = chord_root_note + chord_intervals[i]
    while arp_note > HIGHEST_NOTE do arp_note = arp_note - 12 end
    arp_notes[i] = arp_note
  end

  local interval_start, interval_alt = BASE_NOTE, BASE_NOTE
  if mode == "fifth_up" then
    interval_start, interval_alt = 60, 67
  elseif mode == "fifth_down" then
    interval_start, interval_alt = 60, 55
  elseif mode == "third_up" then
    interval_start, interval_alt = 57, 60
  elseif mode == "third_down" then
    interval_start, interval_alt = 60, 57
  end

  local state = {
    interval_toggle = false,
    arp_index = 0,
    bar_first_note = true,
  }

  local function pick_note(word)
    local note
    if mode == "single" then
      note = BASE_NOTE
    elseif mode == "similar_words" then
      note = BASE_NOTE + (hash_string(word) % RANGE_NOTES)
    elseif mode == "seeded_random" then
      note = BASE_NOTE + rng:random_int(0, RANGE_NOTES - 1)
    elseif mode == "arp" then
      note = arp_notes[(state.arp_index % #arp_notes) + 1]
      state.arp_index = state.arp_index + 1
    elseif mode == "fifth_up" or mode == "fifth_down"
        or mode == "third_up" or mode == "third_down" then
      if state.interval_toggle then
        note = interval_alt
      else
        note = interval_start
      end
      state.interval_toggle = not state.interval_toggle
    else
      note = BASE_NOTE
    end

    if state.bar_first_note then
      note = chord_root_note
      state.bar_first_note = false
    end
    return note
  end

  local events = {}
  local cursor = 0

  for _, line in ipairs(lines) do
    local words = split_whitespace(line)
    if #words > 0 then
      if split_by_syllables then
        local expanded = {}
        for _, word in ipairs(words) do
          local parts = split_word_by_syllables(word, placeholder)
          for _, part in ipairs(parts) do expanded[#expanded + 1] = part end
        end
        words = expanded
      elseif split_long_words then
        local expanded = {}
        for _, word in ipairs(words) do
          local parts = split_word_into_notes(word, split_length, placeholder)
          for _, part in ipairs(parts) do expanded[#expanded + 1] = part end
        end
        words = expanded
      end

      state.bar_first_note = true
      state.arp_index = 0
      local bar_has_notes = false

      for _, word in ipairs(words) do
        if rhythm_mode == "natural" then
          local lyric, rest_ticks, length_source = prepare_natural_word(word, placeholder)
          if lyric == nil then
            cursor = cursor + (rest_ticks or 0)
          else
            local clean_len = utf8_len(length_source or lyric)
            local step
            if clean_len <= 2 then
              step = RHYTHM_TICKS.eighth
            elseif clean_len <= 4 then
              step = RHYTHM_TICKS.quarter
            else
              step = RHYTHM_TICKS.half
            end

            step = math.max(1, step + rng:random_int(-10, 10))
            local duration = math.max(1, pyround(step / note_length))
            local pitch = pick_note(word)

            events[#events + 1] = {
              onset = cursor,
              duration = duration,
              pitch = pitch,
              lyric = lyric,
            }

            cursor = cursor + duration
            cursor = cursor + math.max(0, step + gap_ticks - duration)
                + (rest_ticks or 0)
            bar_has_notes = true
          end
        else
          local lyric = prepare_fixed_word(word, placeholder)
          local duration = math.max(1, pyround(ticks / note_length))
          local pitch = pick_note(word)

          events[#events + 1] = {
            onset = cursor,
            duration = duration,
            pitch = pitch,
            lyric = lyric,
          }

          cursor = cursor + duration
          cursor = cursor + math.max(0, ticks + gap_ticks - duration)
          bar_has_notes = true
        end
      end

      if bar_has_notes then
        cursor = math.floor((cursor + bar_ticks - 1) / bar_ticks) * bar_ticks
      end
    end
  end

  local section_end = 0
  if scale ~= 1.0 then
    for _, event in ipairs(events) do
      local onset = pyround(event.onset / scale)
      local ending = pyround((event.onset + event.duration) / scale)
      local duration = ending - onset
      if duration < 1 then duration = 1 end
      event.onset = onset
      event.duration = duration
      if onset + duration > section_end then
        section_end = onset + duration
      end
    end
  else
    for _, event in ipairs(events) do
      if event.onset + event.duration > section_end then
        section_end = event.onset + event.duration
      end
    end
  end

  return events, section_end
end

local function generate_song(text, base_settings)
  local warnings = {}
  local sections = parse_song_sections(text, base_settings, warnings)
  local events = {}
  local written = 0

  for index, section in ipairs(sections) do
    local section_events, section_end = generate_section(
      section.lines, section.settings, warnings)

    local pad = 0
    if index > 1 then
      local scale = math.max(0.001, tonumber(section.settings.scale) or 1.0)
      local beats_per_bar = math.max(1, math.floor(tonumber(section.settings.beats_per_bar) or 4))
      local bar_ticks = math.max(1, pyround(PPQ * beats_per_bar / scale))
      pad = (bar_ticks - (written % bar_ticks)) % bar_ticks
    end

    local offset = written + pad
    for _, event in ipairs(section_events) do
      events[#events + 1] = {
        onset = event.onset + offset,
        duration = event.duration,
        pitch = event.pitch,
        lyric = event.lyric,
      }
    end
    written = offset + section_end
  end

  local duration = 0
  for _, event in ipairs(events) do
    local ending = event.onset + event.duration
    if ending > duration then duration = ending end
  end

  return {
    events = events,
    sections = #sections,
    duration = duration,
    warnings = warnings,
  }
end

-- --- Dialog helpers ---------------------------------------------------------

local function combo_value(answer, choices, default_index)
  local index = nil
  if type(answer) == "number" then
    index = math.floor(answer)
  elseif type(answer) == "string" then
    for _, choice in ipairs(choices) do
      if choice == answer then return choice end
    end
    local numeric = tonumber(answer)
    if numeric ~= nil then index = math.floor(numeric) end
  end

  if index == nil then index = default_index or 0 end
  if index < 0 then index = 0 end
  if index > #choices - 1 then index = #choices - 1 end
  return choices[index + 1]
end

local function text_answer(answers, name, default)
  local value = answers[name]
  if value == nil then return default end
  return tostring(value)
end

local function bool_answer(answers, name, default)
  local value = answers[name]
  if type(value) == "boolean" then return value end
  if type(value) == "number" then return value ~= 0 end
  if type(value) == "string" then
    local lowered = value:lower()
    return lowered == "true" or lowered == "yes" or lowered == "1"
  end
  return default
end

local function answer_int(answers, name, default, minimum)
  local raw = text_answer(answers, name, tostring(default))
  local parsed = parse_int_string(raw)
  if parsed == nil then return default end
  if minimum ~= nil and parsed < minimum then return minimum end
  return parsed
end

local function answer_float(answers, name, default, minimum)
  local raw = text_answer(answers, name, tostring(default))
  local parsed = parse_float_string(raw)
  if parsed == nil then return default end
  if minimum ~= nil and parsed < minimum then return minimum end
  return parsed
end

local function answer_gap(answers, name, default)
  local raw = trim(text_answer(answers, name, tostring(default)))
  if RHYTHM_BEATS[raw] ~= nil then return RHYTHM_BEATS[raw] end
  local parsed = parse_float_string(raw)
  if parsed == nil or parsed < 0 then return default end
  return parsed
end

local function settings_from_answers(answers)
  local chord = trim(text_answer(answers, "chord", "C"))
  if chord == "" then chord = "C" end

  return {
    tempo = 120, -- parsed for tag compatibility; not applied to the project
    rhythm = combo_value(answers.rhythm, RHYTHM_CHOICES, 2),
    rhythm_mode = combo_value(answers.rhythm_mode, RHYTHM_MODE_CHOICES, 0),
    mode = combo_value(answers.mode, MODE_CHOICES, 0),
    seed = answer_int(answers, "seed", 42, nil),
    beats_per_bar = answer_int(answers, "beats_per_bar", 4, 1),
    split_long_words = bool_answer(answers, "split_long_words", false),
    split_length = answer_int(answers, "split_length", 4, 1),
    placeholder = combo_value(answers.placeholder, PLACEHOLDER_CHOICES, 0),
    split_by_syllables = bool_answer(answers, "split_by_syllables", false),
    chord = chord,
    note_length = answer_float(answers, "note_length", 1.0, 0.001),
    gap = answer_gap(answers, "gap", 0.0),
    scale = answer_float(answers, "scale", 1.0, 0.001),
  }
end

-- --- Synthesizer V entry points --------------------------------------------

function getClientInfo()
  return {
    name = "Lyrics to Notes (Lua)",
    category = "Lyrics",
    author = "audio_checks",
    versionNumber = 1,
    minEditorVersion = 65537,
  }
end

local function plural(count, singular, plural_form)
  if count == 1 then return singular end
  return plural_form
end

function main()
  local clipboard = SV:getHostClipboard()
  if type(clipboard) ~= "string" then clipboard = "" end

  local form = {
    title = "Lyrics to Notes",
    message = "One lyric line per musical bar. Paste Obsidian-style tags to override the defaults: "
        .. "#mode-arp, #chord-Am, #rhythm-natural, #rhythm-eighth, #beats-per-bar-3, "
        .. "#split-by-syllables, #split-long-words, #split-length-4, #note-length-2, "
        .. "#gap-eighth, #scale-2, #seed-7. Tempo tags are ignored; the project tempo is used.",
    buttons = "OkCancel",
    widgets = {
      {
        name = "lyrics", type = "TextArea",
        label = "Lyrics (one musical bar per line)",
        height = 210,
        default = clipboard,
      },
      {
        name = "mode", type = "ComboBox",
        label = "Pitch mode",
        choices = MODE_CHOICES,
        default = 0,
      },
      {
        name = "rhythm_mode", type = "ComboBox",
        label = "Rhythm mode",
        choices = RHYTHM_MODE_CHOICES,
        default = 0,
      },
      {
        name = "rhythm", type = "ComboBox",
        label = "Fixed rhythm",
        choices = RHYTHM_CHOICES,
        default = 2,
      },
      {
        name = "chord", type = "TextBox",
        label = "Chord (e.g. C, Am, C^7#11)",
        default = "C",
      },
      {
        name = "beats_per_bar", type = "TextBox",
        label = "Beats per bar",
        default = "4",
      },
      {
        name = "split_by_syllables", type = "CheckBox",
        text = "Split words by syllable (word first, then '+' per extra syllable)",
        default = false,
      },
      {
        name = "split_long_words", type = "CheckBox",
        text = "Split long words into placeholder notes",
        default = false,
      },
      {
        name = "split_length", type = "TextBox",
        label = "Long-word split length (characters)",
        default = "4",
      },
      {
        name = "note_length", type = "TextBox",
        label = "Note length divisor (2 = half-length notes)",
        default = "1",
      },
      {
        name = "gap", type = "TextBox",
        label = "Gap after each note (beats or rhythm name)",
        default = "0",
      },
      {
        name = "scale", type = "TextBox",
        label = "Timeline divisor (2 = half total length)",
        default = "1",
      },
      {
        name = "seed", type = "TextBox",
        label = "Random seed",
        default = "42",
      },
      {
        name = "placeholder", type = "ComboBox",
        label = "Split / continuation token",
        choices = PLACEHOLDER_CHOICES,
        default = 0,
      },
      {
        name = "new_track", type = "CheckBox",
        text = "Create a new track",
        default = false,
      },
    },
  }

  local result = SV:showCustomDialog(form)
  local status = result and result.status
  if not (status == "Ok" or status == true or status == "Yes") then
    SV:finish()
    return
  end

  local answers = (result and result.answers) or {}
  local lyrics = text_answer(answers, "lyrics", "")
  if trim(lyrics) == "" then
    SV:showMessageBox("Lyrics to Notes", "No lyrics were provided.")
    SV:finish()
    return
  end

  local generated = generate_song(lyrics, settings_from_answers(answers))
  if #generated.events == 0 then
    local message = "No notes were generated. Check the lyrics and settings."
    if #generated.warnings > 0 then
      message = message .. "\n\n" .. table.concat(generated.warnings, "\n")
    end
    SV:showMessageBox("Lyrics to Notes", message)
    SV:finish()
    return
  end

  local project = SV:getProject()
  local editor = SV:getMainEditor()

  local group = SV:create("NoteGroup")
  local section_word = plural(generated.sections, "section", "sections")
  group:setName(string.format("Lyrics to Notes (%d %s)",
    generated.sections, section_word))

  local tick_to_blick = SV.QUARTER / PPQ
  local function to_blick(ticks)
    return math.floor(ticks * tick_to_blick + 0.5)
  end

  for _, event in ipairs(generated.events) do
    local onset = to_blick(event.onset)
    local ending = to_blick(event.onset + event.duration)
    local duration = ending - onset
    if duration < 1 then duration = 1 end

    local note = SV:create("Note")
    note:setTimeRange(onset, duration)
    note:setPitch(event.pitch)
    note:setLyrics(event.lyric)
    group:addNote(note)
  end

  project:addNoteGroup(group)

  local make_new_track = bool_answer(answers, "new_track", false)
  local source_group = editor:getCurrentGroup()
  local target_track

  if make_new_track then
    target_track = SV:create("Track")
    target_track:setName("Lyrics to Notes")
    project:addTrack(target_track)
  else
    target_track = editor:getCurrentTrack()
    if target_track == nil then target_track = project:getTrack(1) end
  end

  local reference = SV:create("NoteGroupReference")
  reference:setTarget(group)

  -- A new track starts with the default voice; copy the current group's voice
  -- so the generated notes keep the sound the user is already working with.
  if make_new_track and source_group ~= nil then
    local ok, voice = pcall(function() return source_group:getVoice() end)
    if ok and voice ~= nil then
      pcall(function() reference:setVoice(voice) end)
    end
  end

  local start_blick = 0
  local ok_playback, playback = pcall(function() return SV:getPlayback() end)
  if ok_playback and playback ~= nil then
    local ok_head, seconds = pcall(function() return playback:getPlayhead() end)
    if ok_head and seconds ~= nil then
      local ok_blick, blick = pcall(function()
        return project:getTimeAxis():getBlickFromSeconds(seconds)
      end)
      if ok_blick and blick ~= nil then start_blick = blick end
    end
  end
  if start_blick < 0 then start_blick = 0 end
  reference:setTimeOffset(math.floor(start_blick + 0.5))

  target_track:addGroupReference(reference)

  local note_word = plural(#generated.events, "note", "notes")
  local message = string.format("Created %d %s in %d %s and placed it at the playhead.",
    #generated.events, note_word, generated.sections, section_word)
  if make_new_track then
    message = message .. "\nTrack: new track \"Lyrics to Notes\"."
  else
    message = message .. "\nTrack: current track."
  end

  if #generated.warnings > 0 then
    local shown = {}
    for i = 1, math.min(#generated.warnings, 12) do
      shown[#shown + 1] = generated.warnings[i]
    end
    message = message .. "\n\nWarnings:\n" .. table.concat(shown, "\n")
    if #generated.warnings > #shown then
      message = message .. "\n(" .. (#generated.warnings - #shown) .. " more)"
    end
  end

  SV:showMessageBox("Lyrics to Notes", message)
  SV:finish()
end

-- Exposed for testing; Synthesizer V only calls getClientInfo() and main().
LyricsToNotes = {
  generate_song = generate_song,
  parse_song_sections = parse_song_sections,
  parse_song_tag = parse_song_tag,
  parse_chord = parse_chord,
  count_syllables = count_syllables,
  split_word_by_syllables = split_word_by_syllables,
  split_word_into_notes = split_word_into_notes,
  split_song_tags = split_song_tags,
  default_settings = DEFAULT_SETTINGS,
  choices = {
    rhythm = RHYTHM_CHOICES,
    rhythm_mode = RHYTHM_MODE_CHOICES,
    mode = MODE_CHOICES,
    placeholder = PLACEHOLDER_CHOICES,
  },
  pyround = pyround,
}
