# OFX Import Script for YNAB

This script imports OFX files to YNAB using their (currently private) API. 

This script has been tested with OFX files from ING Australia and the Commonwealth Bank. They both have some incompatabilities with the ofxtools library I've used, so there's some munging of the XML to make it work. Not tested for other banks, YMMV.

It is designed to be used with Pythonista on iOS. The script is set up so that you can use the iOS sharing interface with Pythonista to call this script.
That should allow you to grab a CSV from the web and auto-import it into YNAB.
