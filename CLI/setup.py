from setuptools import setup, find_packages
import os

# Read requirements.txt
with open('requirements.txt') as f:
    required = f.read().splitlines()

# Read README.md
long_description = ""
if os.path.exists("README.md"):
    with open("README.md", "r", encoding="utf-8") as fh:
        long_description = fh.read()

setup(
    name="multivol",
    version="0.1.3",
    description="MultiVolatility: Analyze memory dumps faster than ever with Volatility2 and Volatility3 in parallel using Docker",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/BoBNewz/MultiVolatility", 
    packages=find_packages(),
    install_requires=required,
    entry_points={
        "console_scripts": [
            "multivol=multivol.multivol:main",
        ],
    },
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires='>=3.6',
    include_package_data=True,
)
