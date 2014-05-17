import cv2
import numpy as np
from scipy.io import wavfile
from chunk import Chunk
import struct

WAVE_FORMAT_PCM = 0x0001
WAVE_FORMAT_EXTENSIBLE = 0xFFFE

class WavFile(object):
    def __init__(self, path):
        super(WavFile, self).__init__()
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
        if self.sample_width == 2:
            return self._data_chunk.read(count * self.frame_size)
            # return struct.unpack('<{0}h'.format(count*self.channels_count), data)
        elif self.sample_width == 3:
            s = ''
            for x in xrange(count):
                frame = self._data_chunk.read(self.frame_size)
                for c in xrange(0,3*self.channels_count, 3):
                    s += '\0' + frame[c:(c+3)]

            unpacked = struct.unpack('<{0}i'.format(count*self.channels_count), s)
            return [x >> 8 for x in unpacked]


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


# file = WavFile(r"H:\!Ongoing\shiftass\maou\[FFF] Hataraku Maou-sama! - 01 [DEF4B21E].wav")
# file = WavFile(r"H:\[ANE] Koe de Oshigoto! [BDRip 1080p x264 FLAC]\[ANE] Koe de Oshigoto! - Creditless Opening [BDRip 1080p x264 FLAC].wav")
# print(file.getsampwidth())
# c = file.readframes(file.frames_count)
# print(len(c))
# print(file.readframes(10000))
#
# def write_wav(float_array, sample_rate, path):
#     data = (float_array * 32768.0).astype(np.int16)
#     wavfile.write(path, sample_rate, data[0])
