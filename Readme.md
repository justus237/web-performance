### Introduction
This repository features scripts to perform Web and YouTube performance measurements using different DNS protocols.
### Installation
- Download and start modified DNS Proxy: https://github.com/justus237/dnsproxy
- Install Python 3.X requirements: `pip install -r requirements.txt` (only tested with Python 3.8)
### Usage
- Run `run_youtube_measurements.sh`, which starts `DNS proxy` and runs `youtube_measurement.py`
### Hardcoded values to watch out for
- The filepaths in the shell script are hardcoded for the user `ubuntu`
- The target list of DNS resolvers to measure must be placed in `servers.txt`
