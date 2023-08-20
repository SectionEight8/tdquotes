# TDQUOTES
tdquotes.py is a python script intended to be used in KMyMoney as an online quote source, to retrieve quotes using the [Twelve Data](https://twelvedata.com/) financial service API. 

This is alpha level software - use at your own risk.

## Requirements
A Twelve Data API key is required to retrieve quotes.  

This script will currently only run on Linux.

[Python](https://www.python.org/) must be installed to run this script. It was written using Python 3.11, so if possible, install Python 3.11 or higher.  It uses features that were introduced in Python 3.6, so it will certainly fail with any Python older than 3.6.

## Installation
Download tdquotes.py to your preferred directory for user scripts and make sure it is executable (chmod +x).

## Basic Setup
tdquotes requires a configuration file with your Twelve Data API key. This file should be named tdquotes.conf and should either be in the directory where tdquotes.py is installed or be named:

**(user home directory)/.config/tdquotes.conf** 

It **MUST** have a [Settings] section with your Twelve Data API key:

```properties
[Settings] 
apikey = mytwelvedatakey
```
The tdquotes.conf file must be updatable by tdquotes.

Current versions of KMyMoney will not display error messages from an online quote script to the user (this is coming in a future release). Before setting up a quote source in KMyMoney, it is a good idea to test tdquotes first by running it as a command, so you can see any error messages if it fails. After downloading tdquotes.py and setting up tdquotes.conf, open a terminal and navigate to the directory where this is installed and try to fetch a stock quote:

```
cd /path/to/tdquotes.py
./tdquotes.py --fetch GOOG
```
If it is successful, the last line output should be something like the following.  This will be the string it passes to KMyMoney to be parsed by the regexes in the online quote setup there:

```
price="130.28999" date="2023-08-15"
```

## KMyMoney Setup
tdquotes.py should be set up as an online quote script in KMyMoney, according to this paragraph in the [Updating Prices](https://docs.kde.org/stable5/en/kmymoney/kmymoney/details.investments.prices.html#details.investments.onlinequotes) section of the KMyMoney handbook:

> Note that the URL can also be a file: URL, which the quote fetcher takes to be the path to an executable script. It will pass any command-line arguments to it that you have specified, and feed the stdout to the page parser. For example, you might have a script called getquote.sh that contains custom quote logic, taking the symbol as a single parameter. Your URL would be “file:/path/to/getquote.sh %1”.

To do this, create a new Online Quote source in the KMyMoney configuration.  For reasons explained below in the advanced section, this quote source should be named the same name as this script. So if you saved this script as "tdquotes.py", the online quote source in KMyMoney should be named "tdquotes" or "Tdquotes" or "TDquotes".  The case does not matter, but the online quote source name in KMyMoney should match this script's file name, with the .py extension removed.

The tdquotes online quote source should be configured as:

```
URL:            file:/path/to/tdquotes.py --fetch %1
Identifier:     %1
Identify by:    Symbol
Price:          price="([^"]+)
Date:           date="([^"]+)
Date Format:    %y %m %d

```
tdquotes --fetch returns the quote to kmymoney in a string like  **price="123.456" date="YYYY-MM-DD"**. So the price and date regexes should extract them from that string. You should be able to assign this online quote source to any equity in KMyMoney and retrieve a quote, as long as the equity is supported by Twelve Data.

## Advanced Setup
The above setup should be able to retrieve up to 800 quotes from Twelve Data in KMyMoney, which is the daily quote limit of Twelve Data's free tier. However, it will wait a default of 8 seconds between each quote retrieval, so this could take a while in KMyMoney if you need to retrieve a lot of quotes.  The doc below explains how to use the tdquotes.py --retrieve option to mitigate this.

### tdquotes --retrieve
The "`tdquotes --retrieve`" option can retrieve a number of pre-configured quotes from Twelve Data and write the quotes to a .csv file.  When "`tdquotes.py --fetch`" is run from KMyMoney, it first looks in this .csv file for a matching quote and will return that to KMyMoney if one is found. It will only query Twelve Data directly (with the 8 second wait) if no matching quote is found in the .csv file.

"`tdquotes.py --retrieve`" is intended to be run in the background, where the 8 second delay between quotes won't be noticed, whenever you want updated stock quotes in KMyMoney. It can be run from crontab, or a systemd timer unit on Linux.

The following settings, in the [Quotes] section of tdquotes.conf, are required to use the `--retrieve` option:

To specify the ticker symbols to be retrieved, either specify the symbols directly using the "symbols" setting, or specify your kMyMoney database using the "kmmfile" setting. One of these is required. If both are set, "symbols" is used and "kmmfile" is ignored.

Specify the ticker symbols whose quotes will be retrieved using the "symbols" setting:

```properties
[Quotes]
symbols = APPL TSLA AMZN
    MSFT IBM HAL ABC DEF       
```
The symbols should be a blank separated list of strings. The value can span multiple lines, as long as subsequent lines are indented.

Alternatively, you can specify your KMyMoney database and tdquotes will read it to find the symbols to retrieve:

```properties
[Quotes]
kmmfile = /path/to/my/kmymoney/database.kmy
```
This requires that your KMyMoney database is a gzipped XML file. Tdquotes will search the SECURITIES section of your database for all securities that have an online source named with the same name "tdquotes.py" is saved as on your system, with the .py extension removed.  So probably "tdquotes" or "Tdquotes" or "tdquoteS", etc. (the comparison is case insensitive), and then retrieve those quotes from Twelve Data. 

This option is supported because I don't want to configure all of my quote downloads twice (in KMyMoney and a config file).

NOTE:  tdquotes uses the standard python gzip module to unzip your KMyMoney database into memory, and searches that for ticker symbols - so it only reads your KMyMoney database. If you are concerned about this, you should be able to run "tdquotes.py --retrieve" from a user that has read-only access to your KMyMoney database.  However, the usual caveats should apply here: Murphy's Law is relentless, always have backups, etc.

Use the "csvfile" setting to specify the .csv file where quotes will be saved:

```properties
[Quotes]
csvfile = /path/to/csv/file/quotes.csv
```
This file does not need to exist, but tdquotes must be able to write to its directory.  Quotes are saved in the csv file as "SYMBOL","YYYY-MM-DD","price".  When "tdquotes --fetch" is run from KMyMoney, the csv file is first searched for a quote for input symbol. If any are found, the one with the earliest date is returned to KMyMoney and that line is deleted from the csv file. The --fetch option only goes directly to Twelve Data for the quote (with the 8 second delay) if no match can be found in the csv file.   

See the sample tdquotes.conf file for other options. 