#!/bin/bash

echo > /proc/diskstats_uid_global

cat /proc/ratelimit_uid | awk '{printf("%d %d\n", $1, -1)}' | while read line
do
	echo $line > /proc/ratelimit_uid
done
