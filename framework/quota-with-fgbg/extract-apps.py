#!/usr/bin/env python3

import json

f = open('packages.list', 'r')

app_dict = {
    0: "ROOT",
    1000: "SYSTEM",
    #1001: "RADIO",
    #1002: "BLUETOOTH",
    1003: "GRAPHICS",
    1004: "INPUT",
    1005: "AUDIO",
    1006: "CAMERA",
    1007: "LOG",
    1008: "COMPASS",
    1009: "MOUNT",
    1010: "WIFI",
    1011: "ADB",
    1012: "INSTALL",
    1013: "MEDIA",
    1014: "DHCP",
    1015: "SDCARD_RW",
    1016: "VPN",
    1017: "KEYSTORE",
    1018: "USB",
    1019: "DRM",
    1020: "MDNSR",
    1021: "GPS",
    1022: "UNUSED1",
    1023: "MEDIA_RW",
    1024: "MTP",
    1025: "UNUSED2",
    1026: "DRMRPC",
    #1027: "NFC",
    1028: "SDCARD_R",
    1029: "CLAT",
    1030: "LOOP_RADIO",
    1031: "MEDIA_DRM",
    1032: "PACKAGE_INFO",
    1033: "SDCARD_PICS",
    1034: "SDCARD_AV",
    1035: "SDCARD_ALL",
    1036: "LOGD",
    1037: "SHARED_RELRO",
    1038: "DBUS",
    1039: "TLSDATE",
    1040: "MEDIA_EX",
    1041: "AUDIOSERVER",
    1042: "METRICS_COLL",
    1043: "METRICSD",
    1044: "WEBSERV",
    1045: "DEBUGGERD",
    1046: "MEDIA_CODEC",
    1047: "CAMERASERVER",
    1048: "FIREWALL",
    1049: "TRUNKS",
    1050: "NVRAM",
    1051: "DNS",
    1052: "DNS_TETHER",
    1053: "WEBVIEW_ZYGOTE",
    1054: "VEHICLE_NETWORK",
    1055: "MEDIA_AUDIO",
    1056: "MEDIA_VIDEO",
    1057: "MEDIA_IMAGE",
    1058: "TOMBSTONED",
    1059: "MEDIA_OBB",
    1060: "ESE",
    1061: "OTA_UPDATE",
    1062: "AUTOMOTIVE_EVS",
    1063: "LOWPAN",
    1064: "HSM",
    1065: "RESERVED_DISK",
    1066: "STATSD",
    1067: "INCIDENTD",
    1068: "SECURE_ELEMENT",
    1069: "LMKD",
    1070: "LLKD",
    #2000: "SHELL",
    2001: "CACHE",
    2002: "DIAG",
}
for line in f:
    fields = line.split()
    uid = int(fields[1])
    if uid in app_dict:
        #app_dict[uid] += ",%s" % (fields[0])
        True
    else:
        app_dict[uid] = fields[0]

json_file = open('app-list.json', 'w')
json.dump(app_dict, json_file, indent=2, sort_keys=True)
json_file.close()
