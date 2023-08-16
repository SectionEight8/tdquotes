# TDQUOTES
tdquotes.py is a python script intended to be used by KMyMoney as an online quote source, using [Twelve Data](https://twelvedata.com/).

## Requirements
A Twelve Data API key is required to retrieve quotes.  

[Python](https://www.python.org/) must be installed to run this script. It was written using Python 3.11, so if possible, install Python 3.11 or highter.  It uses features that were introduced in Python 3.6, so it will probably fail with Python older than 3.6.

## Installation
Download tdquotes.py to your preferred directory for user scripts and make sure it is executable (chmod +x).

## Setup
tdquotes requires a minimum configuration file with your Twelve Data API key. This file should be named

**(user home directory)/.config/tdquotes.conf** and should contain:

`[Settings] 
apikey = mytwelvedatakey
`
