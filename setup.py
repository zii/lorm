#coding: utf-8
from setuptools import setup, find_packages

__version__ = '1.0.12'

setup(
    name         = "lorm",
    version      = __version__,
    keywords     = ['orm'],
    author       = "zii",
    author_email = "gamcat@gmail.com",
    url          = "https://github.com/zii/lorm",
    description  = "A light weight mysql client library.",
    long_description = open('README.rst').read(),
    license      = "MIT",
    classifiers=[
        'Development Status :: 5 - Production/Stable',
        'Intended Audience :: Developers',
        'Topic :: Software Development :: Libraries :: Application Frameworks',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3',
    ],
    install_requires = [],
    #py_modules = ['lorm'],
    packages = find_packages(),
)
