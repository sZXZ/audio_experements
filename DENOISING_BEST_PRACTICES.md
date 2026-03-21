# Best Practices for Natural-Sounding Denoising

Denoising is a delicate balance. If you push it too hard, your audio will sound "watery," "robotic," or "hollow." This guide helps you achieve professional, natural-sounding results using the `remove_noise.py` script and the `noisereduce` library.

---

## 1. The Power of the Noiseprint
The quality of your result depends almost entirely on your noise sample.
- **Find "Pure" Noise**: Look for a section of the recording where nothing else is happening—no breathing, no mouth clicks, and no background voices. Even 0.5 seconds of "silence" can work if it contains the representative background hiss or hum.
- **Representative Noise**: Ensure the noise in your sample is the same noise present during the speech/music. If the character of the noise changed (e.g., a fan turned on halfway through), use a sample from the specific section you are cleaning.

## 2. Avoid the "Watery" Sound (`prop_decrease`)
The most common mistake is trying to remove 100% of the noise. This often creates "bubbly" artifacts called *musical noise*.
- **The "80% Rule"**: Instead of `prop_decrease=1.0`, try `0.8` or `0.9`. Leaving a tiny bit of natural floor noise often sounds much more "real" and less "processed" to the human ear.
- **Multiple Passes**: Sometimes, doing two passes at `0.5` decrease with different settings yields better results than a single pass at `1.0`.

## 3. Balancing Frequency and Time (`n_fft`)
The `n_fft` parameter controls how the algorithm "hears" the sound.
- **Low `n_fft` (512, 1024)**: Better for short, percussive sounds (drums, clicks). It has better **time resolution**.
- **High `n_fft` (2048, 4096)**: Better for constant hums or whistles. It has better **frequency resolution**, meaning it can pinpoint specific noise frequencies more accurately without affecting nearby harmonics.

## 4. Smoothing Artifacts
If the audio sounds "glassy" or "bubbly," you need to smooth the noise mask.
- **`freq_mask_smooth_hz`**: Increase this (e.g., to `1000`) to smooth out frequency-based artifacts.
- **`time_mask_smooth_ms`**: Increase this (e.g., to `100`) to blend the transitions between noisy and clean sections more naturally.

## 5. Stationary vs. Non-Stationary
- **`stationary=True`**: Use this for predictable noise like white noise, tape hiss, or a constant computer fan.
- **`stationary=False`**: Use this for unpredictable noise like a distant highway, wind, or "babble" (crowd noise). It is slower to process but much more effective for changing environments.

## 6. Pre-Processing: The High-Pass Filter
Before denoising, check if your noise is mostly "rumble" (low-frequency).
- **Cut the Lows**: Many background noises are below 80-100Hz. Using a High-Pass Filter (HPF) *before* denoising can significantly reduce the workload for the algorithm and preserve more "life" in the upper frequencies.

## 7. Post-Processing: Restoring the "Air"
After denoising, the audio might feel "dead" or extremely dry.
- **Add a Hint of Room Tone**: Sometimes adding a very quiet, high-quality "room tone" recording *back* in can mask the fact that denoising occurred.
- **Subtle EQ**: Use a slight "High Shelf" boost (around 10kHz+) after denoising to restore some of the "air" that might have been lost in the process.

## Summary Checklist for a "Better" Clean:
1. **Sample**: Select a high-quality noiseprint.
2. **Decrease**: Set `prop_decrease` to `0.85` instead of `1.0`.
3. **Smooth**: Increase `time_mask_smooth_ms` to `60` or `80`.
4. **Resolution**: If cleaning constant hum, set `n_fft` to `2048`.
5. **Trust your Ears**: If it sounds robotic, dial back the `prop_decrease`.
