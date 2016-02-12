from distutils.core import setup
import os
try:
    import py2exe
except ImportError:
    pass
import sys

setup(
    name='Sushi',
    description='Automatic subtitle shifter based on audio',
    version='0.5.0',
    url='https://github.com/tp7/Sushi',
    console=['sushi.py'],
    license='MIT',
    options={
        'py2exe': {
            'compressed': True,
            'optimize': 2,
            "excludes": ["translation", "Tkconstants", "Tkinter", "tcl", 'pyreadline', 'email',
                         'numpy.core.multiarray_tests', 'numpy.core.operand_flag_tests', 'numpy.core.struct_ufunc_test',
                         'numpy.core.umath_tests', 'numpy.core._dotblas', 'matplotlib'],
            "dll_excludes": ['w9xpopen.exe', 'AVICAP32.dll', 'AVIFIL32.dll', 'MSACM32.dll', 'MSVFW32.dll'],
        }
    },
    zipfile='lib/library.zip',
    data_files=[
        ('', ('readme.md', 'LICENSE')),
        ('licenses', ('licenses/OpenCV.txt', 'licenses/SciPy.txt'))
    ]
)

try:
    dist_dir = next(sys.argv[i + 1].strip('"') for i, arg in enumerate(sys.argv) if arg.lower() == '-d')
except StopIteration:
    dist_dir = 'dist'

# move our license to the right directory
license_output_path = os.path.join(dist_dir, 'licenses', 'Sushi.txt')
if os.path.exists(license_output_path):
    os.remove(license_output_path)
os.rename(os.path.join(dist_dir, 'LICENSE'), license_output_path)

