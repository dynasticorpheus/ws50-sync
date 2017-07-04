#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""Retrospective update of Domoticz with Withings data ON DB LEVEL. BE CAREFULL!"""

import os
import sys
import time
import sqlite3
import argparse
import hashlib
from datetime import datetime

import requests

_AUTHOR_ = 'dynasticorpheus@gmail.com'
_VERSION_ = "0.4.8"

parser = argparse.ArgumentParser(description='Withings WS-50 Syncer by dynasticorpheus@gmail.com')
parser.add_argument('-u', '--username', help='username (email) in use with account.withings.com', required=True)
parser.add_argument('-p', '--password', help='password in use with account.withings.com', required=True)
parser.add_argument('-c', '--co2', help='co2 idx', type=int, required=False)
parser.add_argument('-t', '--temperature', help='temperature idx', type=int, required=False)
parser.add_argument('-d', '--database', help='fully qualified name of database-file', required=True)
parser.add_argument('-l', '--length', help='set short log length (defaults to one day)', type=int, choices=xrange(1, 8), default=1, required=False)
parser.add_argument('-f', '--full', help='update using complete history', action='store_true', required=False)
parser.add_argument('-r', '--remove', help='clear existing data from database', action='store_true', required=False)
parser.add_argument('-w', '--warning', help='suppress urllib3 warnings', action='store_true', required=False)
parser.add_argument('-i', '--insecure', help='disable SSL/TLS certificate verification', action='store_true', required=False)
parser.add_argument('-q', '--quiet', help='do not show per row update info', action='store_true', required=False)
parser.add_argument('-n', '--noaction', help='do not update database', action='store_true', required=False)

args = parser.parse_args()

TMPID = 12
CO2ID = 35

NOW = int(time.time())
PDAY = NOW - (86400 * args.length)

HEADER = {'user-agent': 'Mozilla/5.0 (Windows NT 6.1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/41.0.2228.0 Safari/537.36'}

URL_BASE = "https://scalews.withings.net/cgi-bin"
URL_AUTH = URL_BASE + "/auth?action=login&appliver=3000201&apppfm=android&appname=wiscaleNG&callctx=foreground"
URL_ASSO = URL_BASE + "/association?action=getbyaccountid&enrich=t&appliver=3000201&apppfm=android&appname=wiscaleNG&callctx=foreground&sessionid="
URL_USAGE = "https://goo.gl/z6NNlH"


def clear_line():
    sys.stdout.write("\033[F")
    sys.stdout.write("\033[K")


def init_database(db):
    global conn
    global c
    if os.path.exists(db):
        conn = sqlite3.connect(db, timeout=60)
        c = conn.cursor()
        c.execute('SELECT * FROM Preferences WHERE Key = "DB_Version";')
        dbinfo = c.fetchall()
        for row in dbinfo:
            dbversion = row[1]
        print "[-] Attaching database " + db + " [version " + str(dbversion) + "]"
    else:
        sys.exit("[-] Database not found " + db + "\n")


def clear_devices(idx, table):
    print "[-] Removing existing data from table " + str(table).upper()
    try:
        c.execute('DELETE FROM ' + str(table) + ' WHERE DeviceRowID = ' + str(idx) + ';')
    except Exception:
        sys.exit("[-] Data removal failed, exiting" + "\n")


def get_lastupdate(idx, table):
    comment = ""
    for dates in c.execute('select max(Date) from ' + str(table) + ' where DeviceRowID=' + str(idx)):
        if dates[0] is None:
            lastdate = PDAY
            comment = " (" + str(args.length) + " day limit)"
        else:
            dt_obj = datetime.strptime(str(dates[0]), "%Y-%m-%d %H:%M:%S")
            lastdate = int(time.mktime(dt_obj.timetuple())) + 1
            if lastdate < PDAY:
                lastdate = PDAY
                comment = " (" + str(args.length) + " day limit)"
    print "[-] Downloading all measurements recorded after " + time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(lastdate)) + comment
    return lastdate


def authenticate_withings(username, password):
    global pem
    if args.warning:
        try:
            requests.packages.urllib3.disable_warnings()
        except Exception:
            pass
    if args.insecure:
        pem = False
    else:
        try:
            import certifi
            pem = certifi.old_where()
        except Exception:
            pem = True
    requests.head(URL_USAGE, timeout=3, headers=HEADER, allow_redirects=True, verify=pem)
    payload = {'email': username, 'hash': hashlib.md5(password).hexdigest(), 'duration': '900'}
    print "[-] Authenticating at scalews.withings.net"
    response = requests.post(URL_AUTH, data=payload)
    id = response.json()
    sessionkey = id['body']['sessionid']
    response = requests.get(URL_ASSO + sessionkey)
    id = response.json()
    deviceid = id['body']['associations'][0]['deviceid']
    return deviceid, sessionkey


def download_data(deviceid, sessionkey, type, lastdate):
    payload = '/v2/measure?action=getmeashf&deviceid=' + str(deviceid) + '&meastype=' + str(type) + '&startdate=' + str(lastdate) + '&enddate=' + str(NOW) + \
        '&appliver=3000201&apppfm=android&appname=wiscaleNG&callctx=foreground&sessionid=' + str(sessionkey)
    try:
        response = requests.get(URL_BASE + payload)
    except Exception:
        sys.exit("[-] Data download failed, exiting" + "\n")
    dataset = response.json()
    return dataset


