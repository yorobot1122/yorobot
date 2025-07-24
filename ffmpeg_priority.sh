#!/bin/bash
# ffmpeg_priority.sh

# -n -5: ffmpeg 프로세스의 우선순위를 높임 (낮을수록 높음)
# "$@": 파이썬 코드에서 전달된 모든 인자(옵션, 주소 등)를 그대로 전달
nice -n -5 /home/ubuntu/yorobot/ffmpeg "$@"
