#!/bin/bash


adb shell "su -c 'cat /data/system/packages.list'" > packages.list
