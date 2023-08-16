# TDQUOTES
tdquotes.py is a python script intended to be used in KMyMoney as an online quote source, using the [Twelve Data](https://twelvedata.com/) financial service API.

This is alpha level software - use at your own risk.

## Requirements
A Twelve Data API key is required to retrieve quotes.  

[Python](https://www.python.org/) must be installed to run this script. It was written using Python 3.11, so if possible, install Python 3.11 or higher.  It uses features that were introduced in Python 3.6, so it will certainly fail with Python older than 3.6.

## Installation
Download tdquotes.py to your preferred directory for user scripts and make sure it is executable (chmod +x).

## Basic Setup
tdquotes requires a minimum configuration file with your Twelve Data API key. This file should be named tdquotes.conf and should either be in the directory where this script is installed or be named:

**(user home directory)/.config/tdquotes.conf** 

It **MUST** have a [Settings] section with your Twelve Data API key:

```
[Settings] 
apikey = mytwelvedatakey
```
The tdquotes.conf file must be updatable by tdquotes.

Current versions of KMyMoney will not display error messages from an online quote script to the user (this is coming in a future release). Before setting up a quote source in KMyMoney, it is a good idea to test it by running tdquotes as a command, so you can see any error messages if it fails. After setting up tdquotes.conf, open a terminal and navigate to the directory where this is installed and try to fetch a stock quote:

```
cd /path/to/tdquotes.py
./tdquotes.py --fetch GOOG
```
If it is successful, the last line output should be something like:

```
price="130.28999" date="2023-08-15"
```

## KMyMoney Setup
tdquotes.py should be set up as an online quote script in KMyMoney, according to this paragraph in the [Updating Prices](https://docs.kde.org/stable5/en/kmymoney/kmymoney/details.investments.prices.html#details.investments.onlinequotes) section of the KMyMoney handbook:

> Note that the URL can also be a file: URL, which the quote fetcher takes to be the path to an executable script. It will pass any command-line arguments to it that you have specified, and feed the stdout to the page parser. For example, you might have a script called getquote.sh that contains custom quote logic, taking the symbol as a single parameter. Your URL would be “file:/path/to/getquote.sh %1”.

To do this, create a new Online quote source in the KMyMoney configuration.  For reasons explained below in the advanced section, you should name this new online quote source the same name as this script. So if you saved this script as "tdquotes.py", the Online quote source in KMyMoney should be named "tdquotes" or "Tdquotes" or "TDquotes".  The case does not matter, but the online quote name in KMyMoney should match this script's file name, with the .py extension removed.

The tdquotes should be configured as:

```
URL:            file:/path/to/tdquotes.py --fetch %1
Identifier:     %1
Identify by:    Symbol
Price:          price="([^"]+)
Date:           date="([^"]+)
Date Format:    %y %m %d

```
