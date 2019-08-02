#!/bin/bash

#set -x

adb shell dumpsys display | grep "mGlobalDisplayState=ON" >/dev/null || { echo -n -1; exit; }

TASK_RECORD=`adb shell dumpsys activity activities | grep -A 1 -m 1 "* TaskRecord{"`

APP_STRING=`echo "$TASK_RECORD" | grep -o "effectiveUid=u0a[[:digit:]]\+"`

if [ $? -eq 0 ]
then
	echo "$TASK_RECORD" | grep -o "effectiveUid=u0a[[:digit:]]\+" | grep -o "[[:digit:]]\+$" | xargs printf "1%04d"
else
	echo "$TASK_RECORD" | grep -o "effectiveUid=[[:digit:]]\+" | grep -o "[[:digit:]]\+$"
fi
