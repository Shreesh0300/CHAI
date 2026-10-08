import sounddevice as sd
import numpy as np

def find_best_input_device():
    devs = sd.query_devices()
    candidates = []
    for idx, d in enumerate(devs):
        if d['max_input_channels'] <= 0:
            continue
        name_lower = d['name'].lower()
        if any(v in name_lower for v in ['voicemod', 'dummy', 'mapper', 'primary', 'stereo mix']):
            continue
        candidates.append(idx)
    
    print('Filtered candidates:', [(i, devs[i]['name']) for i in candidates])
    
    best_idx = None
    best_peak = -1
    for idx in candidates:
        try:
            sample = sd.rec(int(0.2 * 16000), samplerate=16000, channels=1, dtype='int16', device=idx)
            sd.wait()
            peak = int(np.max(np.abs(sample)))
            name = devs[idx]['name']
            print(f'Device {idx} ({name}): peak = {peak}')
            if peak > best_peak:
                best_peak = peak
                best_idx = idx
        except Exception as e:
            print(f'Error testing {idx}: {e}')
    
    selected_name = devs[best_idx]['name'] if best_idx is not None else 'None'
    print(f'Selected device: {best_idx} ({selected_name}) with peak {best_peak}')
    return best_idx

if __name__ == '__main__':
    find_best_input_device()
