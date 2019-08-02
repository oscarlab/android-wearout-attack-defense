#!/usr/bin/perl -w
use strict;
use List::Util qw(max);

my $NSECS = 10;	      		# *operational* seconds we want the disk to live
my $T_start = 0;		# time device turned on (assume always operational)
my $T_end = $T_start + $NSECS;	# time it's okay for device to die
my $W_max = 1000;		# bytes we can write to disk before it's bricked
my $SLK_RATE = .03;		# slack as rate of $W_max
my $SLK = $W_max * $SLK_RATE;	# slack bytes 
my $Wtag_max = $W_max - $SLK;	# bytes when factoring slack into $W_max
my $B = $W_max / $NSECS;	# bytes/sec bandwidth, when not allowing slack
my $Btag = $Wtag_max / $NSECS;	# bytes/sec bandwidth, when we *do* allow slack
my $NCORES = 3;			# cores in system
my $MAX_TPUT = $B*5;		# bytes/sec max throughput of disk, per core
my $W_t = 0;			# bytes written till time t ($T_start<=t<$T_end)

#-------------------------------------------------------------------------------
# v1: simplest correct rate-limiting version, which is susceptible
# to the trivial DOS attack of using all slack immediately and thus
# causing all apps to be rate-limited forever.
#-------------------------------------------------------------------------------
sub simplest_but_vulnerable_to_dos() {

    # let's simulate a case whereby all phone cores are busy running
    # malicious apps that want to write the maximal disk throughput
    # ($MAX_TPUT) all the time, assuming (i) the disk is performant
    # enough to accommodate that, yet (ii) the rate-limiting policy
    # still needs to cap (and indeed does cap) the write activity
    # volume, so as to ensure that the device will live for at least
    # $NSECS.
    
    for(my $t=$T_start; $t < $T_end; $t++) { # time secs

	# num of bytes all running apps want to write in the next second
	my $want_bytes = $MAX_TPUT * $NCORES;

	# num of bytes all said apps are allowed to write during
        # the next second, due to the rate limiting policy
	my $allowed_bytes = ($t + 1 - $T_start)*$Btag + $SLK - $W_t; 
	die "bug" if $allowed_bytes < 0;

	# here's where we rate limit
	my $write_bytes = 
	    $want_bytes < $allowed_bytes ? $want_bytes : $allowed_bytes;
	$W_t += $write_bytes;

	# and here's were we see how our simplistic simulation progresses
	printf("%3d: write_bytes=%7.1f W_t=%7.1f\n", $t, $write_bytes, $W_t);
    }
}

#-------------------------------------------------------------------------------
# main:
#-------------------------------------------------------------------------------
simplest_but_vulnerable_to_dos();