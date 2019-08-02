#!/usr/bin/perl -w
use strict; use warnings;
use List::Util qw(sum);
use List::Util qw(min);
use List::Util qw(max);

my $NSECS = 3600;#60*60; # *operational* seconds we want the disk to live
my $T_start = 0; # time device turned on (assume always operational)
my $T_end = $T_start + $NSECS; # time it's okay for device to die
my $BASE_CREDIT = 5;
my $MAX_NEW_APPS = 10;
my $W_max = 5000 - ($MAX_NEW_APPS * $BASE_CREDIT); # MBs we can write to disk before it's bricked, minus credit for new apps
my $GLOBAL_CREDIT = 0; # everyone can draw from global unsed credit

my $IDLE_RATE = 0.8; # % of device time spent in idle mode (no apps running)
my $SLK_RATE = 0.3; # slack as rate of $W_max
my $SLK = $W_max * $SLK_RATE; # slack bytes

my $Wtag_max = $W_max - $SLK; # MBs when factoring slack and new app credit into $W_max
my $B = $W_max / $NSECS; # MBs/sec bandwidth, when not allowing slack
my $Btag = $Wtag_max / $NSECS; # MBs/sec bandwidth, when we *do* allow slack
my $N_APPS = 2; # apps running in system
my $MAX_TPUT = 100; # MBs/sec max throughput of disk
my $W_t = 0; # MBs written till time t ($T_start<=t<$T_end)
my $BURST_SECS = 6; # seconds per average app session
my $MAX_SMALL_BURST = 15;
my $NO_BURSTS = -1;
my $MAX_SAVING_PERIOD = $NSECS / 4; # arbitray for now

my $SEC_SLACK = $SLK / $NSECS; # per-sec credit

my $ACTIVE = 0;
my $BACKGROUND = 1;
my $IDLE = 2;
#-------------------------------------------------------------------------------
# credit based rate-limiting version
#-------------------------------------------------------------------------------

package App;

