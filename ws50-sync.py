#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""Retrospective update of Domoticz with Withings data ON DB LEVEL. BE CAREFULL!"""

import os
import sys
import time
import sqlite3
import requests
import re
import argparse
from datetime import datetime


_AUTHOR_ = 'dynasticorpheus@gmail.com'
_VERSION_ = "0.4.4"

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
parser.add_argument('-q', '--quiet', help='do not show per row update info', action='store_true', required=False)
parser.add_argument('-n', '--noaction', help='do not update database', action='store_true', required=False)

args = parser.parse_args()
s = requests.Session()
s.mount("http://", requests.adapters.HTTPAdapter(max_retries=3))
s.mount("https://", requests.adapters.HTTPAdapter(max_retries=3))

TMPID = 12
CO2ID = 35

NOW = int(time.time())
PDAY = NOW - (86400 * args.length)

HEADER = {'user-agent': 'Mozilla/5.0 (Windows NT 6.1) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/41.0.2228.0 Safari/537.36'}

URL_DATA = "https://healthmate.withings.com/index/service/v2/measure"
URL_AUTH = "https://account.withings.com/connectionuser/account_login?appname=my2&appliver=c7726fda&r=https%3A%2F%2Fhealthmate.withings.com%2Fhome"
URL_ASSO = "https://healthmate.withings.com/index/service/association"
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


def restpost(url, payload, head=None):
    try:
        if head is not None:
            r = s.post(url, data=payload, timeout=90, stream=False, headers=head)
        else:
            r = s.post(url, data=payload, timeout=90, stream=False)
    except requests.exceptions.RequestException as e:
        sys.exit("ERROR " + str(e.message) + "\n")
    if r.status_code != requests.codes.ok:
        sys.exit("HTTP ERROR " + str(r.status_code) + "\n")
    try:
        commit_data = r.json()
    except ValueError:
        commit_data = r
    return commit_data


def authenticate_withings(username, password):
    if args.warning:
        try:
            requests.packages.urllib3.disable_warnings()
        except Exception:
            pass
    auth_data = "email=" + str(username) + "&is_admin=&password=" + str(password)
    print "[-] Authenticating at account.withings.com"
    s.request("HEAD", URL_USAGE, timeout=3, headers=HEADER, allow_redirects=True)
    response = restpost(URL_AUTH, auth_data)
    if 'session_key' in s.cookies.get_dict():
        jar = s.cookies.get_dict()
    else:
        sys.exit("[-] Session key negotiation failed, check username and/or password" + "\n")
    accountid = re.sub("[^0-9]", "", str(re.search('(?<=accountId)(.*)', response.content)))
    payload = "accountid=" + str(accountid) + "&action=getbyaccountid&appliver=c7726fda&appname=my2&apppfm=web&enrich=t&sessionid=" + \
        jar['session_key'] + "&type=-1"
    response = restpost(URL_ASSO, payload)
    deviceid = response['body']['associations'][0]['deviceid']
    sessionkey = jar['session_key']
    return deviceid, sessionkey


def download_data(deviceid, sessionkey, type, lastdate):
    base = "action=getmeashf&appliver=82dba0d8&appname=my2&apppfm=web&deviceid=" + str(deviceid) + "&enddate=" + \
        str(NOW) + "&sessionid=" + str(sessionkey) + "&startdate=" + str(lastdate) + "&meastype="
    try:
        payload = base + str(type)
        r = s.request("POST", URL_DATA, data=payload)
    except Exception:
        sys.exit("[-] Data download failed, exiting" + "\n")
    dataset = r.json()
    return dataset


def update_meter(name, idx, field, dbtable, dataset):
    try:
        count = 0
        for item in dataset['body']['series']:
            for item2 in reversed(item['data']):
                if not args.quiet:
                    print('[-] INSERT INTO ' + str(dbtable) + '(DeviceRowID,' + str(field) + ',Date) VALUES (' + str(idx) + ',' + str(
                        item2['value']) + ",'" + time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(item2['date'])) + "'" + ')')
                    clear_line()
                if not args.noaction:
                    c.execute('INSERT INTO ' + str(dbtable) + '(DeviceRowID,' + str(field) + ',Date) VALUES (' + str(idx) + ',' + str(
                        item2['value']) + ",'" + time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(item2['date'])) + "'" + ')')
                count += 1
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
        co2rows = update_meter("CO2 Hourly", args.co2, "Value", "Meter", co2data)
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
        tmprows = update_meter("TEMPERATURE Hourly", args.temperature, "Temperature", "Temperature", tmpdata)
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