def update_meter(name, idx, field, dbtable, dataset, status=None):
    try:
        count = 0
        for item in dataset['body']['series']:
            for item2 in reversed(item['data']):
                if not args.quiet:
                    print('[-] INSERT INTO ' + str(dbtable) + '(DeviceRowID,' + str(field) + ',Date) VALUES (' + str(idx) + ',' + str(
                        item2['value']) + ",'" + time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(item2['date'])) + "'" + ')')
                    clear_line()
                c.execute('INSERT INTO ' + str(dbtable) + '(DeviceRowID,' + str(field) + ',Date) VALUES (' + str(idx) + ',' + str(
                    item2['value']) + ",'" + time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(item2['date'])) + "'" + ')')
                count += 1
            if count > 0 and status is not None:
                c.execute('UPDATE DeviceStatus SET ' + str(status) + ' = ' + str(item2['value']) + ' WHERE ID = ' + str(idx))
                c.execute('UPDATE DeviceStatus SET LastUpdate = ' + "'" + time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(
                    item2['date'])) + "'" + ' WHERE ID = ' + str(idx))
            print "[-] Updating " + str(name).upper() + " table with " + str(count) + " measurements" + " [" + str(not args.noaction).upper() + "]"
    except Exception:
        conn.close()
        sys.exit("[-] Meter update failed, exiting" + "\n")
    return count


def full_update(name, type, field, table, idx, dataset):
    try:
        c.execute('CREATE TEMPORARY TABLE IF NOT EXISTS WS50SYNC ([DeviceRowID] BIGINT NOT NULL, [Value] BIGINT, [Temperature] FLOAT, [Date] DATETIME);')
        update_meter(str(name), idx, field, "WS50SYNC", dataset)
    except Exception:
        print "[-] Temporary table update failed, exiting"
        conn.close()
        sys.exit()
    print "[-] Calculating daily MIN, MAX & AVG values"
    c.execute('select DeviceRowID, min(' + str(field) + '), max(' + str(field) + '), avg(' + str(
        field) + '), date(date) from WS50SYNC where DeviceRowID=' + str(idx) + ' group by date(date);')
    dbdata = c.fetchall()
    for row in dbdata:
        if type.upper() == "CO2":
            c.execute('INSERT INTO ' + str(table) + ' (DeviceRowID,Value1,Value2,Value3,Value4,Value5,Value6,Date) VALUES (' + str(row[0]) + ',' + str(
                row[1]) + ',' + str(row[2]) + ',0,0,0,0' + ",'" + str(row[4]) + "'" + ')')
        if type.upper() == "TEMPERATURE":
            c.execute('INSERT INTO ' + str(table) + ' (DeviceRowID,Temp_Min,Temp_Max,Temp_Avg,Date) VALUES (' + str(row[0]) + ',' + str(row[1]) + ',' + str(
                row[2]) + ',' + str(row[3]) + ",'" + str(row[4]) + "'" + ')')


def commit_database():
    print "[-] Committing and closing database"
    try:
        conn.commit()
    except Exception:
        conn.rollback()
        conn.close()
        sys.exit("[-] Error during commit, reverting changes and closing database" + "\n")
    c.execute('PRAGMA wal_checkpoint(PASSIVE);')
    conn.close()


def main():
    totalrows = 0
    print
    print "Withings WS-50 Syncer Version " + _VERSION_
    print

    if not (args.co2 or args.temperature):
        parser.error('argument -c/--co2 and/or -t/--temperature is required')

    if args.full and not args.remove:
        parser.error('argument -f/--full requires -r/--remove')

    if args.noaction:
        print "[-] Dry run mode enabled, no changes to the database will be made"

    init_database(args.database)

    deviceid, sessionkey = authenticate_withings(args.username, args.password)

    if args.co2:
        if args.remove:
            clear_devices(args.co2, "Meter")
        lastentrydate = get_lastupdate(args.co2, "Meter")
        co2data = download_data(deviceid, sessionkey, CO2ID, lastentrydate)
        co2rows = update_meter("CO2 Hourly", args.co2, "Value", "Meter", co2data, "nValue")
        totalrows = totalrows + co2rows
        if args.full:
            if args.remove:
                clear_devices(args.co2, "MultiMeter_Calendar")
            completedataset = download_data(deviceid, sessionkey, CO2ID, 0)
            full_update("CO2 Yearly", "CO2", "Value", "MultiMeter_Calendar", args.co2, completedataset)

    if args.temperature:
        if args.remove:
            clear_devices(args.temperature, "Temperature")
        lastentrydate = get_lastupdate(args.temperature, "Temperature")
        tmpdata = download_data(deviceid, sessionkey, TMPID, lastentrydate)
        tmprows = update_meter("TEMPERATURE Hourly", args.temperature, "Temperature", "Temperature", tmpdata, "sValue")
        totalrows = totalrows + tmprows
        if args.full:
            if args.remove:
                clear_devices(args.temperature, "Temperature_Calendar")
            completedataset = download_data(deviceid, sessionkey, TMPID, 0)
            full_update("TEMPERATURE Yearly", "TEMPERATURE", "Temperature", "Temperature_Calendar", args.temperature, completedataset)

    if not args.noaction and totalrows > 0:
        commit_database()
    else:
        print "[-] Nothing to commit, closing database"
        conn.close()

    print

if __name__ == "__main__":
    main()
