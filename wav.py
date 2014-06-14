import logging
import cv2
import numpy as np
from chunk import Chunk
import struct
from time import time
import os.path
from common import SushiError

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
                raise SushiError('File does not start with RIFF id')
            if riff.read(4) != 'WAVE':
                raise SushiError('Not a WAVE file')

            fmt_chunk_read = False
            data_chink_read = False
            file_size = os.path.getsize(path)

            while True:
                try:
                    chunk = Chunk(self._file, bigendian=False)
                except EOFError:
                    break

                if chunk.getname() == 'fmt ':
                    self._read_fmt_chunk(chunk)
                    fmt_chunk_read = True
                elif chunk.getname() == 'data':
                    if file_size > 0xFFFFFFFF:
                        # large broken wav
                        self.frames_count = (file_size - self._file.tell()) // self.frame_size
                    else:
                        self.frames_count = chunk.chunksize // self.frame_size
                    data_chink_read = True
                    break
                chunk.skip()
            if not fmt_chunk_read or not data_chink_read:
                raise SushiError('Invalid WAV file')
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
        # always reads formats as unsigned to increase sample values range for better matching
        if not count:
            return ''
        data = self._file.read(count * self.frame_size)
        if self.sample_width == 2:
            unpacked = np.fromstring(data, dtype=np.int16)
        elif self.sample_width == 3:
            bytes = np.ndarray(len(data), 'int8', data)
            unpacked = np.zeros(len(data) / 3, np.int16)
            unpacked.view(dtype='int8')[0::2] = bytes[1::3]
            unpacked.view(dtype='int8')[1::2] = bytes[2::3]
        else:
            raise SushiError('Unsupported sample width: {0}'.format(self.sample_width))

        unpacked = unpacked.astype('float32')

        if self.channels_count == 1:
            return unpacked
        else:
            cc = self.channels_count
            arrays = [unpacked[i::cc] for i in range(cc)]
            return reduce(lambda a, b: a + b, arrays) / float(cc)

    def _read_fmt_chunk(self, chunk):
        wFormatTag, self.channels_count, self.framerate, dwAvgBytesPerSec, wBlockAlign = struct.unpack('<HHLLH',
                                                                                                       chunk.read(14))
        if wFormatTag == WAVE_FORMAT_PCM or wFormatTag == WAVE_FORMAT_EXTENSIBLE:  # ignore the rest
            bits_per_sample = struct.unpack('<H', chunk.read(2))[0]
            self.sample_width = (bits_per_sample + 7) // 8
        else:
            raise SushiError('unknown format: {0}'.format(wFormatTag))
        self.frame_size = self.channels_count * self.sample_width


class WavStream(object):
    READ_CHUNK_SIZE = 1  # one second, seems to be the fastest

    def __init__(self, path, sample_rate=12000, sample_type='uint8'):
        if sample_type not in ('float32', 'uint8'):
            raise SushiError('Unknown sample type of WAV stream, must be uint8 or float32')

        file = DownmixedWavFile(path)
        total_seconds = file.frames_count / float(file.framerate)
        downsample_rate = sample_rate / float(file.framerate)

        self.sample_count = int(total_seconds * sample_rate)
        self.sample_rate = sample_rate

        seconds_read = 0
        arrays = []
        before_read = time()
        while seconds_read < total_seconds:
            data = file.readframes(int(self.READ_CHUNK_SIZE * file.framerate))
            new_length = int(round(len(data) * downsample_rate))

            data = data.reshape((1, len(data)))
            if downsample_rate != 1:
                data = cv2.resize(data, (new_length, 1), interpolation=cv2.INTER_NEAREST)
            arrays.append(data)

            seconds_read += self.READ_CHUNK_SIZE

        data = np.concatenate(arrays, axis=1)

        # normalizing
        # also clipping the stream by 0.5 of max/min values to remove spikes
        max_value = np.mean(data[data >= 0]) * 4
        min_value = np.mean(data[data <= 0]) * 4

        data = np.clip(data, min_value, max_value)

        self.data = (data - min_value) / (max_value - min_value)

        if sample_type == 'uint8':
            self.data = np.round(self.data * 255.0).astype('uint8')

        file.close()
        logging.info('Done reading WAV {0} in {1}s'.format(path, time() - before_read))

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
