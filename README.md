**WS50-SYNC**
---------

ws50-sync is a python based program which pulls air quality data from your Withings account and stores it directly in a Domoticz DB.

Keep Domoticz running in the background whilst using this script otherwise the database journal will not record the changes and revert them at start up.


    Withings WS-50 Syncer by dynasticorpheus@gmail.com

	optional arguments:
	  -h, --help            show this help message and exit
	  -u USERNAME, --username USERNAME
                      username (email) in use with account.withings.com
	  -p PASSWORD, --password PASSWORD
                        password in use with account.withings.com
	  -c CO2, --co2 CO2     co2 idx
	  -t TEMPERATURE, --temperature TEMPERATURE
                        temperature idx
	  -d DATABASE, --database DATABASE
                        fully qualified name of database-file
	  -r, --remove          clear existing data from database
	  -n, --noaction        do not update database
