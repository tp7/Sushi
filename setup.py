from distutils.core import setup
import sushi

setup(
    name='Sushi',
    description='Automatic subtitle shifter based on audio',
    version=sushi.VERSION,
    url='https://github.com/tp7/Sushi',
    console=['sushi.py'],
    license='MIT'
)
