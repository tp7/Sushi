## ShiftAss ##
Script for shifting subtitles based on audio streams.

### Declaimer ###
This script is in super early alpha stage so don't expect it to handle any complicated cases or malformed input, have nice error reporting or super advanced features. It is provided with hope to find some users. If none will be found, I will shut the project down.

I'm not a Python programmer. The code is a mess.

### Purpose
Imagine you've got a subtitle file synced to one video file, but you want to use these subtitles with some other video you've got via totally legal ways. The common example is TV vs. BD releases, PAL vs. NTSC video and releases in different countries. In a lot of cases, subtitles won't match right away and you need to sync them.

The purpose of this script is to avoid all the hassle of manual syncing. It attempts to synchronize subtitles by finding similarities in audio streams. The script is very fast (not counting a few seconds to load large WAV files) and can be used right when you want to watch something.

### How it works
You need to provide two audio files and a subtitle file (currently only .ASS) that matches one of those files. For every line in the subtitles, the script will extract corresponding audio from the source audio stream and will try to find the closest similar pattern in the destination audio stream. The shift found will be applied to the subtitles.

During loading, both audio streams will be downsampled and converted to internal representation suitable for OpenCV. You can control downsampling with `--sample-rate` and `--sample-type` arguments, however it's not recommended to touch these values unless you get some problems with the defaults (12Hz, float32 samples).

Of course it won't search the whole stream for every line. Instead, a small window (2 seconds in every direction, 4 total) is searched first, centered at the `original time + shift of the last line` position. If the script cannot find a reasonably good match in this window, it increases the search area to a larger value (20 seconds total by default) and attempts to search again, but this time the closest found match will be considered correct. You can control the size of the larger search window using the `--window` argument.

Also, the script won't attempt to search for a line if a line with identical start and end times has been already processed. This is very useful for typesetting and can significantly improve performance, but you can still disable it with the `--no-fast-skip` switch.

Then, the script will try to split all lines into groups. It can either try to build these groups automatically (lines with similar shift are grouped), or get them from XML chapters, provided with `--chapters` argument. This is done because it is very unlikely for every line to have its own shift (unless there's some frame rate problems). Shift values of all events in every group are used to calculate weighted average (where weight is the coefficient of similarity of audio streams, calculated before), which is then applied to every line on the group. Of course you can disable grouping with `--no-grouping` switch.

### Usage
The minimal command line looks like this:
```
python shiftass.py --src-audio hdtv.wav --dst-audio bluray.wav -o output.ass subtitles.ass
```

### Requirements
For the time being, the script is provided as-is. I don't know what exact versions you need to run it, but here's my environment:

1. Windows, but it probably will run on most other operation systems
2. [Python 2.7.6][1] (won't run on 3.x)
3. [SciPy 0.14.0][2]
4. [NumPy 1.8.1][3]
5. [OpenCV 2.4.9][4] (only `imgproc` module is used)


### Limitations
Only ASS scripts and XML chapters are supported right now. Only WAV audio files can be read, this script will not be able to decode anything. 24-bit WAVs and large WAVs  will most likely fail because the script tries to load the whole file at once (if this happens, you can try `--sample-type uint8` to save some RAM). I'm testing it on 25 minutes 300MB WAV files.

No keyframes snapping is performed.  

This script will never be able to property handle frame-by-frame typesetting. If underlying video stream changes (e.g. has different telecine pattern), you might get incorrect output.

In short, while this might be safe for immediate viewing, you probably shouldn't use it to blindly shift subtitles for permanent storing.


  [1]: https://www.python.org/download/releases/2.7.6/
  [2]: http://www.scipy.org/
  [3]: http://www.numpy.org/
  [4]: http://opencv.org/