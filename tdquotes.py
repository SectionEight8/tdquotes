#!/usr/bin/env python3
#
#   This script is intended to be called by KMyMoney to retrieve stock quotes from twelvedata.com
#
#   License: MIT
#

import configparser
import csv
import gzip
import json
import logging
import logging.handlers
import re
import sys
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from operator import itemgetter
from pathlib import Path, PurePath

# default path name of our config file:
gbl_configfile = Path.home() / '.config' / 'tdquotes.conf'
gbl_config = configparser.ConfigParser()
gbl_logger = logging.getLogger( __name__ )

def main():
    global gbl_logger, gbl_configfile

    #  Set config defaults:
    gbl_config['Settings'] = {'quotetime': '0',
                           'delay'    : '8'}
    gbl_config['Logging']  = {'loglevel': 'ERROR'}
    gbl_config['Quotes']   = {'csvfile' : ''}

    # find our config file - return with error if it doesn't exist
    gbl_configfile = getconfigfile()
    if  not gbl_configfile:
        return 0

    gbl_config.read( gbl_configfile )
    gbl_config.sections()

    #  Initialize the logger:
    if  gbl_config.has_option( 'Logging', 'logfile' ):
        logfile = gbl_config['Logging']['logfile']
        if  logfile.lower() == 'syslog':
            handler = logging.handlers.SysLogHandler( address='/dev/log' )
        else:
            handler = logging.FileHandler( logfile )
    else:
        handler = logging.NullHandler()

    gbl_logger.addHandler( handler )

    try:
        logging.basicConfig( style='{',
                             format='{asctime} {levelname:<8} {message}',
                             datefmt='%a, %d %b %Y %H:%M:%S' )
    except Exception as e:
        printerror( f'Unable to initialize log: {e}' )

    loglevel = gbl_config['Logging']['loglevel']
    try:
        gbl_logger.setLevel( loglevel )
    except ValueError as e:
        printerror( f'Error setting log level: {e}' )
        gbl_logger.setLevel( logging.ERROR )

    if not gbl_config.has_option( 'Settings', 'APIkey' ):
        printerror( f'Your config file - {gbl_configfile} - must specify your Twelve Data API key' )
        return 0

    if len( sys.argv ) < 2:
        printerror( 'Either "--fetch" or "--retrieve" is required' )
        return 0

    if  sys.argv[1].lower() == '--retrieve':
        retrievequotes()
        return 0

    elif  sys.argv[1].lower() == '--fetch':
        #  fetch a quote and return it to kmymoney:
        if  len( sys.argv ) < 3:
            printerror( 'The --fetch option requires a ticker symbol' )
            return 0

        ticker = sys.argv[2].upper()
        date, price = fetchquote( ticker )
        if  date is None or price is None:
            return 0

        # emit the date & price to kmymoney:
        strout = f'price="{price}" date="{date}"'
        gbl_logger.debug( 'reply to Kmymoney:' )
        gbl_logger.debug( strout )
        print( strout )

    return 0

def getconfigfile():
    """
        Find "tdquotes.conf" if it exists.  If not, issue an error and return None
    """
    if  gbl_configfile.exists():
        configfile = gbl_configfile
    else:
        configfile = Path( sys.argv[0] ).parent / "tdquotes.conf"
        if  not configfile.exists():
            printerror( f'A config file of {gbl_configfile} or {configfile} with your Twelve Data API key is required' )
            configfile = None

    return configfile



def fetchquote( ticker ):
    """
       Fetch a quote for the input ticker symbol

       First, search the configured .csv file for a quote retrieved by the "--retrieve" request.
       If a csv file is not configured, does not exist, or has no quote for the input ticker,
       get a quote directly from Twelve Data
    """
    csvfilename = gbl_config['Quotes']['csvfile']
    date = price = None
    if  csvfilename  and  Path( csvfilename ).exists():
        rows = csvread( csvfilename )
        for ix, row in enumerate(rows):
            if  row[0] == ticker:
                date = row[1]
                price = row[2]
                gbl_logger.info( f'Quote for {ticker} retrieved from {csvfilename}: price={price}, date={date}' )
                
                #  delete the row we just read from the csv file and update it: 
                del rows[ix]
                with  open( csvfilename, 'w', newline='' ) as csvfile:
                    writer = csv.writer( csvfile, delimiter=',', quotechar='"', quoting=csv.QUOTE_ALL )
                    writer.writerows( rows )

                break

    # if we couldn't get a quote from the csvfile, fetch directly from twelve data:
    if  date is None or price is None:
        date, price = tdquote( ticker )

    return date, price

def tdquote( ticker, count=0, total=0 ):
    """
      Retrieve a quote from twelvedata.com for the input ticker symbol.  Wait if necessary
    """
    apikey = gbl_config['Settings']['apikey']
    url = f'https://api.twelvedata.com/eod?symbol={ticker}&apikey={apikey}'
    req = urllib.request.Request( url )
    req.add_header( 'User-agent', 'Mozilla/5.0' )

    gbl_logger.debug( f'URL to retrieve {ticker}: {url}' )

    waittime = tddelay( 'wait' )

    try:
        with urllib.request.urlopen( req ) as response:
            mktdata = response.read().decode()
    except urllib.error.URLError as e:
        printerror( f'URLError on URL for {ticker}\n{url}:\nError: {e.reason}' )
        return None, None

    tddelay( 'update' )

    gbl_logger.debug( f'twelvedata.com response:\n{mktdata}' )

    try:
        quote = json.loads( mktdata )
    except json.JSONDecodeError as e:
        printerror( f'JSON decoder error: {e.msg} on data:\n{e.doc}' )
        return None, None

    try:
        price = quote['close']
        date = quote['datetime']
    except KeyError as e:
        printerror( f'Unable to extract price or date, key {e}'    
                    f' is missing in Twelve Data output for {ticker}' )
        return None, None

    if  count > 0:
        gbl_logger.info( f'{count} of {total} quotes: {ticker} from twelvedata.com date:{date}  price:{price}, '
                     f'waited {waittime} seconds' )
    else:
        gbl_logger.info( f'{ticker} from twelvedata.com date:{date}  price:{price}, waited {waittime} seconds' )

    return date, price


