from setuptools import setup
import sushi

setup(
    name='Sushi',
    description='Automatic subtitle shifter based on audio',
    packages=['sushi'],
    version=sushi.VERSION,
    url='https://github.com/tp7/Sushi',
    license='MIT',
    entry_points={
        'console_scripts': [
            "sushi=sushi.__main__:main",
        ],
    },
)
