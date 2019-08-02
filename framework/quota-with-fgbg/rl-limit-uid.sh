#!/bin/bash

source rl-env.sh

if [ $# -lt 2 ]
then
	echo -e "Usage:\n\t$0 UID RATE"
	exit 1
fi

RL_UID=$1
RATE=$2

echo "Move all UID \"$RL_UID\" processes to rate-limiting $RATE..."

echo "$RL_UID $RATE" > $RL_ROOT

