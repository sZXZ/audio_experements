import noisereduce as nr
import numpy as np
from scipy.io import wavfile
import argparse
import os

def remove_noise(
    input_path, 
    output_path, 
    noise_path=None, 
    stationary=True, 
    prop_decrease=1.0, 
    time_constant_s=2.0, 
    freq_mask_smooth_hz=500, 
    time_mask_smooth_ms=50, 
    thresh_n_mult_nonstationary=2, 
    sigmoid_slope_nonstationary=10, 
    n_std_thresh_stationary=1.5, 
    tmp_folder=None, 
    chunk_size=600000, 
    padding=30000, 
    n_fft=1024, 
    win_length=None, 
    hop_length=None, 
    clip_noise_stationary=True, 
    use_tqdm=False, 
    n_jobs=1, 
    use_torch=False, 
    device='cpu'
):
    """
    Remove noise from a WAV file using 'noisereduce'.
    If noise_path is provided, it uses it as a noiseprint. 
    Otherwise, it analyzes the entire input signal to detect noise.
    
    Parameters
    ----------
    input_path : str
        Path to the noisy input WAV file.
    output_path : str
        Path where the cleaned audio file will be saved.
    noise_path : str, optional
        Path to the noise sample (noiseprint) WAV file. If None, the script 
        will attempt to estimate noise from the input audio. Defaults to None.
    stationary : bool, optional
        Whether the noise is stationary (constant hum/hiss) or non-stationary (e.g. babble).
        Defaults to True. Note: If noise_path is None, you might want to try 
        setting stationary to False for non-constant noises.
    prop_decrease : float, optional
        The proportion of noise to reduce (0.0 to 1.0). 1.0 is total reduction.
        Defaults to 1.0.
    time_constant_s : float, optional
        The time constant (in seconds) for calculating the noise mask. 
        Higher values lead to more smoothing. Defaults to 2.0.
    freq_mask_smooth_hz : int, optional
        The frequency (in Hz) to smooth the noise mask over. Defaults to 500.
    time_mask_smooth_ms : int, optional
        The time (in ms) to smooth the noise mask over. Defaults to 50.
    thresh_n_mult_nonstationary : float, optional
        The threshold multiplier for non-stationary noise reduction. Defaults to 2.
    sigmoid_slope_nonstationary : float, optional
        The slope of the sigmoid for non-stationary noise reduction. Defaults to 10.
    n_std_thresh_stationary : float, optional
        The number of standard deviations for the threshold in stationary noise reduction. 
        Defaults to 1.5.
    tmp_folder : str, optional
        The folder to store temporary files if memory is an issue. Defaults to None.
    chunk_size : int, optional
        The number of samples per chunk for processing long files. Defaults to 600000.
    padding : int, optional
        The number of samples for padding chunks. Defaults to 30000.
    n_fft : int, optional
        The number of FFT bins. Defaults to 1024.
    win_length : int, optional
        The window length for the STFT. If None, it uses n_fft. Defaults to None.
    hop_length : int, optional
        The hop length for the STFT. If None, it uses n_fft // 4. Defaults to None.
    clip_noise_stationary : bool, optional
        Whether to clip the noise mask in stationary noise reduction. Defaults to True.
    use_tqdm : bool, optional
        Whether to show a progress bar. Defaults to False.
    n_jobs : int, optional
        The number of parallel jobs for processing. Defaults to 1.
    use_torch : bool, optional
        Whether to use PyTorch for faster processing (requires torch). Defaults to False.
    device : str, optional
        The hardware device to use if use_torch is True (e.g. 'cuda', 'cpu', 'mps'). 
        Defaults to 'cpu'.
    """
    print(f"Loading files...")
    # Load noisy audio
    rate, data = wavfile.read(input_path)
    
    noise_data = None
    if noise_path:
        # Load noise sample (noiseprint)
        noise_rate, noise_data = wavfile.read(noise_path)
        if rate != noise_rate:
            print(f"Warning: Sample rates don't match! Input: {rate}, Noise: {noise_rate}. Results may be poor.")
        
        # noisereduce expects data in shape (channels, samples)
        if len(noise_data.shape) > 1:
            noise_data = noise_data.T
    
    # Store original dtype and shape
    original_dtype = data.dtype
    is_stereo = len(data.shape) > 1
    
    # noisereduce expects data in shape (channels, samples)
    if is_stereo:
        data = data.T
    
    # Perform noise reduction
    print(f"Applying noise reduction...")
    reduced_noise = nr.reduce_noise(
        y=data, 
        sr=rate, 
        y_noise=noise_data,
        stationary=stationary,
        prop_decrease=prop_decrease,
        time_constant_s=time_constant_s,
        freq_mask_smooth_hz=freq_mask_smooth_hz,
        time_mask_smooth_ms=time_mask_smooth_ms,
        thresh_n_mult_nonstationary=thresh_n_mult_nonstationary,
        sigmoid_slope_nonstationary=sigmoid_slope_nonstationary,
        n_std_thresh_stationary=n_std_thresh_stationary,
        tmp_folder=tmp_folder,
        chunk_size=chunk_size,
        padding=padding,
        n_fft=n_fft,
        win_length=win_length,
        hop_length=hop_length,
        clip_noise_stationary=clip_noise_stationary,
        use_tqdm=use_tqdm,
        n_jobs=n_jobs,
        use_torch=use_torch,
        device=device
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
    parser.add_argument("-n", "--noise", help="Optional path to noise sample .wav file", default=None)
    parser.add_argument("-o", "--output", help="Output .wav path", default="cleaned.wav")
    parser.add_argument("--stationary", type=lambda x: (str(x).lower() == 'true'), default=True, help="Stationary noise reduction (True/False)")
    parser.add_argument("--prop_decrease", type=float, default=1.0, help="Proportion of noise reduction")
    
    args = parser.parse_args()
    
    if not os.path.exists(args.input):
        print(f"Error: Input file not found: {args.input}")
        return
    if args.noise and not os.path.exists(args.noise):
        print(f"Error: Noise sample file not found: {args.noise}")
        return
        
    remove_noise(
        args.input, 
        args.output, 
        noise_path=args.noise, 
        stationary=args.stationary, 
        prop_decrease=args.prop_decrease
    )

if __name__ == "__main__":
    main()
