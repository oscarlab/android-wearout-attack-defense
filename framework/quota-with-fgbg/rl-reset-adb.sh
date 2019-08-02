#!/bin/bash

adb shell "su -c 'echo > /proc/diskstats_uid_global'"

adb shell "su -c 'echo "-1 0" > /proc/ratelimit_uid'"
