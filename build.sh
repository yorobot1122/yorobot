#!/bin/bash
mkdir -p bin
curl -L https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz | tar -xJ
mv ffmpeg-*-static/ffmpeg ./bin/ffmpeg
chmod +x ./bin/ffmpeg
