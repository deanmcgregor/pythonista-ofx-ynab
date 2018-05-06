#!python2
#import appex
#import dialogs
import sys
import csv
from datetime import datetime

import ynab

def get_account(account_name, api_client, budget):
  try:
    for a in accounts_response.data.accounts:
      if a.name == account_name:
        return a.id
    return None
  except ynab.rest.ApiException as e:
    print("When trying to get accounts, encounted the error %s" % e)

if appex.is_running_extension():
      csv_file = appex.get_file_path()
else:
  csv_file = sys.argv[1]

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


with open(csv_file, 'r') as f:
  #Commbank have CSV files with no headers...
  #Check the first line to see if it's ING or Commbank's CSV file
  first_line = f.readline()
  f.seek(0) #rewind
  if first_line.startswith("Date,"):
    c = csv.DictReader(f)
  else:
    c = csv.DictReader(f, fieldnames=["Date", "Debit", "Description", "Balance", "Category"])

  for record in c:
    #Commbank only has one column to show transactions,
    #ING has two. Below allows for this discrepency
    amount = record["Debit"]
    if amount == "":
      amount = record["Credit"]
    amount = int(float(amount)*1000) #This is how the YNAB API repersents money
    imported_date = datetime.now().date()
    date = record["Date"]
    
    transaction_date = datetime.strptime(date, "%d/%m/%Y").date()
    
    date_str = transaction_date.isoformat()
    
    transaction_diff = imported_date - transaction_date
    
    # We only care about the last 30 days
    if transaction_diff.days > 30:
    	break
    
    description = record["Description"]
    payee_name = description.split("- ")[0]
    
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
except ynab.rest.ApiException as e:
  print("When trying to commit transctions to YNAB: %s\n" % e)
