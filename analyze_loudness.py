import sys
import numpy as np
from scipy.io import wavfile
import argparse

def analyze_loudness(filename):
    """
    Analyzes a WAV file and calculates its Peak and RMS loudness in dBFS.
    """
    try:
        sample_rate, data = wavfile.read(filename)
    except Exception as e:
        print(f"Error reading file {filename}: {e}")
        return

    # Normalize data to float32 in range [-1.0, 1.0]
    if data.dtype == np.int16:
        data = data.astype(np.float32) / 32768.0
    elif data.dtype == np.int32:
        data = data.astype(np.float32) / 2147483648.0
    elif data.dtype == np.uint8:
        data = (data.astype(np.float32) - 128.0) / 128.0
    elif data.dtype == np.float32 or data.dtype == np.float64:
        # Data is already float, but we skip it for performance if it's already in range
        pass
    else:
        print(f"Unsupported data type: {data.dtype}")
        return

    # Handle multi-channel files
    if len(data.shape) > 1:
        # data.shape[1] is the number of channels
        num_channels = data.shape[1]
        
        # Calculate per-channel stats
        peak_per_channel = np.max(np.abs(data), axis=0)
        rms_per_channel = np.sqrt(np.mean(data**2, axis=0))
        
        # Calculate overall stats
        peak_overall = np.max(peak_per_channel)
        # Average RMS across channels
        rms_overall = np.sqrt(np.mean(data**2))
    else:
        num_channels = 1
        peak_overall = np.max(np.abs(data))
        rms_overall = np.sqrt(np.mean(data**2))
        peak_per_channel = [peak_overall]
        rms_per_channel = [rms_overall]

    # Convert to dB (relative to Full Scale)
    def to_db(value):
        if value > 0:
            return 20 * np.log10(value)
        return -float('inf')

    peak_db = to_db(peak_overall)
    rms_db = to_db(rms_overall)

    # Print results
    print("-" * 40)
    print(f"Loudness Analysis for: {filename}")
    print("-" * 40)
    print(f"Sample Rate: {sample_rate} Hz")
    print(f"Channels:    {num_channels}")
    print(f"Duration:    {len(data)/sample_rate:.3f} seconds")
    print("-" * 40)
    print(f"Peak (Overall):  {peak_db: >7.2f} dBFS")
    print(f"RMS (Overall):   {rms_db: >7.2f} dBFS")
    
    if num_channels > 1:
        print("-" * 40)
        for i in range(num_channels):
            p_db = to_db(peak_per_channel[i])
            r_db = to_db(rms_per_channel[i])
            print(f"Channel {i+1} Peak: {p_db: >7.2f} dBFS")
            print(f"Channel {i+1} RMS:  {r_db: >7.2f} dBFS")
    print("-" * 40)

def main():
    parser = argparse.ArgumentParser(description="Analyze WAV file loudness.")
    parser.add_argument("filename", help="Path to the .wav file")
    args = parser.parse_args()
    
    analyze_loudness(args.filename)

if __name__ == "__main__":
    main()
