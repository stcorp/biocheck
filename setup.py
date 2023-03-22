from setuptools import setup

setup(
    name='biocheck',
    version='1.0',
    description='BIOMASS Product Internal Consistency Checker',
    author='S[&]T',
    license='BSD',
    py_modules=['biocheck'],
    entry_points={'console_scripts': ['biocheck = biocheck:main']},
    install_requires=['lxml'],
)
