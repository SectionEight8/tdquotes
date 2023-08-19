#!/usr/bin/env python3
#
#   This script is intended to be called by KMyMoney to retrieve stock quotes from twelvedata.com
#
#   License: MIT
#

import configparser
import csv
import fcntl
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

class lock:
    def __init__(self, name ):
        self.name = name

    def __enter__(self ):
        # acquire this lock:
        self.fobj = open( f'/tmp/tdquotes_{self.name}.lck', "wb" )
        starttime = int( time.time() )
        fcntl.flock( self.fobj.fileno(), fcntl.LOCK_EX )
        locktime = int( time.time() ) - starttime
        if locktime > 1:
            logger.debug( f'Waited {locktime} seconds to acquire {self.name} lock')

    def __exit__(self, exc_type, exc_val, exc_tb):
        #  release the lock:
        fcntl.flock( self.fobj.fileno(), fcntl.LOCK_UN )
        self.fobj.close()
        return None

# default path name of our config file:
configfile = Path.home() / '.config' / 'tdquotes.conf'
config = configparser.ConfigParser()
logger = logging.getLogger( __name__ )

quotelock = lock( 'quotelock' )       # lock to single thread quote retrievals
csvlock   = lock( 'csvlock' )         # lock to single thread csv file updates

def main():
    global configfile

    #  Set config defaults:
    config['Settings'] = {'quotetime': '0',
                           'delay'    : '8'}
    config['Logging']  = {'loglevel': 'ERROR'}
    config['Quotes']   = {'csvfile' : ''}

    # find our config file - return with error if it doesn't exist
    configfile = getconfigfile()
    if not configfile:
        return 0

    config.read( configfile )
    config.sections()

    #  Initialize the logger:
    if  config.has_option( 'Logging', 'logfile' ):
        logfile = config['Logging']['logfile']
        if  logfile.lower() == 'syslog':
            handler = logging.handlers.SysLogHandler( address='/dev/log' )
        else:
            handler = logging.FileHandler( logfile )
    else:
        handler = logging.NullHandler()

    logger.addHandler( handler )

    try:
        logging.basicConfig( style='{',
                             format='{asctime} {levelname:<8} {message}',
                             datefmt='%a, %d %b %Y %H:%M:%S' )
    except Exception as e:
        printerror( f'Unable to initialize log: {e}' )

    loglevel = config['Logging']['loglevel']
    try:
        logger.setLevel( loglevel )
    except ValueError as e:
        printerror( f'Error setting log level: {e}' )
        logger.setLevel( logging.ERROR )

    if not config.has_option( 'Settings', 'APIkey' ):
        printerror( f'Your config file - {configfile} - must specify your Twelve Data API key' )
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
        logger.debug( 'reply to Kmymoney:' )
        logger.debug( strout )
        print( strout )

    return 0

def getconfigfile():
    """
        Find "tdquotes.conf" if it exists.  If not, issue an error and return None
    """
    if  configfile.exists():
        file = configfile
    else:
        file = Path( sys.argv[0] ).parent / "tdquotes.conf"
        if  not file.exists():
            printerror( f'A config file of {file} or {configfile} with your Twelve Data API key is required' )
            file = None

    return file



def fetchquote( ticker ):
    """
       Fetch a quote for the input ticker symbol

       First, search the configured .csv file for a quote retrieved by the "--retrieve" request.
       If a csv file is not configured, does not exist, or has no quote for the input ticker,
       get a quote directly from Twelve Data
    """
    csvfilename = config['Quotes']['csvfile']
    date = price = None
    if  csvfilename  and  Path( csvfilename ).exists():
        with csvlock:
            rows = csvread( csvfilename )
            for ix, row in enumerate(rows):
                if  row[0] == ticker:
                    date = row[1]
                    price = row[2]
                    logger.info( f'Quote for {ticker} retrieved from {csvfilename}: price={price}, date={date}' )

                    #  delete the row we just read from the csv file and update it:
                    del rows[ix]
                    csvwrite( csvfilename, rows )
                    break

    # if we couldn't get a quote from the csvfile, fetch directly from twelve data:
    if  date is None or price is None:
        date, price = tdquote( ticker )

    return date, price

