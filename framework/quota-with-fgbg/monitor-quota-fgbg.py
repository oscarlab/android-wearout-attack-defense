#!/usr/bin/env python3

import sys
import time
import json
import signal
import os
import matplotlib
matplotlib.use('agg')
import matplotlib.pyplot as pyplot
import numpy
from subprocess import call
from subprocess import Popen
from subprocess import PIPE
from subprocess import run
import time

KEEP_UID_STATS_HISTORY = False

PLOT_ONLY = False
PLOT_PER_UID = False
PLOT_OUTPUT_JSON = True
PLOT_UID_SLACK = True

# Environment parameters
UID_DKSTATS = '/proc/diskstats_uid_global'
DB_FILE='uid_stats_data.json'
#WHITELIST = ['0', '104', '105', '1000'] # don't play with these uids
WHITELIST = [] # don't play with these uids

SERVICE_TABLE = {
    '10040': ['1013']
}

# Policy parameters
INTERVAL = 1
# sample length
NSECS = 360
# Estimated lifetime I/O in KiB
W_max = 88 * 1024 * 1024 * 1024
# Desired lifetime in seconds
LIFE_SEC = 2 * 365 * 24 * 3600

QUOTA_PERIOD_BG = 3600
QUOTA_PERIOD_FG = 3600 * 24
RATELIMIT_THRESHOLD_RATE_FG = 0.5
RATELIMIT_THRESHOLD_RATE_BG = 0.5

SLK_RATE = 0.5
SLK = W_max * SLK_RATE

B = W_max / LIFE_SEC

# Delay when update foreground uid
DELAY_UPDATE_FG_UID = 5

current_fg_uid = '-1'
current_fg_uid_delay = 0

# Selector for host-side ratelimit mechanisms
HOST_RATELIMIT_DUMB     = 0
HOST_RATELIMIT_CGROUP1  = 1
HOST_RATELIMIT_CGROUP2  = 2
HOST_RATELIMIT_RL       = 3
HOST_RATELIMIT_RL_ADB       = 4

# HOST_RATELIMIT_CGROUP2 related
HOST_RATELIMIT_CGROUP2_CMD = "./cg2-limit-uid.sh"

# HOST_RATELIMIT_RL related
HOST_RATELIMIT_RL_CTRL_CMD = "./rl-limit-uid.sh"

# HOST_RATELIMIT_RL_ADB related

host_ratelimit_type = HOST_RATELIMIT_DUMB

if host_ratelimit_type == HOST_RATELIMIT_RL_ADB:
    print("Skip opening local stats file for adb")
elif host_ratelimit_type == HOST_RATELIMIT_DUMB:
    print("Skip opening local stats file for adb")
else:
    f = open(UID_DKSTATS, 'r')

if len(sys.argv) > 1:
    JSON_PREFIX="%s-" % (sys.argv[1])
else:
    JSON_PREFIX=""

previous_stats = {}
uid_birthday = {}
uid_name = {}

hist_bw = {}
hist_total_bw = []
hist_total_bw_fg = []
hist_total_bw_bg = []
hist_stats = {}

w_left = W_max
iteration_count = 0
num_uniq_uid = 0
uid_prison = []
uid_prison_rate = {}
checkpoint_bg = 0
slack_left = SLK

checkpoint_fg = 0
life_left_fg = LIFE_SEC

hist_slack_period_fg = []
hist_slack_period_bg = []
hist_watermark_fg = []
hist_watermark_bg = []
hist_uid_slack_fg = {}
hist_uid_slack_bg = {}
hist_uid_limit = {}

HALT=False

call(['rm', '-f', '/tmp/_WORKLOAD_STARTUP'])

print("Monitor started!\nW_max %.2f GiB, LIFETIME %.2f days, SLACK %.2f GiB, B %.2f KiB/s" %
    (W_max/1024/1024, LIFE_SEC/3600/24, SLK/1024/1024, B))

try:
    json_file = open(DB_FILE, 'r')
    print("previous stats file found")
    uid_db = json.load(json_file)
    json_file.close()
    for uid, data in uid_db.items():
        previous_stats[uid] = data[1]
        uid_birthday[uid] = data[0]
        uid_name[uid] = data[2]
        num_uniq_uid += 1

except IOError:
    print("no previous stats file found")

