import cv2
import numpy as np
from scipy.io import wavfile


class WavStream(object):
    def __init__(self, path, sample_rate = 12000, sample_type = 'float32'):
        rate, data = wavfile.read(path)
        data = np.array(data[:, 0], ndmin=2, dtype=np.uint16)
        self.samples_count = int(len(data[0]) / float(rate) * sample_rate)
        self.sample_rate = sample_rate

        if sample_type == 'float32':
            # precise but eats memory
            data = cv2.resize(data, (self.samples_count, 1))
            self.data = data.astype(np.float32) / 32768.0
        elif sample_type == 'uint8':
            # less precise but more memory efficient
            data = (data >> 8).astype(np.uint8)
            self.data = cv2.resize(data, (self.samples_count, 1))
        else:
            raise RuntimeError('Unknown sample type of WAV stream, must be uint8 or float32')

    @property
    def duration_seconds(self):
        return self.samples_count / self.sample_rate

    def get_substream(self, start, end):
        start_off = self.to_number_of_samples(start)
        end_off = self.to_number_of_samples(end)
        return self.data[:, start_off:end_off]

    def to_number_of_samples(self, time):
        return int(self.sample_rate * time)

    def find_substream(self, pattern, **kwargs):
        start_time = max(kwargs.get('start_time', 0.0), 0.0)
        end_time = max(kwargs.get('end_time', self.samples_count), 0.0)

        start_sample = self.to_number_of_samples(start_time)
        end_sample = self.to_number_of_samples(end_time) + len(pattern[0])

        search_source = self.data[:, start_sample:end_sample]
        result = cv2.matchTemplate(search_source, pattern, cv2.TM_SQDIFF_NORMED)
        min_idx = result.argmin(axis=1)[0]

        return result[0][min_idx], start_time + (min_idx / float(self.sample_rate))

#
# def write_wav(float_array, sample_rate, path):
#     data = (float_array * 32768.0).astype(np.int16)
#     wavfile.write(path, sample_rate, data[0])
