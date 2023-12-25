# Copyright (c) 2023, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import json
import traceback

import frappe
import requests
from frappe import _
from frappe.model.document import Document
from requests_oauthlib import OAuth2Session

from datetime import datetime, timedelta

from erpnext import encode_company_abbr

@frappe.whitelist()
def callback(*args, **kwargs):
	migrator = frappe.get_doc("Xero Migrator")
	migrator.set_indicator("Connecting to Xero")
	migrator.code = kwargs.get("code")
	migrator.save()
	migrator.get_tokens()
	migrator.xero_tenant_id = migrator.get_tenant_id()[0]["tenantId"]
	frappe.db.commit()
	migrator.set_indicator("Connected to Xero")
	# We need this page to automatically close afterwards
	frappe.respond_as_web_page("Xero Authentication", html="<script>window.close()</script>")

class XeroMigrator(Document):
	def __init__(self, *args, **kwargs):
		super(XeroMigrator, self).__init__(*args, **kwargs)
		self.oauth = OAuth2Session(
			client_id=self.client_id, redirect_uri=self.redirect_url, scope=self.scope
		)
		if not self.authorization_url and self.authorization_endpoint:
			self.authorization_url = self.oauth.authorization_url(self.authorization_endpoint)[0]

	def on_update(self):
		if self.company:
			# We need a Cost Center corresponding to the selected erpnext Company
			self.default_cost_center = frappe.db.get_value("Company", self.company, "cost_center")
			company_warehouses = frappe.get_all(
				"Warehouse", filters={"company": self.company, "is_group": 0}
			)
			if company_warehouses:
				self.default_warehouse = company_warehouses[0].name
		if self.authorization_endpoint:
			self.authorization_url = self.oauth.authorization_url(self.authorization_endpoint)[0]

	@frappe.whitelist()
	def migrate(self):	
		frappe.enqueue_doc("Xero Migrator", "Xero Migrator", "_migrate", queue="long")

	def _migrate(self):
		try:
			self.set_indicator("In Progress") # done
			# Add xero_id field to every document so that we can lookup by Id reference
			# provided by documents in API responses.
			# Also add a company field to Customer Supplier and Item
			self._make_custom_fields() # done

			self._migrate_accounts()

			#-----------------------------------------------------------------	
			self.get_accounts() # done
			self.get_bank_transactions() # payment entries skipped
			self.get_bank_transfers() #skipped, to do: pull and download data
			self.get_batch_payments() #skipped, to do: pull and download data
			self.get_invoices() # done
			self.get_items() # split to items for sale and stock
			self.get_manual_journals() # done
			self.get_tax_rates() # done
			self.get_users()
			self.get_assets() # done
			#-----------------------------------------------------------------

		except Exception as e:
			self.set_indicator("Failed")
			self._log_error(e)

		frappe.db.commit()

	#xero
	def get_tokens(self):
		token = self.oauth.fetch_token(
			token_url=self.token_endpoint, client_secret=self.client_secret, code=self.code
		)
		self.access_token = token["access_token"]
		self.refresh_token = token["refresh_token"]
		self.save()

	#xero
	def _refresh_tokens(self):
		token = self.oauth.refresh_token(
			token_url=self.token_endpoint,
			client_id=self.client_id,
			refresh_token=self.refresh_token,
			client_secret=self.client_secret,
			code=self.code,
		)
		self.access_token = token["access_token"]
		self.refresh_token = token["refresh_token"]
		self.save()
	
	#xero
	def get_tenant_id(self, **kwargs):
		try:
			query_uri = "https://api.xero.com/connections"
			response = self._get(query_uri)
			response_string = response.json()

			return response_string
		except Exception as e:
			self._log_error(e, response.text)

	# done
	def _make_custom_fields(self):
		doctypes_for_xero_id_field = [
			"Account",
			"Customer", 
			"Address",
			"Item",
			"Supplier",
			"Sales Invoice",
			"Journal Entry",
			"Purchase Invoice",
			"Payment Entry",
			"Asset"
		]
		for doctype in doctypes_for_xero_id_field:
			self._make_custom_xero_id_field(doctype)

		doctypes_for_company_field = ["Customer", "Item", "Supplier"]
		for doctype in doctypes_for_company_field:
			self._make_custom_company_field(doctype)

		doctypes_for_bank_transaction_payment_entries_field = ["Bank Transaction"]
		for doctype in doctypes_for_bank_transaction_payment_entries_field:
			self._make_bank_account_payment_entries(doctype)

		doctypes_for_invoice_number_fields = ["Sales Invoice", "Purchase Invoice"]
		for doctype in doctypes_for_invoice_number_fields:
			self._make_invoice_number_field(doctype)

		frappe.db.commit()

	#xero
	def _make_bank_account_payment_entries(self, doctype):
		pass
		# skip for now

	# done
	def _make_custom_xero_id_field(self, doctype):
		if not frappe.get_meta(doctype).has_field("xero_id"):
			frappe.get_doc(
				{
					"doctype": "Custom Field",
					"label": "Xero ID",
					"dt": doctype,
					"fieldname": "xero_id",
					"fieldtype": "Data",
				}
			).insert()

	# done
	def _make_custom_company_field(self, doctype):
		if not frappe.get_meta(doctype).has_field("company"):
			frappe.get_doc(
				{
					"doctype": "Custom Field",
					"label": "Company",
					"dt": doctype,
					"fieldname": "company",
					"fieldtype": "Link",
					"options": "Company",
				}
			).insert()

	def _make_invoice_number_field(self, doctype):
		if not frappe.get_meta(doctype).has_field("invoice_number"):
			frappe.get_doc(
				{
					"doctype": "Custom Field",
					"label": "Invoice Number",
					"dt": doctype,
					"fieldname": "invoice_number",
					"fieldtype": "Data",
				}
			).insert()

	def _migrate_accounts(self):
		# create the root accounts first before migrating the specific accounts
		self._make_root_accounts()

		for entity in ["Account", "TaxRate"]:
			self._migrate_entries(entity)

	def _make_root_accounts(self):
		# classify accounts for easier reporting
		roots = ["Asset", "Equity", "Expense", "Liability", "Income"]
		for root in roots:
			try:
				if not frappe.db.exists(
					{
						"doctype": "Account",
						"name": encode_company_abbr("{} - Xero".format(root), self.company),
						"company": self.company,
					}
				):
					frappe.get_doc(
						{
							"doctype": "Account",
							"account_name": "{} - Xero".format(root),
							"root_type": root,
							"is_group": "1", # root accounts are group accounts
							"company": self.company,
						}
					).insert(ignore_mandatory=True)
			except Exception as e:
				self._log_error(e, root)
		frappe.db.commit()

	def _migrate_entries(self, entity):
		try:
			if entity == "Asset":
				query_uri = "https://api.xero.com/assets.xro/1.0/Assets"
			else:
				query_uri = "{}/{}".format(
					self.api_endpoint,
					entity,
				)
			# Count number of entries
			# fetch pages and accumulate
				
			entries = self._preprocess_entries(entity, entries)
			self._save_entries(entity, entries)

		except Exception as e:
			self._log_error(e, response.text)

	# pulls data from Xero API
	# each of the methods designates Xero data into ERPNext
	# doctypes
	def _save_entries(self, entity, entries):
		entity_method_map = {
			"Account": self._save_account, #EN: Account
			"TaxRate": self._save_tax_rate, #EN: Sales and Purchase Tax
			"Contact": self._save_contact, #EN: Customer and Supplier
			"Item": self._save_item, #EN: Item
			"Invoice": self._save_invoice, #EN: POS, Sales, Purchase Invoice (retrieve individual invoices to retrieve line items)
			"Payment": self._save_payment, #EN: Payment Entry, AP and AR invoices, invoices
			"CreditNote": self._save_credit_note, #EN: Sales Invoice; Credit Note; Payment Entry
			"ManualJournal": self._save_manual_journal, #EN: Journal Entry
			"BankTransaction": self._save_bank_transaction, #EN: Bank Transaction
			"Asset": self._save_asset #EN: Asset

			#"TaxCode": self._save_tax_code,
			#"Preferences": self._save_preference,
			#"Customer": self._save_customer,
			#"Supplier": self._save_vendor,
			#"SalesReceipt": self._save_sales_receipt,
			#"RefundReceipt": self._save_refund_receipt,
			#"VendorCredit": self._save_vendor_credit,
			#"BillPayment": self._save_bill_payment,
			#"Deposit": self._save_deposit,
			#"Advance Payment": self._save_advance_payment,
			# "Tax Payment": self._save_tax_payment,
			# "Sales Tax Payment": self._save_tax_payment,
			# "Purchase Tax Payment": self._save_tax_payment,
			# "Inventory Qty Adjust": self._save_inventory_qty_adjust,
		}
		total = len(entries)
		for index, entry in enumerate(entries, start=1):
			self._publish(
				{
					"event": "progress",
					"message": _("Saving {0}").format(entity),
					"count": index,
					"total": total,
				}
			)
			entity_method_map[entity](entry)
		frappe.db.commit()

	def _preprocess_entries(self, entity, entries):
		entity_method_map = {
			"TaxRate": self._preprocess_tax_rates,
		}
		preprocessor = entity_method_map.get(entity)
		if preprocessor:
			entries = preprocessor(entries)
		return entries

	#xero
	def get_tax_rates(self):
		try:
			query_uri = "{}/TaxRates".format(
				self.api_endpoint
			)
			response = self._get(query_uri).json()

			tax_rates = response["TaxRates"]

			tax_name_with_rates = []

			for tax_rate in tax_rates:
				tax_name_with_rate = self._map_tax_name_to_rate(tax_rate)
				tax_name_with_rates.append(tax_name_with_rate)

			tax_name_with_rates
		except Exception as e:
			self._log_error(e, response.text)

	#xero
	def _map_tax_name_to_rate(self, tax_rate):
		name = tax_rate["Name"]
		rate = tax_rate["DisplayTaxRate"]
		{name: rate}

	#xero
	def get_tax_rate_value(self, tax_name):
		tax_rates_array = self.get_tax_rates(self)

		for tax_rate in tax_rates_array:
			if tax_name in tax_rates_array:
				return tax_rate[tax_name]
			return None  # Key not found in any dictionary

	#xero
	# given an ID:
	# https://api.xero.com/api.xro/2.0/Accounts/{AccountID}
	def get_accounts(self):
		try:
			query_uri = "{}/Accounts".format(
				self.api_endpoint
			)
			response = self._get(query_uri).json()

			accounts = response["Accounts"]

			for account in accounts:
				self._save_account(account)

		except Exception as e:
			self._log_error(e, response.text)

	#xero
	def _save_account(self, account):
		# Account Class in Xero
		root_account_mapping = {
			"ASSET": "Asset",
			"EQUITY": "Equity",
			"EXPENSE": "Expense",
			"LIABILITY": "Liability",
			"REVENUE": "Income"
		}
		
		try:
			if not frappe.db.exists(
				{"doctype": "Account", "xero_id": account["AccountID"], "company": self.company}
			):
				account_type = account["Type"]

				account_dict = {
					"doctype": "Account",
					"xero_id": account["AccountID"],
					"account_number": account["Code"],
					"account_name": self._get_unique_account_name(account["Name"]),
					"root_type": root_account_mapping[account["Class"]],
					"account_type": self._get_account_type(account),
					"company": self.company,
				}

				if account_type == "BANK":
					account_dict["account_currency"] = account["CurrencyCode"]
					self._create_bank_account

				frappe.get_doc(account_dict).insert()
		except Exception as e:
			self._log_error(e, account)

	# done
	def _get_account_type(self, account):
		account_type = account["Type"]

		# Xero SystemAccountattribute Value: Xero Default Account Name
		xero_system_account_mapping = {
			"CREDITORS": "Accounts Payable",
			"DEBTORS":  "Accounts Receivable",
		}

		# If Account Name is a General term, use the
		# name to classify. Or else, use the account type
		# Xero Account Name: ERPNext Account Type
		xero_common_account_name_mapping = {
			"Sales": "Direct Income",
			"Interest Income": "Income",
			"Cost of Goods Sold": "Cost of Goods Sold",
			"Depreciation": "Depreciation",
			"Accounts Receivable": "Receivable",
			"Accounts Payable": "Payable"
		}

		# Xero Account Type: ERPNext Account Type
		xero_account_type_mapping = {
			"BANK": "Bank",
			"CURRENT": "Current Asset",
			"CURRLIAB": "Current Liability",
			"DEPRECIATN": "Depreciation",
			"DIRECTCOSTS": "Direct Expense",
			"EQUITY": "Equity",
			"EXPENSE": "Expense Account",
			"FIXED": "Fixed Asset",
			"INVENTORY": "Current Asset",
			"LIABILITY": "Liability",
			"OTHERINCOME": "Income Account",
			"OVERHEADS": "Indirect Expense",
			"PREPAYMENT": "Income Account",
			"REVENUE": "Direct Income",
			"SALES": "Direct Income",
			"TERMLIAB": "Liability",
			# "NONCURRENT": 
		}

		xero_account_name = account["Name"]
		xero_account_type = account["Type"]

		if account["SystemAccount"] in xero_system_account_mapping:
			account_type = xero_system_account_mapping[account["SystemAccount"]]
		else:
			if xero_account_name in xero_common_account_name_mapping:
				account_type = xero_common_account_name_mapping[xero_account_name]
			else:
				account_type = xero_account_type_mapping[xero_account_type]
		return account_type
	
	def _get_account_name_by_id(self, xero_id):
		return frappe.get_all(
			"Account", filters={"xero_id": xero_id, "company": self.company}
		)[0]["name"]
	
	def _get_account_name_by_code(self, account_code):
		return frappe.get_all(
			"Account", filters={"account_number": account_code, "company": self.company}
		)[0]["name"]
	
	def _save_tax_rate(self, tax_rate):
		try:
			if not frappe.db.exists(
				{
					"doctype": "Account",
					"xero_id": "TaxRate - {}".format(tax_rate["TaxType"]),
					"company": self.company,
				}
			):
				frappe.get_doc(
					{
						"doctype": "Account",
						"xero_id": "TaxRate - {}".format(tax_rate["TaxType"]),
						"account_name": "{} - QB".format(tax_rate["Name"]),
						"root_type": "Liability",
						"parent_account": encode_company_abbr("{} - QB".format("Liability"), self.company),
						"is_group": "0",
						"company": self.company,
					}
				).insert()
		except Exception as e:
			self._log_error(e, tax_rate)

	def _preprocess_tax_rates(self, tax_rates):
		self.tax_rates = {tax_rate["Type"]: tax_rate for tax_rate in tax_rates}
		return tax_rates
	
	def _save_contact(self, contact):
		try:
			if contact["IsCustomer"]:
				self._save_customer(contact)
			elif contact["IsSupplier"]:
				self._save_supplier(contact)
		except Exception as e:
			self._log_error(e, contact)

	def _save_customer(self, contact):
		try:
			if not frappe.db.exists(
				{"doctype": "Customer", "xero_id": contact["ContactID"], "company": self.company}
			):
				try:
					receivable_account = frappe.get_all(
						"Account",
						filters={
							"account_type": "Receivable",
							"account_currency": contact["DefaultCurrency"],
							"company": self.company,
						},
					)[0]["name"]
				except Exception:
					receivable_account = None
				erpcustomer = frappe.get_doc(
					{
						"doctype": "Customer",
						"xero_id": contact["ContactID"],
						"customer_name": encode_company_abbr(contact["Name"], self.company),
						"customer_type": "Individual",
						"customer_group": "Commercial",
						"default_currency": contact["DefaultCurrency"],
						"accounts": [{"company": self.company, "account": receivable_account}],
						"territory": "All Territories",
						"company": self.company,
					}
				).insert()
				self._create_address(erpcustomer, "Customer", contact["Addresses"])
		except Exception as e:
			self._log_error(e, contact)

	def _save_supplier(self, contact):
		try:
			if not frappe.db.exists(
				{"doctype": "Supplier", "xero_id": contact["ContactID"], "company": self.company}
			):
				erpsupplier = frappe.get_doc(
					{
						"doctype": "Supplier",
						"xero_id": contact["ContactID"],
						"supplier_name": encode_company_abbr(contact["Name"], self.company),
						"supplier_group": "All Supplier Groups",
						"company": self.company,
					}
				).insert()
				self._create_address(erpsupplier, "Supplier", contact["Addresses"])
		except Exception as e:
			self._log_error(e)

	def _create_address(self, entity, doctype, addresses):
		try:
			for index, address in enumerate(addresses):
				if not frappe.db.exists({"doctype": "Address", "xero_id": "{} Address{} - Xero".format(entity.name, index)}):
					frappe.get_doc(
						{
							"doctype": "Address",
							"xero_id": "{} Address{} - Xero".format(entity.name, index),
							"address_title": entity.name,
							"address_type": "Other",
							"address_line1": address["AddressLine1"],
							"pincode": address["PostalCode"],
							"city": address["City"],
							"links": [{"link_doctype": doctype, "link_name": entity.name}],
						}
					).insert()
		except Exception as e:
			self._log_error(e, address)

	#xero
	def _save_item(self, item):
		try:
			if not frappe.db.exists(
				{"doctype": "Item", "xero_id": item["ItemID"], "company": self.company}
			):
				item_dict = {
					"doctype": "Item",
					"xero_id": item["ItemID"],
					"item_code": item["Code"],
					"stock_uom": "Unit",
					"is_stock_item": 0,
					"item_name": item["Name"],
					"company": self.company,
					"item_group": "All Item Groups",
					"item_defaults": [{"company": self.company, "default_warehouse": self.default_warehouse}]
				}
				if "PurchaseDetails" in item:
					if item["IsTrackedAsInventory"]:
						account_code = item["PurchaseDetails"]["COGSAccountCode"]
					else:
						account_code = item["PurchaseDetails"]["AccountCode"]
					expense_account = self._get_account_name_by_code(account_code)
					item_dict["item_defaults"][0]["expense_account"] = expense_account
				if "SalesDetails" in item:
					income_account = self._get_account_name_by_code(item["SalesDetails"]["AccountCode"])
					item_dict["item_defaults"][0]["income_account"] = income_account
				frappe.get_doc(item_dict).insert()
		except Exception as e:
			self._log_error(e, item)

	def _get(self, *args, **kwargs):
		kwargs["headers"] = {
			"Accept": "application/json",
			"Authorization": "Bearer {}".format(self.access_token),
			"Xero-tenant-id": self.xero_tenant_id
		}
		response = requests.get(*args, **kwargs)
		# HTTP Status code 401 here means that the access_token is expired
		# We can refresh tokens and retry
		# However limitless recursion does look dangerous
		if response.status_code == 401:
			self._refresh_tokens()
			response = self._get(*args, **kwargs)
		return response

	#xero
	def _get_unique_account_name(self, xero_name, number=0):
		if number:
			xero_account_name = "{} - {} - Xero".format(xero_name, number)
		else:
			xero_account_name = "{} - Xero".format(xero_name)
		company_encoded_account_name = encode_company_abbr(xero_account_name, self.company)
		if frappe.db.exists(
			{"doctype": "Account", "name": company_encoded_account_name, "company": self.company}
		):
			unique_account_name = self._get_unique_account_name(xero_name, number + 1)
		else:
			unique_account_name = xero_account_name
		return unique_account_name

	#xero
	def _log_error(self, execption, data=""):
		frappe.log_error(
			title="Xero Migration Error",
			message="\n".join(
				[
					"Data",
					json.dumps(data, sort_keys=True, indent=4, separators=(",", ": ")),
					"Exception",
					traceback.format_exc(),
				]
			),
		)

	#xero
	def set_indicator(self, status):
		self.status = status
		self.save()
		frappe.db.commit()

	#xero
	# given an ID:
	# https://api.xero.com/api.xro/2.0/BankTransactions/{BankTransactionID}
	def get_bank_transactions(self):
		try:
			query_uri = "{}/BankTransactions".format(
				self.api_endpoint
			)
			response = self._get(query_uri).json()
			bank_transactions = response["BankTransactions"]

			for bank_transaction in bank_transactions:
				self.process_bank_transaction(bank_transaction)

			return response_string
		except Exception as e:
			self._log_error(e, response.text)

	# #xero
	# def _get_bank_account_number(self, bank_account_details):
	# 	if bank_account_details:
	# 		first_account = bank_account_details[0]
	# 		first_account.get("bank_account_number")

	#xero
	def _get_bank_transaction_line_items(self, bank_transaction_line_items):
		for line_item in bank_transaction_line_items:
			frappe.get_doc(
				{
					"doctype": "Payment Entry",
					"xero_id": line_item["LineItemID"],
					"payment_name": line_item["Description"],

				}
			).insert()
				
	#xero
	def process_bank_transaction(self, bank_transaction):
		# check bank_account_transaction.py: do we need to clear the payment_entries when the 
		# transaction has been reconciled?
		status_mapping = {
			"PAID": "Settled",
			"DELETED": "Cancelled"
		}

		if bank_transaction["IsReconciled"] == "true":
			status_mapping[bank_transaction["Status"]] = "Reconciled"
		else:
			status_mapping[bank_transaction["Status"]] = "Unreconciled"

		bank_account_details = frappe.get_list(
			"Account",
			filters={"bank_account_number": bank_transaction["BankAccount"]["Name"],
			},
		)

		# skip Deposit and Withdrawal
		bank_transaction_dict = {
			"doctype": "Bank Transaction",
			"xero_id": bank_transaction["BankTransactionID"],
			"transaction_id": bank_transaction["BankTransactionID"],
			"transaction_type": bank_transaction["Type"],
			"company": self.company,
			"date": bank_transaction["DateString"],
			"status": status_mapping[bank_transaction["Status"]],
			"bank_account": bank_transaction["BankAccount"]["Name"],
			"bank_party_account_number": self._get_bank_account_number(bank_account_details),
			"currency": bank_transaction["CurrencyCode"],
			"reference_number": bank_transaction["Reference"],
			"payment_entries": self._get_bank_transaction_line_items(bank_transaction["LineItems"]),
			"allocated_amount": bank_transaction["Total"],
		}

		frappe.get_doc(
			bank_transaction_dict
		).insert()

	#xero
	# given an ID:
	# https://api.xero.com/api.xro/2.0/BankTransfers/{BankTransferID}
	def get_bank_transfers(self):
		try:
			query_uri = "{}/BankTransfers".format(
				self.api_endpoint
			)
			response = self._get(query_uri)
			response_string = response.json()

			return response_string
		except Exception as e:
			self._log_error(e, response.text)

	#xero
	# given an ID:
	# https://api.xero.com/api.xro/2.0/BatchPayments/{BatchPaymentID}
	def get_batch_payments(self):
		try:
			query_uri = "{}/BatchPayments".format(
				self.api_endpoint
			)
			response = self._get(query_uri)
			response_string = response.json()

			return response_string
		except Exception as e:
			self._log_error(e, response.text)

	#xero
	# given an ID:
	# https://api.xero.com/api.xro/2.0/Invoices/{InvoiceID}
	def get_invoices(self):
		try:
			query_uri = "{}/Invoices".format(
				self.api_endpoint
			)
			response = self._get(query_uri)
			invoices = response.json()
			
			for invoice in invoices:
				self._save_invoice(invoice)

		except Exception as e:
			self._log_error(e, response.text)

	#xero
	def _save_invoice(self, invoice):
		xero_id = "Invoice - {}".format(invoice["InvoiceID"])
		invoice_type = invoice["Type"]	

		if invoice_type == "ACCPAY":
			self._save_purchase_invoice(invoice, xero_id)
		elif invoice_type == "ACCREC":
			self._save_sales_invoice(invoice, xero_id)

	def _save_sales_invoice(self, invoice, xero_id, is_return=False, is_pos=False):
		try:
			invoice_number = invoice["InvoiceNumber"]
			if not frappe.db.exists(
				{"doctype": "Sales Invoice", "xero_id": xero_id, "company": self.company}
			):
				invoice_dict = {
					"doctype": "Sales Invoice",
					"xero_id": xero_id,
					"invoice_number": invoice_number,
					"currency": invoice["CurrencyCode"],
					"conversion_rate": invoice["CurrencyRate"],
					"posting_date": self.get_date_object(invoice["DateString"]),
					"due_date": self.get_date_object(invoice["DueDateString"]),
					"customer": frappe.get_all(
						"Customer",
						filters={
							"xero_id": invoice["Contact"]["ContactID"],
							"company": self.company,
						},
					)[0]["name"],
					
					"is_return": is_return,
					"items": self._get_si_items(invoice),
					"taxes": self._get_taxes(invoice),

					"set_posting_time": "1",
					"disable_rounded_total": 1,
					"company": self.company,
				}
				# when to apply taxes and discounts

				if "Payments" in invoice:
					invoice_dict["payments"] = self._get_invoice_payments(invoice, is_return=is_return, is_pos=is_pos)

				invoice_doc = frappe.get_doc(invoice_dict)
				invoice_doc.insert()
				invoice_doc.submit()
		except Exception as e:
			self._log_error

	#xero
	def _get_si_items(self, invoice, is_return=False):
		items = []
		for line_item in invoice["LineItems"]:
			item = frappe.db.get_all(
				"Item",
				filters={
					"xero_id": line_item["Item"]["ItemID"],
					"company": self.company,
				},
				fields=["name", "code"],
			)[0]
			items.append(
				{
					"item_name": item["name"],
					"item_code": item["code"],
					"conversion_factor": 1,
					"description": line_item["Description"],
					"qty": line_item["Quantity"],
					"price_list_rate": line_item["UnitAmount"],
					"cost_center": self.default_cost_center,
					"warehouse": self.default_warehouse,
					"item_tax_rate": json.dumps(self._get_item_taxes(line_item["TaxType"], line_item["TaxAmount"])),
					"income_account": self._get_account_name_by_id(line_item["AccountId"])
				}
			)
	
		if is_return:
			items[-1]["qty"] *= -1
		
		return items
	
	def _get_pi_items(self, invoice, is_return=False):
		items = []
		for line_item in invoice["LineItems"]:
			item = frappe.db.get_all(
				"Item",
				filters={
					"xero_id": line_item["Item"]["ItemID"],
					"company": self.company,
				},
				fields=["name", "code"],
			)[0]
			items.append(
				{
					"item_name": item["name"],
					"item_code": item["code"],
					"conversion_factor": 1,
					"description": line_item["Description"],
					"qty": line_item["Quantity"],
					"price_list_rate": line_item["UnitAmount"],
					"cost_center": self.default_cost_center,
					"warehouse": self.default_warehouse,
					"item_tax_rate": json.dumps(self._get_item_taxes(line_item["TaxType"], line_item["TaxAmount"])),
					"expense_account": self._get_account_name_by_id(line_item["AccountId"])
				}
			)
		if is_return:
			items[-1]["qty"] *= -1
		
		return items

	
	def _save_purchase_invoice(self, invoice, xero_id, is_return=False, is_pos=False):
		try:
			invoice_number = invoice["InvoiceNumber"]
			if not frappe.db.exists(
				{"doctype": "Purchase Invoice", "xero_id": xero_id, "company": self.company}
			):
				invoice_dict = {
					"doctype": "Purchase Invoice",
					"xero_id": xero_id,
					"invoice_number": invoice_number,
					"currency": invoice["CurrencyCode"],
					"conversion_rate": invoice["CurrencyRate"],
					"posting_date": self.get_date_object(invoice["DateString"]),
					"due_date": self.get_date_object(invoice["DueDateString"]),
					"customer": frappe.get_all(
						"Supplier",
						filters={
							"xero_id": invoice["Contact"]["ContactID"],
							"company": self.company,
						},
					)[0]["name"],
						
					"items": self._get_pi_items(invoice),
					"taxes": self._get_taxes(invoice),
					"payments": self._get_invoice_payments(invoice, is_return=is_return, is_pos=is_pos),

					"set_posting_time": "1",
					"disable_rounded_total": 1,
					"company": self.company,
				}
				# when to apply taxes and discounts
				invoice_doc = frappe.get_doc(invoice_dict)
				invoice_doc.insert()
				invoice_doc.submit()
		except Exception as e:
			self._log_error
	
	def _get_item_taxes(self, tax_type, tax_amount):
		item_taxes = {}
		if tax_type != "NONE":
			tax_head = self._get_account_name_by_id("TaxRate - {}".format(tax_type))
			tax_rate = tax_amount
			item_taxes[tax_head] = tax_rate["RateValue"]
		return item_taxes

	def _get_taxes(self, entry):
		taxes = []
		for line_item in entry["LineItems"]:
			account_head = self._get_account_name_by_id("TaxRate - {}".format(line_item["TaxType"]))
			taxes.append(
				{
					"charge_type": "Actual",
					"account_head": account_head,
					"description": account_head,
					"cost_center": self.default_cost_center,
					"amount": line_item["TaxAmount"],
				}
			)

	def _get_invoice_payments(self, invoice, is_return=False, is_pos=False):
		# to get payments first
		if is_pos:
			amount = invoice["AmountPaid"]
			if is_return:
				amount = -amount
			return [
				{
					"mode_of_payment": "Cash",
					"amount": amount,
				}
			]

	def _save_manual_journal(self, manual_journal):
		# JournalEntry is equivalent to a Journal Entry
		def _get_je_accounts(lines):
			# Converts JounalEntry lines to accounts list
			posting_type_field_mapping = {
				"Credit": "credit_in_account_currency",
				"Debit": "debit_in_account_currency",
			}

			line_amount_abs_value = abs(line["LineAmount"])

			accounts = []
			for line in lines:
				account_name = self._get_account_name_by_code(
					line["AccountCode"]
				)

				if line["LineAmount"] > 0:
					posting_type = "Debit"
				elif line["LineAmount"] < 0:
					posting_type = "Credit"

				accounts.append(
					{
						"account": account_name,
						posting_type_field_mapping[posting_type]: line_amount_abs_value,
						"cost_center": self.default_cost_center,
					}
				)
			return accounts
		
		xero_id = "Journal Entry - {}".format(manual_journal["ManualJournalID"])
		accounts = _get_je_accounts(manual_journal["JournalLines"])
		posting_date = self.json_date_parser(manual_journal["Date"])
		self.__save_journal_entry(xero_id, accounts, posting_date)

	def __save_journal_entry(self, xero_id, accounts, posting_date):
		try:
			if not frappe.db.exists(
				{"doctype": "Journal Entry", "xero_id": xero_id, "company": self.company}
			):
				je = frappe.get_doc(
					{
						"doctype": "Journal Entry",
						"quickbooks_id": xero_id,
						"company": self.company,
						"posting_date": posting_date,
						"accounts": accounts,
						"multi_currency": 1,
					}
				)
				je.insert()
				je.submit()
		except Exception as e:
			self._log_error(e, [accounts, json.loads(je.as_json())])
	
	def _save_bank_transaction(self, bank_transaction):
		try:
			xero_bank_transaction_status_mapping = {
				"Authorised": "Settled",
				"Deleted": "Cancelled"
			}

			if bank_transaction["IsReconciled"] == "true" and bank_transaction["Status"] == "Authorised":
				status = "Reconciled"
			elif bank_transaction["IsReconciled"] == "false" and bank_transaction["Status"] == "Authorised":
				status = "Unreconciled"
			elif bank_transaction["Status"] == "Cancelled":
				status = "Cancelled"

			field_for_transaction_amount_mapping = {
				"RECEIVE": "Deposit",
				"SPEND": "Withdrawal"
			}

			if bank_transaction["Type"].find('RECEIVE') != -1:
				field_type = field_for_transaction_amount_mapping["RECEIVE"]
			else:
				field_type = field_for_transaction_amount_mapping["DEPOSIT"]

			xero_id = "Bank Transaction - {}".format(bank_transaction["BankTransactionID"])
			payment_entries = []

			if not frappe.db.exists(
				{"doctype": "Bank Transaction", "xero_id": bank_transaction["BankTransactionID"], "company": self.company}
			):
				bank_transaction_dict = {
					"doctype": "Bank Transaction",
					"xero_id": xero_id,
					"status": status,
					"transaction_id": bank_transaction["BankTransactionID"],
					"transaction_type": bank_transaction["Type"],
					field_type: bank_transaction["Total"],
					"company": self.company,
					"date": bank_transaction["DateString"],
					"bank_account": bank_transaction["BankAccount"]["Name"],
					"currency": bank_transaction["CurrencyCode"],
					"reference_number": bank_transaction["Reference"],
					"allocated_amount": bank_transaction["Total"],
				}

			if "BatchPayment" in bank_transaction:
				
				bank_transaction_dict["payment_entries"] = payment_entries

			frappe.get_doc(bank_transaction_dict).insert()

		except Exception as e:
			self._log_error(e, bank_transaction)

	def _save_payment(self, payment):
		try:
			invoice_id = payment["Invoice"]["InvoiceID"]

			payment_type_mapping = {
				"ACCRECPAYMENT": "Receive",
				"ACCRECPAYMENT": "Pay",
				"ARCREDITPAYMENT": "Pay",
				"APCREDITPAYMENT": "Receive Refund",
				"AROVERPAYMENTPAYMENT": "Pay Refund",
				"ARPREPAYMENTPAYMENT": "Pay Refund",
				"APPREPAYMENTPAYMENT": "Receive Refund",
				"APOVERPAYMENTPAYMENT": "Receive Refund"
			}
			payment_type = payment_type_mapping[payment["PaymentType"]]
			if payment_type == "Receive":
				self._save_sales_invoice_payment(payment_type, invoice_id, payment)
			elif payment_type == "Pay":
				self._save_purchase_invoice_payment(payment_type, invoice_id, payment)
		except Exception as e:
			self._log_error(e, payment)

	def _save_sales_invoice_payment(self, payment_type, invoice_id, payment):
		if frappe.db.exists(
			{"doctype": "Sales Invoice", "xero_id": invoice_id, "company": self.company}
		):
			invoice = frappe.get_all(
				"Sales Invoice",
				filters={
					"xero_id": invoice_id,
					"company": self.company,
				},
				fields=["name", "customer", "debit_to"],
			)[0]
			reference_doctype = "Sales Invoice"
			self._save_payment_entry(payment_type, reference_doctype, invoice, payment)

	def _save_purchase_invoice_payment(self, payment_type, invoice_id, payment):		
		if frappe.db.exists(
			{"doctype": "Sales Invoice", "xero_id": invoice_id, "company": self.company}
		):
			invoice = frappe.get_all(
				"Purchase Invoice",
				filters={
					"xero_id": invoice_id,
					"company": self.company,
				},
				fields=["name", "customer", "credit_to"],
			)[0]
			reference_doctype = "Purchase Invoice"
			self._save_payment_entry(payment_type, reference_doctype, invoice, payment)
	
	def _save_payment_entry(self, payment_type, reference_doctype, invoice, payment):	
		if not frappe.db.exists(
			{"doctype": "Payment Entry", "xero_id":  payment["PaymentID"], "company": self.company}
		):
			references = []
			references.append({
				"reference_doctype": reference_doctype,
				"reference_name": invoice["InvoiceNumber"],
				"total_amount": invoice["Total"]
			})
			
			frappe.get_doc({
				"doctype": "Payment Entry",
				"xero_id": payment["PaymentID"],
				"payment_type": payment_type,
				"paid_from": self._get_account_name_by_id(payment["Account"]["AccountID"]), 
				"paid_to": self._get_account_name_by_id(invoice["LineItems"][0]["AccountId"]), 
				"paid_amount": payment["Total"], 
				"total_taxes_and_charges": payment["TotalTax"],
				"references": references
			})
	
	def _save_credit_note(self, credit_note):
		if credit_note["Type"] == "ACCRECCREDIT":
			self._save_sales_invoice_credit_note(credit_note, is_return=True)
		elif credit_note["Type"] == "ACCPAYCREDIT":
			self._save_purchase_invoice_credit_note(credit_note, is_return=True)
	
	def _save_sales_invoice_credit_note(self, credit_note, is_return):
		try:
			for allocation in credit_note["Allocations"]:	
				sales_invoice = frappe.get_all(
					"Sales Invoice",
					filters={
						"xero_id": allocation["CustomerRef"]["InvoiceID"],
						"company": self.company,
					},
				)[0],
			if not frappe.db.exists(
				{"doctype": "Sales Invoice", "xero_id": credit_note["CreditNoteID"], "company": self.company}
			):
				invoice_dict = {
					"doctype": "Sales Invoice",
					"xero_id": credit_note["CreditNoteID"],
					"is_return": is_return,
					"return_against": sales_invoice["name"]
				}
				invoice_doc = frappe.get_doc(invoice_dict)
				invoice_doc.insert()
				invoice_doc.submit()
		except Exception as e:
			self._log_error(e, credit_note)

	def _save_purchase_invoice_credit_note(self, credit_note, is_return):
		try:
			for allocation in credit_note["Allocations"]:	
				purchase_invoice = frappe.get_all(
					"Purchase Invoice",
					filters={
						"xero_id": allocation["CustomerRef"]["InvoiceID"],
						"company": self.company,
					},
				)[0],
			if not frappe.db.exists(
				{"doctype": "Purchase Invoice", "xero_id": credit_note["CreditNoteID"], "company": self.company}
			):
				invoice_dict = {
					"doctype": "Purchase Invoice",
					"xero_id": credit_note["CreditNoteID"],
					"is_return": is_return,
					"return_against": purchase_invoice["name"]
				}
				invoice_doc = frappe.get_doc(invoice_dict)
				invoice_doc.insert()
				invoice_doc.submit()
		except Exception as e:
			self._log_error(e, credit_note)

	def _create_bank_account(self, account):
		try:

			if frappe.db.exists(
				{"doctype": "Bank", "xero_id":  account["AccountID"], "company": self.company}
			):
				bank = frappe.get_all(
					"Bank",
					filters={
						"name": account["Name"],
						"company": self.company,
					},
					fields=["name", "customer", "debit_to"],
				)[0]
			else:
				bank = self._create_bank(account["Name"])
		

			if not frappe.db.exists(
				{"doctype": "Bank Account", "xero_id": account["AccountID"], "company": self.company}
			):
				frappe.get_doc({
					"doctype": "Bank Account",
					"xero_id": account["AccountID"],
					"account_name": bank["name"],
					"account_type": account["BankAccountType"],
					"bank_account_no": account["BankAccountNumber"],
				}).insert()
				
		except Exception as e:
			self._log_error(e, account)
			
	def _create_bank(self, bank):
		try:
			if not frappe.db.exists(
				{"doctype": "Bank", "name": bank, "company": self.company}
			):
				frappe.get_doc({
					"doctype": "Bank",
					"bank_name": bank,	
				}).insert()
		except Exception as e:
			self._log_error(e, bank)

	def _save_asset(self, asset):
		try:
			if asset["assetStatus"] == "REGISTERED":
				if not frappe.db.exists(
					{"doctype": "Asset", "xero_id": asset["assetId"], "company": self.company}
				):
					frappe.get_doc({
						"doctype": "Asset",
						"xero_id": asset["assetId"],
						"item_code": self._get_asset_item_code(asset["assetNumber"]),
						"is_existing_asset": 1,
						"gross_purchase_amount": asset["purchasePrice"],
						"purchase_date": asset["purchaseDate"]
					})
		except Exception as e:
			self._log_error(e, asset)

	#xero
	# given an ID:
	# https://api.xero.com/api.xro/2.0/Items/{ItemID}
	def get_items(self):
		try:
			query_uri = "{}/Items".format(
				self.api_endpoint
			)
			response = self._get(query_uri).json()
			items = response["Items"]

			for item in items:
				self._save_item(item)

		except Exception as e:
			self._log_error(e, response.text)

	#xero
	# given an ID:
	# https://api.xero.com/api.xro/2.0/ManualJournals/{JournalID}
	# In ERPNext, Journal Entries correspond to Journals/Manual Journals in Xero
	def get_manual_journals(self):
		try:
			pages = [1]
			uri_strings = []

			for page in pages:
				query_uri = "{}/ManualJournals?page={}".format(
					self.api_endpoint, page
				)
				response = self._get(query_uri) # check first page of Manual Journal
				page_response = response.json()
				manual_journal = page_response["ManualJournal"] #Check if Manual Journal object contains entries
				if manual_journal:
					# if array is not empty, append the URL string to the uri_strings_array
					uri_strings.append(query_uri)
					# increment the page
					page += 1	
					# append the page to the pages array
					pages.append(page)
					

			for uri_string in uri_strings:
				response = self._get(uri_string)
				manual_journal_content = response.json()
				self.process_manual_journal_entries(manual_journal_content)

		except Exception as e:
			self._log_error(e, response.text)

	def process_manual_journal_entries(self, manual_journal_content):
		for entry in manual_journal_content:
			journal_entry_dict = {
				"xero_id": entry["ManualJournalID"],
				"company": self.company,
				"title": entry["Narration"],
				"posting_date": self.get_date_from_timestamp(self.timestamp_string[entry["Date"]]),
				"accounts":  self.get_journal_entry_accounts(entry["JournalLines"])
			}
	
	#xero
	def get_journal_entry_accounts(self, journal_lines):
		journal_entry_accounts = []

		for line in journal_lines:
			account = frappe.db.get_value("Account", {"account_number": line["Account"]}, "account_name")
			journal_line_dict = {
				"reference_name": line["Description"],
				"account": account
			}

			if line["LineAmount"] > 0:
				journal_line_dict["debit"] = line["LineAmount"]
			else:
				journal_line_dict["credit"] = line["LineAmount"]

			journal_entry_accounts.append(journal_line_dict)

		return journal_entry_accounts

	#xero
	# given an ID:
	# https://api.xero.com/api.xro/2.0/TaxRates/{TaxRateID}
	def get_tax_rates(self):
		try:
			query_uri = "{}/TaxRates".format(
				self.api_endpoint
			)
			response = self._get(query_uri)
			response_string = response.json()

			return response_string
		except Exception as e:
			self._log_error(e, response.text)

	#xero
	# given an ID:
	# https://api.xero.com/api.xro/2.0/Users/{UserID}
	def get_users(self):
		try:
			query_uri = "{}/Users".format(
				self.api_endpoint
			)
			response = self._get(query_uri)
			response_string = response.json()

			return response_string
		except Exception as e:
			self._log_error(e, response.text)

	#xero
	def get_date_from_timestamp(self, timestamp_string):
		timestamp = int(timestamp_string.split('(')[1].split('+')[0])
		date_object = datetime.utcfromtimestamp(timestamp / 1000.0)

		date_object.date().strftime("%m-%d-%Y")

	#xero
	def get_date_object(self, date_time_string):
		date_time_object = self.date_and_time_parser(self, date_time_string)
		extracted_date = date_time_object.date()

		extracted_date.strftime("%m-%d-%Y")

	#xero
	def get_time_object(self, date_time_string):
		date_time_object = date_time_string.date()
		date_time_object.time()

	#xero
	def date_and_time_parser(self, date_time_string):
		date_time_string = "2009-05-27 00:00:00"

		try:
			datetime.strptime(date_time_string, "%Y-%m-%dT%H:%M:%S")

		except ValueError:
			# If parsing fails, the string does not match the specified format
			pass

	def json_date_parser(self, json_date):
		milliseconds = int(json_date[7:20])
		seconds = milliseconds / 1000.0
		date_object = datetime.utcfromtimestamp(seconds)

		timezone_offset = int(json_date[20:24]) * 60
		date_object = date_object - timedelta(minutes=timezone_offset)

		formatted_date = date_object.strftime("%Y-%m-%d")

		return formatted_date
	
	#xero
	def get_assets(self):
		try:
			query_uri = "https://api.xero.com/assets.xro/1.0/Assets"

			response = self._get(query_uri)
			assets = response.json()

			for asset in assets:
				self._process_assets(asset)
		except Exception as e:
			self._log_error(e, response.text)

	#xero
	def _process_assets(self, asset):
		asset_status_mapping = {
			"DRAFT": "Draft",
			"REGISTERED": "Submitted",
			"DISPOSED": "Scrapped"
		}

		asset_dict = {
			"xero_id": asset["assetId"],
			"item_name": asset["assetName"],
			"item_code": asset["assetNumber"],
			"company": self.company,
			"purchase_date": self.get_date_object(asset["purchaseDate"]), 
			"purchase_receipt_amount": asset["purchasePrice"],
			"assetStatus": asset_status_mapping[asset["assetStatus"]],
			"value_after_depreciation": asset["bookDepreciationDetail"]["residualValue"],
		}

		frappe.get_doc(
			asset_dict
		).insert()


# Do we indicate the taxes directly in the Accounts? oir in the TaxRates