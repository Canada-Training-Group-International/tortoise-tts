#!/bin/bash
echo ''
cd "$(dirname "$0")"
cd ..
echo $(pwd)
echo 'running'
ls /home/ec2-user/tortoise-tts/env/bin/python -lh
/home/ec2-user/tortoise-tts/env/bin/python -u -m braincoins.queueClient -l
echo 'finished'


