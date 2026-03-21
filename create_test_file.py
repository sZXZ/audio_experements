import numpy as np
from scipy.io import wavfile
import os

def create_test_wav(filename="test_sine.wav", frequency=440.0, duration_sec=1.0, samplerate=44100, volume_db=-10.0):
    """
    Creates a sine wave WAV file for testing purposes.
    Volume is in dBFS.
    """
    t = np.linspace(0, duration_sec, int(samplerate * duration_sec), endpoint=False)
    # Peak amplitude for 0 dBFS is 1.0. 
    # Amplitude for X dBFS is 10^(X/20)
    amplitude = 10 ** (volume_db / 20)
    
    # Generate sine wave
    data = amplitude * np.sin(2 * np.pi * frequency * t)
    
    # Convert to 16-bit PCM
    data_int16 = (data * 32767).astype(np.int16)
    
    # Write to file
    wavfile.write(filename, samplerate, data_int16)
    print(f"Created test file: {filename} at {volume_db} dBFS Peak.")

if __name__ == "__main__":
    create_test_wav()
