# Noise Removal Script Guide

This guide explains how to use the `remove_noise.py` script and the `noisereduce` library both from the command line and within a Jupyter Notebook.

## Methodology: Noiseprint-Based Reduction
The script uses spectral subtraction provided by the `noisereduce` library. It analyzes a "noiseprint" (a sample of pure noise from the same recording) to create a noise profile, which is then subtracted from the target audio.

## 1. Using from Command Line
You can run the script directly using the virtual environment's Python:

```bash
./.venv/bin/python3 remove_noise.py \
    "/Users/alex/Music/Samples/scizors/s_1_cut_4_norm0db_12db.wav" \
    "/Users/alex/Music/Samples/scizors/s_1_cut_4_norm0db_12db_noise_sample.wav" \
    --output "cleaned_audio.wav"
```

---

## 2. Using inside a Jupyter Notebook

You can integrate the noise removal logic directly into your notebook.

### Preparation
Ensure the `noisereduce` library is available. In your notebook, make sure you are using the kernel associated with `./.venv`.

### Implementation
Copy the following code into a notebook cell:

```python
import noisereduce as nr
import numpy as np
import IPython.display as ipd
from scipy.io import wavfile

# Paths to your files
input_path = "/Users/alex/Music/Samples/scizors/s_1_cut_4_norm0db_12db.wav"
noise_path = "/Users/alex/Music/Samples/scizors/s_1_cut_4_norm0db_12db_noise_sample.wav"

# Load audio
rate, data = wavfile.read(input_path)
noise_rate, noise_data = wavfile.read(noise_path)

# Handle Stereo (move channels to first dimension)
if len(data.shape) > 1:
    data = data.T
if len(noise_data.shape) > 1:
    noise_data = noise_data.T

# Apply Noise Reduction
print("Reducing noise...")
reduced_data = nr.reduce_noise(
    y=data, 
    sr=rate, 
    y_noise=noise_data, 
    stationary=True
)

# Listen in browser (requires mono or specific layout)
# For playback, we transpose back if it was stereo
output_data = reduced_data.T if len(reduced_data.shape) > 1 else reduced_data
ipd.Audio(output_data, rate=rate)
```

### Tips for Better Results
- **Stationary vs Non-stationary**: Set `stationary=True` (default in the script) for constant hum/hiss. If the noise varies over time (like babble), try `stationary=False` (this is more computationally intensive).
- **prop_decrease**: If the output sounds "watery" or has artifacts (musical noise), try decreasing `prop_decrease` to `0.8` or `0.9` in the `reduce_noise()` function.
- **Normalization**: If your noise sample is very quiet, you may want to normalize it before processing, although the script handles most cases automatically.
