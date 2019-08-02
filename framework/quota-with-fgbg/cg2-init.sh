#!/bin/bash

source cg2-env.sh

mkdir -p $CG2_ROOT > /dev/null

grep "$CG2_ROOT" /proc/mounts || mount -t cgroup2 none $CG2_ROOT

echo "+io +memory" > $CG2_ROOT/cgroup.subtree_control