# TODO: Apply previous_stats into future stats (need a working birthday management)
print(previous_stats)

current_stats_dict = {}

def uid_to_name(_uid):
    if _uid in uid_name:
        return uid_name[_uid]
    else:
        return _uid

def signal_handler(signal, frame):
    HALT=True
    print("signal %d received" % signal)
    print(frame)
    if KEEP_UID_STATS_HISTORY:
        print('preparing uid stats data...')
        new_uid_db = {}
        for uid, birthday in uid_birthday.items():
            stats = previous_stats.get(uid, 0) + current_stats_dict.get(uid, 0)
            new_uid_db[uid] = [birthday, stats, uid_to_name(uid)]
        print('Writing out uid stats file...')
        json_file = open(DB_FILE, 'w')
        json.dump(new_uid_db, json_file)
        json_file.close()
        print('done')

    if PLOT_OUTPUT_JSON:
        timestamp = "%.0f" % time.time()
        print('Outputing hist_bw...')
        json_file = open("%shist_bw-%s.json" % (JSON_PREFIX, timestamp), 'w')
        json.dump(hist_bw, json_file)
        json_file.close()
        print('done')

        print('Outputing hist_total_bw...')
        json_file = open("%shist_total_bw-%s.json" % (JSON_PREFIX, timestamp), 'w')
        json.dump(hist_total_bw, json_file)
        json_file.close()
        print('done')

        print('Outputing hist_total_bw_fg...')
        json_file = open("%shist_total_bw_fg-%s.json" % (JSON_PREFIX, timestamp), 'w')
        json.dump(hist_total_bw_fg, json_file)
        json_file.close()
        print('done')

        print('Outputing hist_total_bw_bg...')
        json_file = open("%shist_total_bw_bg-%s.json" % (JSON_PREFIX, timestamp), 'w')
        json.dump(hist_total_bw_bg, json_file)
        json_file.close()
        print('done')

        print('Outputing hist_stats...')
        json_file = open("%shist_stats-%s.json" % (JSON_PREFIX, timestamp), 'w')
        json.dump(hist_stats, json_file)
        json_file.close()
        print('done')

        json_file = open("%shist_uid_slack_fg-%s.json" % (JSON_PREFIX, timestamp), 'w')
        json.dump(hist_uid_slack_fg, json_file)
        json_file.close()
        print('done')

        json_file = open("%shist_uid_slack_bg-%s.json" % (JSON_PREFIX, timestamp), 'w')
        json.dump(hist_uid_slack_bg, json_file)
        json_file.close()
        print('done')

        json_file = open("%shist_uid_limit-%s.json" % (JSON_PREFIX, timestamp), 'w')
        json.dump(hist_uid_limit, json_file)
        json_file.close()

        json_file = open("%shist_slack_period_fg-%s.json" % (JSON_PREFIX, timestamp), 'w')
        json.dump(hist_slack_period_fg, json_file)
        json_file.close()

        json_file = open("%shist_slack_period_bg-%s.json" % (JSON_PREFIX, timestamp), 'w')
        json.dump(hist_slack_period_bg, json_file)
        json_file.close()

        json_file = open("%shist_watermark_fg-%s.json" % (JSON_PREFIX, timestamp), 'w')
        json.dump(hist_watermark_fg, json_file)
        json_file.close()

        json_file = open("%shist_watermark_bg-%s.json" % (JSON_PREFIX, timestamp), 'w')
        json.dump(hist_watermark_bg, json_file)
        json_file.close()

    print(hist_bw)
    print(hist_stats)
    x_intervals = numpy.arange(1, iteration_count+1)
    fig, ax = pyplot.subplots()
    for uid, bw in sorted(hist_bw.items()):
        print(uid)
        print(bw)
        ax.plot(x_intervals, bw, label = uid_to_name(uid))
    ax.set_ylim(bottom=0)
    ax.set_xlim(left=0)
    bottom, top = pyplot.ylim()
    if '1005' in hist_uid_limit:
        ax.axvline(hist_uid_limit['1005'], linestyle='dotted', color='y')
        pyplot.text(1.05 * hist_uid_limit['1005'], 0.95 * top, 'Throttled')
    #ax.legend(loc='upper right')
    ax.legend(loc=9, bbox_to_anchor=(0.5, -0.3), ncol=5)
    ax.set_xlabel('Time (seconds)')
    #ax.set_xlabel('Interval count (%d s)' % INTERVAL)
    ax.set_ylabel('Throughput (KiB/s)')
    #ax.set_title('Plot for %d iterations' % iteration_count)
    #ax.set_title('Plot for %d iterations' % iteration_count)
    pyplot.tight_layout()
    pyplot.savefig("%shist_bw-%s.pdf" % (JSON_PREFIX, timestamp))
    pyplot.close()

    fig, ax = pyplot.subplots()
    ax.plot(x_intervals, hist_total_bw, label='Total')
    ax.plot(x_intervals, hist_total_bw_bg, linestyle='dotted', label='Background')
    ax.plot(x_intervals, hist_total_bw_fg, linestyle='dotted', label='Foreground')
    ax.set_ylim(bottom=0)
    ax.set_xlim(left=0)
    bottom, top = pyplot.ylim()
    ax.legend(loc=9, bbox_to_anchor=(0.5, -0.3), ncol=5)
    ax.set_xlabel('Time (seconds)')
    #ax.set_xlabel('Interval count (%d s)' % INTERVAL)
    ax.set_ylabel('Throughput (KiB/s)')
    #ax.set_title('Plot for %d iterations' % iteration_count)
    #ax.set_title('Plot for %d iterations' % iteration_count)
    pyplot.tight_layout()
    pyplot.savefig("%shist_total_bw-%s.pdf" % (JSON_PREFIX, timestamp))
    pyplot.close()

    fig, ax = pyplot.subplots()
    for uid, stats in sorted(hist_stats.items()):
        ax.plot(x_intervals, stats, label = uid_to_name(uid))
    ax.set_ylim(bottom=0)
    ax.set_xlim(left=0)
    if len(hist_slack_period_fg) > 0:
        ax.plot(x_intervals, hist_slack_period_fg, linestyle='dashed', label='$Slack_{month}$')
    if len(hist_watermark_fg) > 0:
        ax.plot(x_intervals, hist_watermark_fg, linestyle='dotted', label='$W_{mark}')
    #ax.legend(loc='upper right')
    ax.legend(loc=9, bbox_to_anchor=(0.5, -0.3), ncol=5)
    ax.set_xlabel('Interval count (%d s)' % INTERVAL)
    ax.set_ylabel('Total write (KiB)')
    ax.set_title('Plot for %d iterations' % iteration_count)
    pyplot.tight_layout()
    pyplot.savefig("%shist_stats-%s.pdf" % (JSON_PREFIX, timestamp))
    pyplot.close()

    fig, ax = pyplot.subplots()
    for uid, stats in sorted(hist_uid_slack_fg.items()):
        ax.plot(x_intervals, stats, label = uid_to_name(uid))
    if len(hist_slack_period_fg) > 0:
        ax.plot(x_intervals, hist_slack_period_fg, linestyle='dashed', label='$Slack_{hour}$')
    if len(hist_watermark_fg) > 0:
        ax.plot(x_intervals, hist_watermark_fg, linestyle='dashed', label='$W_{mark}$')
    ax.set_ylim(bottom=0)
    ax.set_xlim(left=0)
    bottom, top = pyplot.ylim()
    if '1005' in hist_uid_limit:
        ax.axvline(hist_uid_limit['1005'], linestyle='dotted', color='y')
        pyplot.text(1.05 * hist_uid_limit['1005'], 0.95 * top, 'Throttled')
    #ax.legend(loc='upper right')
    ax.legend(loc=9, bbox_to_anchor=(0.5, -0.3), ncol=5)
    ax.set_xlabel('Time (second)')
    ax.set_ylabel('Total write (KiB)')
    #ax.set_title('Plot for %d iterations' % iteration_count)
    pyplot.tight_layout()
    pyplot.savefig("%shist_uid_slack_fg-%s.pdf" % (JSON_PREFIX, timestamp))
    pyplot.close()

    fig, ax = pyplot.subplots()
    for uid, stats in sorted(hist_uid_slack_bg.items()):
        ax.plot(x_intervals, stats, label = uid_to_name(uid))
    if len(hist_slack_period_bg) > 0:
        ax.plot(x_intervals, hist_slack_period_bg, linestyle='dashed', label='$Slack_{hour}$')
    if len(hist_watermark_bg) > 0:
        ax.plot(x_intervals, hist_watermark_bg, linestyle='dashed', label='$W_{mark}$')
    ax.set_ylim(bottom=0)
    ax.set_xlim(left=0)
    bottom, top = pyplot.ylim()
    if '1005' in hist_uid_limit:
        ax.axvline(hist_uid_limit['1005'], linestyle='dotted', color='y')
        pyplot.text(1.05 * hist_uid_limit['1005'], 0.95 * top, 'Throttled')
    #ax.legend(loc='upper right')
    ax.legend(loc=9, bbox_to_anchor=(0.5, -0.3), ncol=5)
    ax.set_xlabel('Time (second)')
    ax.set_ylabel('Total write (KiB)')
    #ax.set_title('Plot for %d iterations' % iteration_count)
    pyplot.tight_layout()
    pyplot.savefig("%shist_uid_slack_bg-%s.pdf" % (JSON_PREFIX, timestamp))
    pyplot.close()

    if PLOT_PER_UID:
        for uid, bw in hist_bw.items():
            fig, ax1 = pyplot.subplots()
            ax2 = ax1.twinx()
            ax1.plot(x_intervals, bw, label = "bw", color='g')
            ax2.plot(x_intervals, hist_stats[uid], label = "stats", color='b')
            ax.legend(loc='upper right')
            ax1.set_xlabel('Interval count (%d s)' % INTERVAL)
            ax1.set_ylabel('Throughput (KiB/s)', color='g')
            ax2.set_ylabel('Total write (KiB)', color='b')
            pyplot.savefig("%s-%s-avg%.2f.png" % (uid, timestamp, numpy.mean(bw)))
            pyplot.close()

    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)

