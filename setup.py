#!/usr/bin/env python

#
# Copyright (c) 2013, Digium, Inc.
#

"""Setup script
"""

import os

from setuptools import setup

setup(
    name="swaggerpy",
    version="0.3.0",
    license="BSD 3-Clause License",
    description="Library for accessing Swagger-enabled API's",
    long_description=open(os.path.join(os.path.dirname(__file__),
                                       "README.rst")).read(),
    author="Alexander Efremov",
    author_email="pulsar314@gmail.com",
    url="https://github.com/pulsar314/swagger-py",
    packages=["swaggerpy"],
    classifiers=[
        "Development Status :: 1 - Planning",
        "Intended Audience :: Developers",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "License :: OSI Approved :: BSD License",
        "Operating System :: OS Independent",
        "Programming Language :: Python",
    ],
    install_requires=["tornado"],
)
