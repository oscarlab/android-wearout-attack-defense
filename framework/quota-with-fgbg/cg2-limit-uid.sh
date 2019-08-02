#!/bin/bash

source cg2-env.sh

if [ $# -lt 2 ]
then
	echo -e "Usage:\n\t$0 UID RATE"
	exit 1
fi

CG2_UID=$1
RATE=$2

CG2_UID_PATH="rl-$CG2_UID"

echo "Move all UID \"$CG2_UID\" processes to rate-limiting $RATE..."

if [ ! -d $CG2_ROOT/$CG2_UID_PATH ]
then
	echo -n "No CG2 group for $CG2_UID found, creating..."
	mkdir -p $CG2_ROOT/$CG2_UID_PATH
	echo "done"
fi

echo "$BLOCK_DEV wbps=$RATE" > $CG2_ROOT/$CG2_UID_PATH/io.max

for pid in `ps auxn | grep "^[[:space:]]*$CG2_UID " | awk '{ print $2 }'`
do
	echo "Found PID $pid"
	for tid in `ls /proc/$pid/task/`
	do
		echo "Found TID $tid"
		echo $tid > $CG2_ROOT/$CG2_UID_PATH/cgroup.procs
	done
done