def get_birthday(uid):
    return 0

def leash_uid(_uid_prison, _uid, _rate):
    if _uid in _uid_prison:
        print("Leashing leashed uid %s with rate %d" % (_uid, _rate))
    else:
        _uid_prison.append(_uid)
        uid_prison_rate[_uid] = _rate

    if host_ratelimit_type == HOST_RATELIMIT_CGROUP1:
        return
    elif host_ratelimit_type == HOST_RATELIMIT_CGROUP2:
        call([HOST_RATELIMIT_CGROUP2_CMD, _uid, str(_rate)])
        return
    elif host_ratelimit_type == HOST_RATELIMIT_RL:
        call([HOST_RATELIMIT_RL_CTRL_CMD, _uid, str(_rate)])
        return
    elif host_ratelimit_type == HOST_RATELIMIT_RL_ADB:
        call(["adb", "shell", "su -c 'echo %s %d > /proc/ratelimit_uid'" % (_uid, _rate)])
    return

def unleash_uid(_uid_prison, _uid):
    if _uid not in _uid_prison:
        print("Unleashing non-leashed uid " + _uid)
        return
    _uid_prison.remove(_uid)
    uid_prison_rate[_uid] = -1

    if host_ratelimit_type == HOST_RATELIMIT_CGROUP1:
        return
    elif host_ratelimit_type == HOST_RATELIMIT_CGROUP2:
        return
    elif host_ratelimit_type == HOST_RATELIMIT_RL:
        call([HOST_RATELIMIT_RL_CTRL_CMD, _uid, "-1"])
        return
    elif host_ratelimit_type == HOST_RATELIMIT_RL_ADB:
        call(["adb", "shell", "echo %s -1 > /proc/ratelimit_uid" % (_uid)])
        return
    return

