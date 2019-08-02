#!/bin/bash

adb shell dumpsys activity activities | grep -A 1 -m 1 "* TaskRecord{" | grep -o "effectiveUid=u0a[[:digit:]]\+" | grep -o "[[:digit:]]\+$" | xargs printf "1%04d"