def tddelay(request):
    """
        If necessary, wait before retrieving another quote from Twelve Data.

            Input request -
                'wait': wait before retrieving another quote.
                'update': update the quote retrieval time stamp in the config file as the current time in seconds since start
                    of epoch.
    """
    waittime = 0
    if request == 'wait':
        quotetime = int( gbl_config['Settings']['quotetime'] )
        delay = int( gbl_config['Settings']['delay'] )
        if quotetime:
            interval = int(time.time()) - quotetime
            if interval < delay:
                waittime = delay - interval
                gbl_logger.debug( f'Sleeping {waittime} seconds before retrieving quote' )
                time.sleep( waittime )

    elif request == 'update':
        #  update quotetime in the config file:
        gbl_config['Settings']['quotetime'] = str( int( time.time() ) )
        try:
            with  open( gbl_configfile, 'w' ) as cf:
                gbl_config.write( cf )
        except OSError as e:
            printerror( f'Unable to update quote time in {gbl_configfile}\n{e.strerror}' )

    return waittime

def retrievequotes():
    """
        Retrieve configured quotes and place them in a .csv file
    """
    csvfilename = gbl_config['Quotes']['csvfile']
    if not csvfilename:
        printerror( "A config setting of [Quotes], csvfile = /path/to/csvfile is required to retrieve multiple quotes" )
        return None

    #  Get ticker symbols, either from our config file or kmymoney file:
    if  gbl_config.has_option( 'Quotes', 'symbols' ):
        symbols = gbl_config['Quotes']['symbols'].split()
    elif  gbl_config.has_option( 'Quotes', 'kmmfile' ):
        symbols = getkmmtickers( gbl_config['Quotes']['kmmfile'] )
    else:
        printerror( 'Config setting "symbols" or "kmmfile" is required to retrieve multiple quotes' )
        return None

    #  Remove any excluded symbols
    if  gbl_config.has_option( 'Quotes', 'exclude' ):
        exclude = gbl_config['Quotes']['exclude'].split()
        for excluded in exclude:
            if  excluded in symbols: symbols.remove(excluded)

    gbl_logger.info( f'Retrieving {len( symbols )} quotes for: {symbols}' )

    rows = csvread( csvfilename )

    for i, ticker in enumerate( symbols, start=1 ) :
        date, price = tdquote( ticker, i, len(symbols) )
        if  date and price:
            for row in rows:
                if  ticker == row[0]  and date == row[1]:
                    row[2] = price
                    break
            else:
                rows.append( [ticker, date, price] )

    rows.sort( key=itemgetter(0,1) )

    with  open( csvfilename, 'w', newline='' ) as csvfile:
        writer = csv.writer( csvfile, delimiter=',', quotechar='"', quoting=csv.QUOTE_ALL )
        writer.writerows( rows )

def getkmmtickers(kmmfile):
    """
        Retrieve all investment ticker symbols with an online source matching the name of this script,
        from the input kmymoney database
    """
    myname = PurePath( sys.argv[0] ).stem.lower()

    try:
        with gzip.open( kmmfile, 'rb' ) as kmy:
            kmmxml = str( kmy.read() )
    except Exception as e:
        printerror( f'Unable to read kmmfile {kmmfile}, error: {str(e)}' )
        return None

    #  extract the <SECURITIES/> section of the kmm database:
    regex = r"<SECURITIES (.*?)</SECURITIES>"
    mat = re.search( regex, kmmxml, re.DOTALL )
    if  not mat:
        printerror( f'Unable to extract security data from Kmymoney file {kmmfile}' )
        return None

    del kmmxml

    #  find all security ticker symbols with an online quote source named the same as this script:
    secxml = mat.group()
    symbols = []
    securities = ET.fromstring( secxml )
    for security in securities:
        if security.tag == 'SECURITY' and 'symbol' in security.attrib and security.attrib['symbol']:
            for  kvpairs in security:
                for  pair in kvpairs:
                    if  pair.tag == 'PAIR' and 'key' in pair.attrib and pair.attrib['key'] == 'kmm-online-source':
                        if  'value' in pair.attrib and pair.attrib['value'].lower() == myname:
                            symbols.append( security.attrib['symbol'] )

    return symbols

def  csvread( file ):
    """
       Read the input CSV file and return a list of rows
    """
    rows = []
    if  Path( file ).exists():
        with open( file, 'r', newline='' ) as csvfile:
            reader = csv.reader( csvfile, delimiter=',', quotechar='"' )
            rows = [ row for row in reader ]
    return rows


def printerror( message ):
    """
       Print an error message to the log and stderr.
    """
    print( message, file=sys.stderr )
    if gbl_logger: gbl_logger.error( message )

if __name__ == '__main__':
    sys.exit( main() )
