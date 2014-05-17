import cv2
import math
import numpy as np
from scipy.io import wavfile
from chunk import Chunk
import struct

WAVE_FORMAT_PCM = 0x0001
WAVE_FORMAT_EXTENSIBLE = 0xFFFE

class DownmixedWavFile(object):
    def __init__(self, path):
        super(DownmixedWavFile, self).__init__()
        self._file = None
        self._file = open(path, 'rb')
        try:
            riff = Chunk(self._file, bigendian=False)
            if riff.getname() != 'RIFF':
                raise Exception('file does not start with RIFF id')
            if riff.read(4) != 'WAVE':
                raise Exception('not a WAVE file')

            fmt = Chunk(self._file, bigendian=False)
            if fmt.getname() != 'fmt ':
                raise Exception('Invalid WAV header')
            self._read_fmt_chunk(fmt)
            fmt.skip()

            self._data_chunk = Chunk(self._file, bigendian=False)
            if self._data_chunk.getname() != 'data':
                raise Exception('Invalid WAV header')
            self.frames_count = self._data_chunk.chunksize // self.frame_size
            self.data_start = self._file
        except:
            if self._file:
                self._file.close()
            raise

    def __del__(self):
        self.close()

    def close(self):
        if self._file:
            self._file.close()
            self._file = None

    def readframes(self, count):
        if not count:
            return ''
        data = self._data_chunk.read(count * self.frame_size)
        if self.sample_width == 2:
            unpacked = np.fromstring(data, dtype=np.int16)
        elif self.sample_width == 3:
            s = ''.join(['\0' + data[i:i+3] for i in xrange(0, len(data), 3)])
            unpacked = np.fromstring(s, dtype=np.int32) >> 8
        else:
            raise Exception('Unsupported sample width: {0}'.format(self.sample_width))

        if self.channels_count == 1:
            return np.array(unpacked, dtype=np.float64)
        elif self.channels_count == 2:
            even = unpacked[::2]
            odd = unpacked[1::2]
            return (even + odd) / 2.0


    def _read_fmt_chunk(self, chunk):
        wFormatTag, self.channels_count, self.framerate, dwAvgBytesPerSec, wBlockAlign = struct.unpack('<HHLLH', chunk.read(14))
        if wFormatTag == WAVE_FORMAT_PCM or wFormatTag == WAVE_FORMAT_EXTENSIBLE: # ignore the rest
            bits_per_sample = struct.unpack('<H', chunk.read(2))[0]
            self.sample_width = (bits_per_sample + 7) // 8
        else:
            raise Exception('unknown format: {0}'.format(wFormatTag))
        self.frame_size = self.channels_count * self.sample_width

class WavStream(object):
    def __init__(self, path, sample_rate=12000, sample_type='float32'):
        if sample_type not in ('float32', 'uint8'):
            raise RuntimeError('Unknown sample type of WAV stream, must be uint8 or float32')

        file = DownmixedWavFile(path)
        total_seconds = file.frames_count / float(file.framerate)
        downsample_rate = sample_rate / float(file.framerate)

        self.sample_count = int(total_seconds * sample_rate)
        self.sample_rate = sample_rate

        seconds_read = 0
        chunk = 1  # one second, seems to be the fastest
        arrays = []
        while seconds_read < total_seconds:
            data = file.readframes(int(chunk*file.framerate))
            new_length = int(round(len(data) * downsample_rate))
            data = np.array(data, ndmin=2)
            data = cv2.resize(data, (new_length, 1), interpolation=cv2.INTER_NEAREST)

            if sample_type == 'float32':
                # precise but eats memory
                arrays.append(data.astype(np.float32) / (32768.0 if file.sample_width == 2 else 8388608.0))
            else:
                # less precise but more memory efficient
                arrays.append((data / 256.0).astype(np.uint8))

            seconds_read += chunk

        self.data = np.concatenate(arrays, axis=1)
        file.close()

    @property
    def duration_seconds(self):
        return self.sample_count / self.sample_rate

    def get_substream(self, start, end):
        start_off = self.to_number_of_samples(start)
        end_off = self.to_number_of_samples(end)
        return self.data[:, start_off:end_off]

    def to_number_of_samples(self, time):
        return int(self.sample_rate * time)

    def find_substream(self, pattern, **kwargs):
        start_time = max(kwargs.get('start_time', 0.0), 0.0)
        end_time = max(kwargs.get('end_time', self.sample_count), 0.0)

        start_sample = self.to_number_of_samples(start_time)
        end_sample = self.to_number_of_samples(end_time) + len(pattern[0])

        search_source = self.data[:, start_sample:end_sample]
        result = cv2.matchTemplate(search_source, pattern, cv2.TM_SQDIFF_NORMED)
        min_idx = result.argmin(axis=1)[0]

        return result[0][min_idx], start_time + (min_idx / float(self.sample_rate))