{
    sub new {
        my $class = shift;

        # Average I/O rate of app in MB/s. Assuming:
        # (1) app I/O rate is known from either database/sampling
        # (2) rate is 0.1, 0.5, or malicious
        # (3) apps with 0.5 rate display occasional bursts
        my $rate = shift;
        my $sleepy = shift; # % of time app doesnt run at all
        my $bg = shift; # % of time running in background
        my $bg_factor = shift; # I/O rate in background (% of foreground rate)
        my $burst = shift;

        if ($burst > 0) {
            my $nonactive_slack = ($burst - 1)/$burst;
            $bg += (1-$bg-$sleepy) * $nonactive_slack;
            $sleepy += (1-$sleepy) * $nonactive_slack;
            printf("sleepy %f bg %f\n", $sleepy, $bg);
        }

        # credit is accumulated according to rate as higher bandwidth apps
        # require more intensive bursts
        my $credit = $BASE_CREDIT;
        my $runtime = ($rate == 0.5)?$burst:$NO_BURSTS;
        my $self = {rate => $rate, credit => $credit, runtime => $runtime,
                    orig_rate => $rate, unhappiness => 0.0, demand => 0.0,
                    drag => 0.0, withdrawl => 0.0,bg_withdraw => 0.0,
                    sleepy => $sleepy,uptime => 0,
                    bg_factor => $bg_factor, bg => $bg, bgtime => 0,
                    status => $IDLE, burst=>$burst };
        bless $self;

        return $self;
    }

    sub game {
        return new
    }

    # top up active apps according to their base rate.
    # non-IO-intensive apps save just enough for one burst
    sub topup {
        my $self = shift;
        my $howmuch = shift;

        die "bug" if $howmuch < 0;
        $self->{credit} += $howmuch;
    }

    # make credit withdraw
    sub withdraw {
        my $self = shift;
        my $howmuch = shift;

        $self->{credit} -= $howmuch;
        die "bug" if $self->{credit} < 0;
        $self->{withdrawl} += $howmuch;

        if ($self->{status} == $BACKGROUND) {
            $self->{bg_withdraw} += $howmuch;
        }
    }

    # get credit balance
    sub balance {
        my $self = shift;

        return $self->{credit};
    }

    sub getRate {
        my $self = shift;

        return $self->{rate};
    }

    sub adjustWithdrawl{
        my $self = shift;
        my $ret = shift;
        my $io_factor = ($W_max-$GLOBAL_CREDIT-$self->{bg_withdraw}) /
            ($W_max-$GLOBAL_CREDIT);
        # penalize for background IO-intensiveness
        # note, we do not penalize for time. many low-rate apps (e.g., whatsapp)
        # are constantly active

        $ret *= ($io_factor);
        # and penalize for constant background work
        #$ret *= ($NSECS - $self->{bgtime}) / $NSECS;

        return $ret
    }

    sub globalTopup{
        my $self = shift;
        my $global_withdraw = $self->getRate() - $self->balance();

        if ($GLOBAL_CREDIT < $global_withdraw) {
            $global_withdraw = $GLOBAL_CREDIT;
        }

        $global_withdraw = $self->adjustWithdrawl($global_withdraw);
        $GLOBAL_CREDIT -= $global_withdraw;
        $self->{credit} += $global_withdraw;

        die "bug" if $GLOBAL_CREDIT < 0;
        return $global_withdraw;
    }

    sub calc_adjusted_rate {
        my $self = shift;
        my $wants = $self->getRate();
        my $ret = $wants;

        # small reward for idleness relative to I/O rate.
        # (should consider higher reward for frequently operated apps)
        if ($wants == 0) {
            return $self->{orig_rate} / 20;
        }

        # adjsut for malicious apps
        $ret = $wants;
        if ($wants > 0.5) {
            $ret = 0.5;
        }

        $ret = $self->adjustWithdrawl($ret);

        return $ret;
    }

    sub getOrigRate {
        my $self = shift;

        return $self->{orig_rate};
    }

    sub getWithdrawl {
        my $self = shift;

        return $self->{withdrawl};
    }

    # get rate.
    # assumes this gets called on every second's start
    sub nextSecondRate {
        my $self = shift;

        $self->{status} = $ACTIVE; # default active

        # set status
        if (rand(1) <= $self->{bg}){
            $self->{status} = $BACKGROUND;
            $self->{bgtime}++;
        }
        elsif ((rand(1)<= $self->{sleepy})){
            $self->{status} = $IDLE;
        }

        # handle drag first
        if ($self->{drag} > 0){
            $self->{rate} = $self->{drag};
            $self->{drag} = 0;
            goto DEMAND;
        }
        else {
            # no drag, get normal rate and continue according to status
            $self->{drag} = 0;
            $self->{rate} = $self->{orig_rate};
        }

        # middle of active run, skip rate adjustment for background/idle
        if ($self->{runtime} < $self->{burst} and $self->{runtime} >0) {
            goto RUNNING;
        }

        # background run
        if ($self->{status} == $BACKGROUND) {
            $self->{rate} *= $self->{bg_factor};
            goto DEMAND;
        }
        # idle time
        elsif ($self->{status} == $IDLE) {
            $self->{rate} = 0;
            goto DEMAND;
        }

RUNNING:
        # app is active! check for bursts
        if ($self->{runtime} == $NO_BURSTS){
            goto DEMAND;
        }

        $self->{runtime}--;

        if ($self->{runtime} % $BURST_SECS == 0){
            $self->{rate} = $MAX_SMALL_BURST;

            if ($self->{runtime}==0){
                $self->{runtime} = $self->{burst};
            }
        }
        else {
            $self->{rate} = $self->{orig_rate};
        }

DEMAND:
        $self->{demand} += $self->{rate};
    }

    sub addUnhappiness {
        my $self = shift;
        my $sad = shift;

        $self->{unhappiness} += $sad;
    }

    sub getUnhappiness{
        my $self = shift;
        my $sad = $self->{unhappiness};

        return $sad / $self->{demand};
    }
}

package main;

# init apps with <rate, sleepy, bg, bg_factor>
sub init_low_rate{
    return new App->new(0.1, 0.99, 0, 0.5, $NO_BURSTS);
}

sub init_social{
    return new App->new(0.1, 0, 0.9, 0.2, $NO_BURSTS);
}

sub init_camera{
    return new App->new(0.5,0.95, 0, 0, 7);
}

sub init_game{
    return new App->new(0.5,0.2, 0.9, 0.5, 60);
}


sub init_malicious{
    return new App->new($MAX_TPUT, 0.0, 1, 1, $NO_BURSTS);
}

