import noisereduce as nr
import numpy as np
from scipy.io import wavfile
import argparse
import os

def remove_noise(input_path, noise_path, output_path):
    """
    Remove noise from a WAV file using a noiseprint-based approach with 'noisereduce'.
    """
    print(f"Loading files...")
    # Load noisy audio
    rate, data = wavfile.read(input_path)
    # Load noise sample (noiseprint)
    noise_rate, noise_data = wavfile.read(noise_path)
    
    if rate != noise_rate:
        print(f"Warning: Sample rates don't match! Input: {rate}, Noise: {noise_rate}. Results may be poor.")
    
    # Store original dtype and shape
    original_dtype = data.dtype
    is_stereo = len(data.shape) > 1
    
    # noisereduce expects data in shape (channels, samples)
    # wavfile.read returns (samples, channels)
    if is_stereo:
        data = data.T
        if len(noise_data.shape) > 1:
            noise_data = noise_data.T
    
    # Perform noise reduction
    # y: the noisy audio
    # y_noise: the noise sample to analyze
    # stationary: Whether to use stationary or non-stationary noise reduction
    print(f"Applying noise reduction (noiseprint-based)...")
    reduced_noise = nr.reduce_noise(
        y=data, 
        sr=rate, 
        y_noise=noise_data,
        stationary=True,  # Set to True for constant background noise
        prop_decrease=1.0  # Proportion of noise to reduce (0-1)
    )
    
    # Transpose back to (samples, channels) for wavfile.write
    if is_stereo:
        reduced_noise = reduced_noise.T
    
    # Clip and convert back to original dtype to avoid artifacts/errors
    if np.issubdtype(original_dtype, np.integer):
        info = np.iinfo(original_dtype)
        reduced_noise = np.clip(reduced_noise, info.min, info.max).astype(original_dtype)
    else:
        reduced_noise = reduced_noise.astype(original_dtype)
        
    # Write to file
    wavfile.write(output_path, rate, reduced_noise)
    print(f"Done! Cleaned audio saved to: {output_path}")

def main():
    parser = argparse.ArgumentParser(description="Noise reduction using noiseprint.")
    parser.add_argument("input", help="Path to noisy .wav file")
    parser.add_argument("noise", help="Path to noise sample .wav file")
    parser.add_argument("-o", "--output", help="Output .wav path", default="cleaned.wav")
    
    args = parser.parse_args()
    
    if not os.path.exists(args.input):
        print(f"Error: Input file not found: {args.input}")
        return
    if not os.path.exists(args.noise):
        print(f"Error: Noise sample file not found: {args.noise}")
        return
        
    remove_noise(args.input, args.noise, args.output)

if __name__ == "__main__":
    main()
