import os
from setuptools import setup, find_packages

# Read the contents of README.md
this_directory = os.path.abspath(os.path.dirname(__file__))
with open(os.path.join(this_directory, 'README.md'), encoding='utf-8') as f:
    long_description = f.read()

# This setup is for the Visualization component (visbox)
setup(
    name="athena-rods-vis",
    version="0.1.2",
    description="ATHENA-rods visualization client",
    long_description=long_description,
    long_description_content_type='text/markdown',
    author="Ondrej Chvala",
    author_email="ochvala@utexas.edu",
    packages=find_packages(where="src", include=['arod_visual', 'arod_control']),
    package_dir={"": "src"},
    install_requires=[
        "dash",
        "plotly",
        "numpy<2",
        "scipy",
    ],
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Framework :: Dash",
    ],
)