def is_uid_ratelimited(_uid_prison, _uid):
    return _uid in _uid_prison

def update_foreground_app():
    global current_fg_uid_delay
    global current_fg_uid
    if current_fg_uid_delay > 0:
        current_fg_uid_delay -= 1
    else:
        current_fg_uid = run(['./adb-get-fg-uid-screen.sh'], stdout=PIPE).stdout.decode('utf-8')
        current_fg_uid_delay = DELAY_UPDATE_FG_UID

def is_fg_uid(_uid):
    #print("checking %s with %s" %(_uid, current_fg_uid))
    if _uid == current_fg_uid:
        return True
    if current_fg_uid in SERVICE_TABLE and _uid in SERVICE_TABLE[current_fg_uid]:
        return True
    return False

slack_period_fg = 0
slack_period_bg = 0

while True:
    if HALT == True:
        break
    if NSECS > 0 and iteration_count * INTERVAL > NSECS:
        os.kill(os.getpid(), signal.SIGINT)
        break

    current_time = time.time()
    # New foreground quota period
    if current_time - checkpoint_fg >= QUOTA_PERIOD_FG:
        checkpoint_fg = current_time
        if slack_period_fg > 0:
            # recycle remaining slack
            slack_left += slack_period_fg
        period_left_fg = life_left_fg / QUOTA_PERIOD_FG
        slack_period_fg = slack_left / period_left_fg
        slack_left -= slack_period_fg
        ratelimit_threshold_fg = slack_period_fg * RATELIMIT_THRESHOLD_RATE_FG
        life_left_fg -= QUOTA_PERIOD_FG
        life_left_bg = QUOTA_PERIOD_FG
        slack_left_bg = slack_period_fg
        b_tag_fg = (w_left - slack_left) / life_left_fg
        uid_slack_fg = {}
        print("New foreground slack period: period_left_fg %d slack_period_fg %.2f ratelimit_threshold_fg %.2f b_tag_fg %.2f"
            % (period_left_fg, slack_period_fg, ratelimit_threshold_fg, b_tag_fg))


    if current_time - checkpoint_bg >= QUOTA_PERIOD_BG:
        checkpoint_bg = current_time
        if slack_period_bg > 0:
            # recycle remaining slack
            slack_period_fg += slack_period_bg
        period_left_bg = life_left_bg / QUOTA_PERIOD_BG
        slack_period_bg = slack_left_bg / period_left_bg
        slack_period_fg -= slack_period_bg
        ratelimit_threshold_bg = slack_period_bg * RATELIMIT_THRESHOLD_RATE_BG
        life_left_bg -= QUOTA_PERIOD_BG
        b_tag_bg = b_tag_fg # FIXME
        uid_slack_bg = {}
        print("New background slack period: period_left_bg %d slack_period_bg %.2f ratelimit_threshold_bg %.2f b_tag_bg %.2f"
            % (period_left_bg, slack_period_bg, ratelimit_threshold_bg, b_tag_bg))

    iteration_count += 1
    update_foreground_app()
    if host_ratelimit_type == HOST_RATELIMIT_RL_ADB:
        f = Popen(["adb", "shell", "cat /proc/diskstats_uid_global"], stdout=PIPE).stdout
    elif host_ratelimit_type == HOST_RATELIMIT_DUMB:
        f = Popen(["adb", "shell", "cat /proc/diskstats_uid_global"], stdout=PIPE).stdout
    else:
        f.seek(0)
    line = f.readline()
    fields = line.split()

    sample_seq = int(fields[0])
    timestamp = int(fields[1])
    timestamp_diff = int(fields[2])

    # print(fields)
    print("seq %d timestamp %lu diff %lu" % (sample_seq, timestamp, timestamp_diff))

    iter_total_throughput = 0
    iter_total_throughput_fg = 0
    iter_total_throughput_bg = 0
    iter_uid_throughput = {}

    for line in f:
        fields = line.split()
        #print(fields)

        if int(fields[0]) == -1:
            print("total %lu" % int(fields[1]))
        else:
            uid = fields[0]
            if host_ratelimit_type == HOST_RATELIMIT_RL_ADB:
                uid = str(uid, "utf-8")
            if host_ratelimit_type == HOST_RATELIMIT_DUMB:
                uid = str(uid, "utf-8")
            stats = int(fields[1]) / 2
            stats_diff = int(fields[2]) / 2
            current_stats_dict[uid] = stats
            if uid in WHITELIST:
                continue
            if uid not in uid_birthday:
                uid_birthday[uid] = get_birthday(uid)
                num_uniq_uid += 1
            if uid not in hist_bw:
                hist_bw[uid] = [0] * (iteration_count - 1)
            if uid not in hist_stats:
                hist_stats[uid] = [0] * (iteration_count - 1)

            this_bw = stats_diff / timestamp_diff

            hist_bw[uid].append(this_bw)
            hist_stats[uid].append(stats)
            if uid in WHITELIST:
                continue

            iter_total_throughput += this_bw
            iter_uid_throughput[uid] = this_bw

    hist_total_bw.append(iter_total_throughput)
    if PLOT_ONLY:
        time.sleep(INTERVAL)
        continue

    # Deal with this second
    w_left -= iter_total_throughput

    hist_slack_period_fg.append(slack_period_fg)
    hist_slack_period_bg.append(slack_period_bg)
    hist_watermark_fg.append(ratelimit_threshold_fg)
    hist_watermark_bg.append(ratelimit_threshold_bg)

    is_phone_active = False
    for _uid, _throughput in iter_uid_throughput.items():
        if is_fg_uid(_uid):
            # Foreground app
            print("Foreground %s %s" % (_uid, current_fg_uid))
            is_phone_active = True
            iter_total_throughput_fg += _throughput
            if _uid not in uid_slack_fg:
                uid_slack_fg[_uid] = 0

            if iter_total_throughput > b_tag_fg:
                uid_slack_fg[_uid] += (iter_total_throughput - b_tag_fg) / iter_total_throughput * _throughput
                if uid_slack_fg[_uid] >= 0.99 * ratelimit_threshold_fg:
                    leash_uid(uid_prison, _uid, b_tag_fg / num_uniq_uid * 1024)
                    if _uid not in hist_uid_limit:
                        hist_uid_limit[_uid] = iteration_count
                elif is_uid_ratelimited(uid_prison, _uid):
                    unleash_uid(uid_prison, _uid)
            elif is_uid_ratelimited(uid_prison, _uid):
                unleash_uid(uid_prison, _uid)

        else:
            # background app
            iter_total_throughput_bg += _throughput
            if _uid not in uid_slack_bg:
                uid_slack_bg[_uid] = 0

            if iter_total_throughput > b_tag_bg:
                uid_slack_bg[_uid] += (iter_total_throughput - b_tag_bg) / iter_total_throughput * _throughput
                if uid_slack_bg[_uid] >= 0.99 * ratelimit_threshold_bg:
                    leash_uid(uid_prison, _uid, b_tag_bg / num_uniq_uid * 1024)
                    if _uid not in hist_uid_limit:
                        hist_uid_limit[_uid] = iteration_count
                elif is_uid_ratelimited(uid_prison, _uid):
                    unleash_uid(uid_prison, _uid)
            elif is_uid_ratelimited(uid_prison, _uid):
                unleash_uid(uid_prison, _uid)

        if PLOT_UID_SLACK:
            if _uid not in uid_slack_fg:
                uid_slack_fg[_uid] = 0
            if _uid not in uid_slack_bg:
                uid_slack_bg[_uid] = 0
            if _uid not in hist_uid_slack_fg:
                hist_uid_slack_fg[_uid] = [0] * (iteration_count - 1)
            hist_uid_slack_fg[_uid].append(uid_slack_fg[_uid])
            if _uid not in hist_uid_slack_bg:
                hist_uid_slack_bg[_uid] = [0] * (iteration_count - 1)
            hist_uid_slack_bg[_uid].append(uid_slack_bg[_uid])

    if is_phone_active:
        print("Phone active: %s" % (current_fg_uid))
        slack_period_fg += b_tag_fg - iter_total_throughput
        if iter_total_throughput < b_tag_fg:
            ratelimit_threshold_fg += (b_tag_fg - iter_total_throughput) * 0.5
    else:
        slack_period_bg += b_tag_bg - iter_total_throughput
        if iter_total_throughput < b_tag_bg:
            ratelimit_threshold_bg += (b_tag_bg - iter_total_throughput) * 0.5

    hist_total_bw_fg.append(iter_total_throughput_fg)
    hist_total_bw_bg.append(iter_total_throughput_bg)

    #print(current_stats_dict)
    print("Finished one cycle: period_left_bg %d slack_period_bg %.2f ratelimit_threshold_bg %.2f b_tag_bg %.2f iter_total_throughput_bg %.2f"
        % (period_left_bg, slack_period_bg, ratelimit_threshold_bg, b_tag_bg, iter_total_throughput_bg))
    print("Finished one cycle: period_left_fg %d slack_period_fg %.2f ratelimit_threshold_fg %.2f b_tag_fg %.2f iter_total_throughput_fg %.2f"
        % (period_left_fg, slack_period_fg, ratelimit_threshold_fg, b_tag_fg, iter_total_throughput_fg))
    time.sleep(INTERVAL)