def tdquote( ticker, count=0, total=0 ):
    """
      Retrieve a quote from twelvedata.com for the input ticker symbol.  Wait if necessary
    """
    apikey = config['Settings']['apikey']
    url = f'https://api.twelvedata.com/eod?symbol={ticker}&apikey={apikey}'
    req = urllib.request.Request( url )
    req.add_header( 'User-agent', 'Mozilla/5.0' )

    logger.debug( f'URL to retrieve {ticker}: {url}' )

    #  If a --retrieve call is running at the same time a kmm user is downloading quotes with --fetch calls, we could
    #  have problems here - we could retrieve too many quotes from twelve data and experience failures or (maybe??)
    #  have our API key revoked. So we single thread through the quote retrieval from twelve data here.
    with quotelock:
        waittime = tddelay( 'wait' )

        try:
            with urllib.request.urlopen( req ) as response:
                mktdata = response.read().decode()
        except urllib.error.URLError as e:
            printerror( f'URLError on URL for {ticker}\n{url}:\nError: {e.reason}' )
            return None, None

        tddelay( 'update' )

    logger.debug( f'twelvedata.com response:\n{mktdata}' )

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
        logger.info( f'{count} of {total} quotes: {ticker} from twelvedata.com date:{date}  price:{price}, '
                     f'waited {waittime} seconds' )
    else:
        logger.info( f'{ticker} from twelvedata.com date:{date}  price:{price}, waited {waittime} seconds' )

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
        quotetime = int( config['Settings']['quotetime'] )
        delay = int( config['Settings']['delay'] )
        if quotetime:
            interval = int(time.time()) - quotetime
            if interval < delay:
                waittime = delay - interval
                logger.debug( f'Sleeping {waittime} seconds before retrieving quote' )
                time.sleep( waittime )

    elif request == 'update':
        #  update quotetime in the config file:
        config['Settings']['quotetime'] = str( int( time.time() ) )
        try:
            with  open( configfile, 'w' ) as cf:
                config.write( cf )
        except OSError as e:
            printerror( f'Unable to update quote time in {configfile}\n{e.strerror}' )

    return waittime

def retrievequotes():
    """
        Retrieve configured quotes and place them in a .csv file
    """
    csvfilename = config['Quotes']['csvfile']
    if not csvfilename:
        printerror( "A config setting of [Quotes], csvfile = /path/to/csvfile is required to retrieve multiple quotes" )
        return None

    #  Get ticker symbols, either from our config file or kmymoney file:
    if  config.has_option( 'Quotes', 'symbols' ):
        symbols = config['Quotes']['symbols'].split()
    elif  config.has_option( 'Quotes', 'kmmfile' ):
        symbols = getkmmtickers( config['Quotes']['kmmfile'] )
    else:
        printerror( 'Config setting "symbols" or "kmmfile" is required to retrieve multiple quotes' )
        return None

    #  Remove any excluded symbols
    if  config.has_option( 'Quotes', 'exclude' ):
        exclude = config['Quotes']['exclude'].split()
        for excluded in exclude:
            if  excluded in symbols: symbols.remove(excluded)

    logger.info( f'Retrieving {len( symbols )} quotes for: {symbols}' )

    quotes = []
    for i, ticker in enumerate( symbols, start=1 ) :
        quotes.append( [ticker, tdquote( ticker, i, len(symbols) )] )

    with csvlock:
        rows = csvread( csvfilename )

        for  ticker, (date, price) in quotes:
            if  date and price:
                for row in rows:
                    if  ticker == row[0]  and date == row[1]:
                        row[2] = price
                        break
                else:
                    rows.append( [ticker, date, price] )

        rows.sort( key=itemgetter(0,1) )

        csvwrite( csvfilename, rows )

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

def csvwrite( file, rows ):
    """
        Write the input rows[] to the input csv file.  
    """
    with  open( file, 'w', newline='' ) as csvfile:
        writer = csv.writer( csvfile, delimiter=',', quotechar='"', quoting=csv.QUOTE_ALL )
        writer.writerows( rows )
def printerror( message ):
    """
       Print an error message to the log and stderr.
    """
    print( message, file=sys.stderr )
    if logger: logger.error( message )

if __name__ == '__main__':
    sys.exit( main() )
