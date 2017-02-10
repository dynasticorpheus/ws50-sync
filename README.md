WS50-SYNC
=========

ws50-sync is a python based program which pulls air quality data from your Withings account and stores it directly in a Domoticz DB.


    Withings WS-50 Syncer by dynasticorpheus@gmail.com
    
    optional arguments:
      -h, --help            show this help message and exit
      -u USERNAME, --username USERNAME
                            username in use with account.withings.com
      -p PASSWORD, --password PASSWORD
                            password in use with account.withings.com
      -c CO2, --co2 CO2     co2 idx
      -t TEMPERATURE, --temperature TEMPERATURE
                            temperature idx
      -d DATABASE, --database DATABASE
                            fully qualified name of database-file
      -f, --full            update using complete history
      -r, --remove          clear existing data from database
      -w, --warning         suppress urllib3 warnings
      -i, --insecure        disable SSL/TLS certificate verification
      -q, --quiet           do not show per row update info
      -n, --noaction        do not update database
