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
_VERSION_ = "0.3.0"

parser = argparse.ArgumentParser(description='Withings WS-50 Syncer by dynasticorpheus@gmail.com')
parser.add_argument('-u', '--username', help='username (email) in use with account.withings.com', required=True)
parser.add_argument('-p', '--password', help='password in use with account.withings.com', required=True)
parser.add_argument('-c', '--co2', help='co2 idx', type=int, required=True)
parser.add_argument('-t', '--temperature', help='temperature idx', type=int, required=True)
parser.add_argument('-d', '--database', help='fully qualified name of database-file', required=True)
parser.add_argument('-r', '--remove', help='clear existing data from database', action='store_true', required=False)
parser.add_argument('-n', '--noaction', help='do not update database', action='store_true', required=False)

args = parser.parse_args()
s = requests.Session()

TMPID = 12
CO2ID = 35

NOW = int(time.time())
PDAY = NOW - 86400

URL_DATA = "https://healthmate.withings.com/index/service/v2/measure"
URL_AUTH = "https://account.withings.com/connectionuser/account_login?appname=my2&appliver=c7726fda&r=https%3A%2F%2Fhealthmate.withings.com%2Fhome"
URL_ASSO = "https://healthmate.withings.com/index/service/association"


def clear_line():
    sys.stdout.write("\033[F")
    sys.stdout.write("\033[K")


def init_database(db):
    global conn
    global c
    if os.path.exists(db):
        print "[-] Attaching database " + db
        conn = sqlite3.connect(db, timeout=60)
        c = conn.cursor()
    else:
        sys.exit("[-] Database not found " + db + "\n")


def clear_devices(idx, table1, table2):
    print "[-] Removing existing data from tables " + str(table1).upper() + " and " + str(table2).upper()
    try:
        c.execute('DELETE FROM ' + str(table1) + ' WHERE DeviceRowID = ' + str(idx) + ';')
        c.execute('DELETE FROM ' + str(table2) + ' WHERE DeviceRowID = ' + str(idx) + ';')
    except Exception:
        sys.exit("[-] Data removal failed, exiting" + "\n")


def get_lastupdate(idx):
    comment = ""
    for dates in c.execute('select max(Date) from Meter where DeviceRowID=' + str(idx)):
        if dates[0] is None:
            lastdate = PDAY
            comment = " (24 hour limit)"
        else:
            dt_obj = datetime.strptime(str(dates[0]), "%Y-%m-%d %H:%M:%S")
            lastdate = int(time.mktime(dt_obj.timetuple())) + 1
            if lastdate < PDAY:
                lastdate = PDAY
                comment = " (24 hour limit)"
    print "[-] Downloading all measurements recorded after " + time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(lastdate)) + comment
    return lastdate


def authenticate_withings(username, password):
    auth_data = "email=" + str(username) + "&is_admin=&password=" + str(password)
    print "[-] Authenticating at account.withings.com"
    try:
        response = s.request("POST", URL_AUTH, data=auth_data)
    except Exception:
        sys.exit("[-] Authenticating failed, exiting" + "\n")
    jar = s.cookies.get_dict()
    accountid = re.sub("[^0-9]", "", str(re.search('(?<=accountId)(.*)', response.content)))
    payload = "accountid=" + str(accountid) + "&action=getbyaccountid&appliver=c7726fda&appname=my2&apppfm=web&enrich=t&sessionid=" + \
        jar['session_key'] + "&type=-1"
    response = s.request("POST", URL_ASSO, data=payload)
    r = response.json()
    deviceid = r['body']['associations'][0]['deviceid']
    sessionkey = jar['session_key']
    return deviceid, sessionkey


def download_data(deviceid, sessionkey, type, lastdate):
    BASE = "action=getmeashf&appliver=82dba0d8&appname=my2&apppfm=web&deviceid=" + str(deviceid) + "&enddate=" + \
        str(NOW) + "&sessionid=" + str(sessionkey) + "&startdate=" + str(lastdate) + "&meastype="
    try:
        payload = BASE + str(type)
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
                print('[-] INSERT INTO ' + str(dbtable) + '(DeviceRowID,' + str(field) + ',Date) VALUES (' + str(idx) + ',' + str(
                    item2['value']) + ",'" + time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(item2['date'])) + "'" + ')')
                if not args.noaction:
                    c.execute('INSERT INTO ' + str(dbtable) + '(DeviceRowID,' + str(field) + ',Date) VALUES (' + str(idx) + ',' + str(
                        item2['value']) + ",'" + time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(item2['date'])) + "'" + ')')
                count += 1
                clear_line()
            print "[-] Updating " + str(name).upper() + " table with " + str(count) + " measurements" + " [" + str(not args.noaction).upper() + "]"
    except Exception:
        conn.close()
        sys.exit("[-] Meter update failed, exiting" + "\n")
    return count


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
    print
    print "Withings WS-50 Syncer Version " + _VERSION_
    print

    init_database(args.database)

    if args.remove:
        clear_devices(args.co2, "Meter", "MultiMeter_Calendar")
        clear_devices(args.temperature, "Temperature", "Temperature_Calendar")

    deviceid, sessionkey = authenticate_withings(args.username, args.password)

    lastentrydate = get_lastupdate(args.co2)

    co2data = download_data(deviceid, sessionkey, CO2ID, lastentrydate)
    tmpdata = download_data(deviceid, sessionkey, TMPID, lastentrydate)

    co2rows = update_meter("CO2", 36, "Value", "Meter", co2data)
    tmprows = update_meter("TEMPERATURE", 37, "Temperature", "Temperature", tmpdata)

    totalrows = co2rows + tmprows

    if not args.noaction and totalrows > 0:
        commit_database()
    else:
        print "[-] Nothing to commit, closing database"
        conn.close()

    print

if __name__ == "__main__":
    main()