sub app_credit_based_dos{
    # Design aims for the common case;
    # i) several low-rate apps (0.1 MB/s)
    # ii) at most one high-rate app (0.5MB/s) with occasional bursts
    # iii) device is mostly left idle (no apps running)
    # malicious apps will prevent device from going idle, and cause high-rate
    # apps to starve. however, low-rate apps should still be (mostly) OK
    #
    # Implemnetation:
    # treat B = Btag + SEC_SLACK as time-unit credit to be distributed between
    # all apps.
    # if apps require >= B, then B is distributed as credit between all apps.
    # otherwise, we distribute whatever they need, the rest is saved to global
    # credit (which all apps can later use)
    #
    # Assume:
    # (i) non-served I/O does not linger
    my $testnum =shift;
    my @apps = (); #map { new App->new($MAX_TPUT) } 1..$NAPPS;
    open(my $fh, '>', 'report.csv');
    my $i=0;

    # Init low-rate apps
    $N_APPS = 1;
       if (1){
    $N_APPS = 20;
    for(; $i < $N_APPS-3; $i++) {
       $apps[$i] = init_low_rate();
        printf $fh "low-rate,,,,";
    }

    # low-rate social media app (constant background)
    for(; $i < $N_APPS-1; $i++) {
        $apps[$i] = init_social();
        printf $fh "social,,,,";
    }
}
    # Init high-rate game app
    $apps[$N_APPS-1] = init_game();
    printf $fh "game,,,,";

    if ($testnum == 1) {
        # Init malicious app (active in background)
        $apps[0] = init_malicious();
        printf $fh "malicious,,,,";
    }
    elsif ($testnum == 2) {
        # Init malicious app (active in background)
        $apps[0] = init_malicious();
        printf $fh "malicious,,,,";
        $apps[1] = init_malicious();
        printf $fh "malicious,,,,";
    }
    printf $fh "\n";
    for($i = 0; $i < $N_APPS; $i++) {
        printf $fh "rate,withdraw,credit,,";
    }
    printf $fh "\n";
    # Now allocate IO rates and credit per top running apps (==APPS).
    printf("W_max %d Btag %.3f SEC_SLACK %.3f\n", $W_max, $Btag, $SEC_SLACK);

    # start running the clock
    # assume same apps always running for now
    for(my $t=$T_start; $t < $T_end; $t++) { # time secs
        my $t_credit = $B; # time-unit additional bandwidth
        my $write_bytes = 0;

        # update rate for apps
        foreach my $x (@apps) {
            $x->nextSecondRate();
        }

        # 1. calc app I/O demand of all running apps in the next second
        my @adjusted_demand = ();
        my @real_demand = ();
        for(my $i=0; $i < $N_APPS; $i++) {
            $adjusted_demand[$i] = $apps[$i]->calc_adjusted_rate();
            #printf(" adjusted_demand[i] %.3f ", $adjusted_demand[$i]);
            $real_demand[$i] = $apps[$i]->getRate();
        }
        my $total_demand = sum(@real_demand);

        # if demand > MAX_TPUT --> factor real demand
        if ($total_demand > $MAX_TPUT) {
            foreach my $x (@real_demand) { $x *= ($MAX_TPUT / $total_demand);}
        }

        # whatever is left from Btag save to global credit.
        if ($total_demand < $Btag) {
            my $global_save = ($Btag - $total_demand);
            $t_credit -= $global_save;
            $GLOBAL_CREDIT += $global_save;
        }

        # 2. allocate remaining time-unit bandwidth proportionally according
        #    to *adjusted* demand (to avoid over-allocating to malicious app)
        foreach my $x (@apps) {
            my $save = $t_credit * $x->calc_adjusted_rate() /
                sum(@adjusted_demand);
            $x->topup($save);
            die "bug" if $x->balance() < 0;
        }

        # 3. now handle actual writing
        for(my $i=0; $i < $N_APPS; $i++) {
            my $rate = $real_demand[$i];
            my $withdraw = $rate; # by default we withdraw as much as possible

            # app not performing any writes
            if ($rate == 0){
                #printf $fh "%.3f,%.3f,%.3f,%.3f,,", $apps[$i]->balance(), $withdraw, $rate, $apps[$i]->{drag};
                printf $fh "%.3f,%.3f,%.3f,,", $rate,$withdraw,$apps[$i]->balance();
                next;
            }

            # check if app has enough credit. if not, withdraw from
            # global account (naively according to app order for now)
            if ($rate > $apps[$i]->balance()) {
                $apps[$i]->globalTopup(); # top up from global credit

                # here's where we rate limit.
                $withdraw = $apps[$i]->balance();
                die "bug" if $withdraw < 0;
                # update unhappiness
                $apps[$i]->addUnhappiness($rate - $withdraw);
                $apps[$i]->{drag}+=$rate - $withdraw;
            }
            printf("%d) app %d (status %d): credit %.3f wrote %.3f rate %.8f drag %.3f (adjusted_demand %.3f GLOBAL_CREDIT %d)\n", $t,
                $i, $apps[$i]->{status}, $apps[$i]->balance(), $withdraw,
                $apps[$i]->getRate(), $apps[$i]->{drag}, $adjusted_demand[$i],
                $GLOBAL_CREDIT);

            # finally, make withdraw from app's account
            $apps[$i]->withdraw($withdraw);
            $write_bytes += $withdraw;
            #printf $fh "%.3f,%.3f,%.3f,%.3f,,", $apps[$i]->balance(), $withdraw, $rate, $apps[$i]->{drag};
            printf $fh "%.3f,%.3f,%.3f,,", $rate, $withdraw,$apps[$i]->balance();
            die "bug" if $rate - $withdraw < 0;
        }

        $W_t += $write_bytes;
        printf $fh "\n";
    }

    close $fh;
    printf("W_t=%7.1f (GLOBAL_CREDIT %d)\n", $W_t, $GLOBAL_CREDIT);
    print "done\n";
}

app_credit_based_dos(shift);
