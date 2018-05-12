#!python2
import appex
import dialogs
import sys
import csv
from datetime import datetime
from ofxtools.Parser import OFXTree
import xml.etree.ElementTree as ET 
import tempfile
import ynab

def read_ofx_from_file(file_path):
    # ING thinks it's a good idea to embed HTML inside XML with no escaping
    # This strips that out.
    ofx_file = open(file_path, 'r')
    ofx_file_content = ofx_file.read().replace("<BR/>", " ")
    ofx_file.close()

    with tempfile.NamedTemporaryFile() as temp:
        temp.write(ofx_file_content)
        temp.seek(0)

        parser = OFXTree()
        parser.parse(temp)

        # need this for a few fields later
        now = datetime.now().date()
        ofx_now_string = now.strftime("%Y%m%d")
        epoch_string = "19700101"

        #check acctfrom exists, if not make it
        #we can use a dummy value since don't need this field in our import
        stmtr = parser.find(".//STMTRS")
        if stmtr is None:
            print "Cannot find STMTR"
            exit(1) 

        acctfrom = parser.find(".//STMTRS/BANKACCTFROM")
        if acctfrom is None:
            acctfrom_tree = ET.fromstring("<BANKACCTFROM><BANKID>0</BANKID><ACCTID>0</ACCTID><ACCTTYPE>SAVINGS</ACCTTYPE></BANKACCTFROM>")

            stmtr.insert(0, acctfrom_tree)

        # We also ignore this, so just put some dummy values
        ledger = parser.find(".//STMTRS/LEDGERBAL")
        if ledger is not None:
            stmtr.remove(ledger)
        ledger_tree = ET.fromstring("<LEDGERBAL><BALAMT>0</BALAMT><DTASOF>"+ofx_now_string+"</DTASOF></LEDGERBAL>")        
        stmtr.insert(0,ledger_tree)

        avail = parser.find(".//STMTRS/AVAILBAL")
        if avail is not None:
            stmtr.remove(avail)
        avail_tree = ET.fromstring("<AVAILBAL><BALAMT>0</BALAMT><DTASOF>"+ofx_now_string+"</DTASOF></AVAILBAL>")        
        stmtr.insert(0,avail_tree) 

        # Again not really used with our import, so just set the maximum time frame
        banktranlist = parser.find(".//BANKTRANLIST")
        if banktranlist is None:
            print "Cannot find BANKTRANLIST"
            exit(1) 

        dtstart = parser.find(".//BANKTRANLIST/DTSTART")
        if dtstart is None:
            
            dtstart_tree = ET.fromstring("<DTSTART>"+epoch_string+"</DTSTART>")
            dtend_tree = ET.fromstring("<DTEND>"+ofx_now_string+"</DTEND>")

            banktranlist.insert(0, dtstart_tree)
            banktranlist.insert(1, dtend_tree)

        # Commbanks fault this time. They have some non-standard date here, at least for this library
        # This standardises them to be the same
        sors = parser.find(".//SONRS")
        if sors is None:
            print "Cannot find SONRS"
            exit(1)

        dtserver = parser.find(".//SONRS/DTSERVER")
        if dtserver is not None:
            sors.remove(dtserver)

        dtserver_val = ET.fromstring("<DTSERVER>"+ofx_now_string+"</DTSERVER>")
        sors.insert(0, dtserver_val)

        return parser.convert()
 
def get_account(account_name, api_client, budget):
  try:
    for a in accounts_response.data.accounts:
      if a.name == account_name:
        return a.id
    return None
  except ynab.rest.ApiException as e:
    print("When trying to get accounts, encounted the error %s" % e)

if appex.is_running_extension():
  ofx_file = appex.get_file_path()
else:
  ofx_file = sys.argv[1]

key_file = open("key.txt", 'r')
key = key_file.readline().strip()
key_file.close()

ynab_config = ynab.configuration.Configuration()
ynab_config.api_key['Authorization'] = key 
ynab_config.api_key_prefix['Authorization'] = 'Bearer'

api_client = ynab.api_client.ApiClient(configuration=ynab_config)

# Get which budget to import into
try:
  budgets = ynab.BudgetsApi(api_client).get_budgets()
except ynab.rest.ApiException as e:
  print("When trying to get the budgets, encoutered error %s" % e)
  exit(1)

budgets_dict = {}

for b in budgets.data.budgets:
  budgets_dict[b.name] = b.id

chosen_budget = dialogs.list_dialog(title="Choose which budget to import data into:",
                                    items = budgets_dict.keys())

if chosen_budget is None:
  exit(0)
  
this_budget = budgets_dict[chosen_budget]
  
#Find which account in the budget to import into 
accounts_response = ynab.AccountsApi(api_client).get_accounts(this_budget)
accounts = {}

for a in accounts_response.data.accounts:
  accounts[a.name] = a.id
  
chosen_account = dialogs.list_dialog(title="Choose which account to import data into:",
                                    items = accounts.keys())

if chosen_account is None:
  exit(0)
  
this_account = accounts[chosen_account]
        
#Dictionary to generate consiste unique ids for
#each transaction to avoid importing twice
import_id_table = {}

transaction_list = []

ofx = read_ofx_from_file(ofx_file)

for record in ofx.statements[0].transactions:

    #Commbank only has one column to show transactions,
    #ING has two. Below allows for this discrepency
    amount = record.trnamt
    amount = int(float(amount)*1000) #This is how the YNAB API repersents money

    imported_date = datetime.now().date()

    date = record.dtposted

    transaction_date = date.date()

    date_str = transaction_date.isoformat()

    transaction_diff = imported_date - transaction_date

    # We only care about the last 30 days
    if transaction_diff.days > 30:
        break

    description = record.memo
    #YNAB has a max character limit of 50
    payee_name = (description.split("- ")[0])[:50]

    import_id_candidate = "YNAB:"+(str(amount))+":"+date_str
    if import_id_candidate in import_id_table:
        num = import_id_table[import_id_candidate]
        import_id_table[import_id_candidate] += 1
    else:
        import_id_table[import_id_candidate] = 1
        num = 1

    import_id = import_id_candidate+":"+str(num)

    transaction = ynab.SaveTransaction(account_id=this_account, 
                                        date=date_str, 
                                        amount=amount, 
                                        payee_name=payee_name,
                                        import_id=import_id)

    transaction_list.append(transaction)

try:
  transactions = ynab.BulkTransactions(transaction_list)
  ynab.ynab.TransactionsApi(api_client).bulk_create_transactions(this_budget, transactions)
  dialogs.alert("Import Complete", button1="Ok", hide_cancel_button=True)
except ynab.rest.ApiException as e:
  print("When trying to commit transctions to YNAB: %s\n" % e)
