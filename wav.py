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
            min_length = len(unpacked) // self.channels_count
            real_length = len(unpacked) / float(self.channels_count)
            if min_length != real_length:
                logging.error("Length of audio channels didn't match. This might result in broken output")

            channels = (unpacked[i::self.channels_count] for i in xrange(self.channels_count))
            data = reduce(lambda a, b: a[:min_length]+b[:min_length], channels)
            data /= float(self.channels_count)
            return data

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
        self.data = np.empty((1, self.sample_count), np.float32)

        before_read = time()
        try:
            seconds_read = 0
            samples_read = 0
            while seconds_read < total_seconds:
                data = file.readframes(int(self.READ_CHUNK_SIZE * file.framerate))
                new_length = int(round(len(data) * downsample_rate))

                dst_view = self.data[0][samples_read:samples_read+new_length]

                if downsample_rate != 1:
                    data = data.reshape((1, len(data)))
                    data = cv2.resize(data, (new_length, 1), interpolation=cv2.INTER_NEAREST)[0]

                np.copyto(dst_view, data, casting='no')
                samples_read += new_length
                seconds_read += self.READ_CHUNK_SIZE

            # normalizing
            # also clipping the stream by 3*median value from both sides of zero
            max_value = np.median(self.data[self.data >= 0], overwrite_input=True) * 3
            min_value = np.median(self.data[self.data <= 0], overwrite_input=True) * 3

            np.clip(self.data, min_value, max_value, out=self.data)

            self.data -= min_value
            self.data /= (max_value - min_value)

            if sample_type == 'uint8':
                self.data *= 255.0
                self.data += 0.5
                self.data = self.data.astype('uint8')

        except Exception as e:
            raise SushiError('Error while loading {0}: {1}'.format(path, e))
        finally:
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
