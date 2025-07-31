#!/bin/bash
curl -L https://github.com/ffbinaries/ffbinaries-prebuilt/releases/download/v4.3/ffmpeg-linux-64.zip -o ffmpeg.zip
unzip ffmpeg.zip
mkdir -p bin
mv ffmpeg bin/
chmod +x bin/ffmpeg
export PATH=$PATH:$(pwd)/bin
python3 main.py
