#!/bin/bash

source cg2-env.sh

echo > /proc/diskstats_uid_global

find $CG2_ROOT -mindepth 1 -type d -exec rmdir {} \;
