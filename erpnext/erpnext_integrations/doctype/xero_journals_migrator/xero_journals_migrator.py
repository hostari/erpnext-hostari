# Copyright (c) 2024, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import json
import traceback

import frappe
import requests
from frappe import _
from frappe.model.document import Document
from requests_oauthlib import OAuth2Session
import re

from datetime import datetime, timedelta
from erpnext import encode_company_abbr

@frappe.whitelist()
def callback(*args, **kwargs):
	migrator = frappe.get_doc("Xero Journals Migrator")
	migrator.set_indicator("Connecting to Xero")
	migrator.code = kwargs.get("code")
	migrator.save()
	migrator.get_tokens()
	migrator.xero_tenant_id = migrator.get_tenant_id()[0]["tenantId"]
	migrator.save()
	frappe.db.commit()
	migrator.set_indicator("Connected to Xero")
	# We need this page to automatically close afterwards
	frappe.respond_as_web_page("Xero Authentication", html="<script>window.close()</script>")

class XeroJournalsMigrator(Document):
	def __init__(self, *args, **kwargs):
		super(XeroJournalsMigrator, self).__init__(*args, **kwargs)
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
		self._migrate()
		#frappe.enqueue_doc("Xero Journals Migrator", "Xero Journals Migrator", "_migrate", queue="long", timeout=5000)

	def _migrate(self):
		try:
			self.set_indicator("In Progress") # done
			# Add xero_id field to every document so that we can lookup by Id reference
			# provided by documents in API responses.
			# Also add a company field to Customer Supplier and Item
			self._make_custom_fields() # done

			self._migrate_accounts()

			entities_for_normal_transform = [
				"Journal",
			]

			for entity in entities_for_normal_transform:
				self._migrate_entries(entity)

			self.set_indicator("Complete")
		except Exception as e:
			self.set_indicator("Failed")
			self._log_error(e)

	def _make_custom_fields(self):
		doctypes_for_xero_id_field = [
			"Account",
			"Journal Entry",
		]
		for doctype in doctypes_for_xero_id_field:
			self._make_custom_xero_id_field(doctype)

		self._create_bank_account_number_field()

		frappe.db.commit()

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

	# Xero does not expose bank name and bank information
	# Create a bank account number field in Account instead
	def _create_bank_account_number_field(self):
		doctype = "Account"
		self._log_error("Response", f"Response: bank_account_number")
		if not frappe.get_meta(doctype).has_field("bank_account_number"):
			frappe.get_doc(
				{
					"doctype": "Custom Field",
					"label": "Bank Account Number",
					"dt": doctype,
					"fieldname": "bank_account_number",
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
		roots = ["Asset", "Equity", "Expense", "Liability", "Revenue"]
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
			pluralized_entity_name = "{}s".format(entity)
			query_uri = "{}/{}".format(
				self.api_endpoint,
				pluralized_entity_name,
			)
			
			# Count number of entries
			# fetch pages and accumulate
				
			entities_for_pagination = {
				"Account": False,
				"TaxRate": False,
				"Journal": False,
			}

			entities_for_offset = {
				"Account": False,
				"TaxRate": False,
				"Journal": True,
			}

			offsetter = {
				"Journal": "JournalNumber",
			}
			
			if entities_for_pagination[entity] == True and entities_for_offset[entity] == False:
				re = self.query_with_pagination(entity)
			elif entities_for_pagination[entity] == False and entities_for_offset[entity] == True:
				results = self._query_with_offset(entity, offsetter[entity])
			else:				
				response = self._get(query_uri)

				#self._save_entries(entity, content)

				if response.status_code == 200:
					response_json = response.json()

					if pluralized_entity_name in response_json and response_json[pluralized_entity_name]:
						results = response_json[pluralized_entity_name]
						
			#self._log_error(entity, results)
			self._save_entries(entity, results)
		except Exception as e:
			self._log_error(e)
	
	def query_with_pagination(self, entity):
		pluralized_entity_name = "{}s".format(entity)
		query_uri = "{}/{}".format(
			self.api_endpoint,
			pluralized_entity_name,
		)

		entries = []
		pages = [1] 

		try:
			while pages:
				next_page_url = f"{query_uri}?page={pages[0]}"
				response = self._get(next_page_url)
				current_page = pages.pop(0)

				if response.status_code == 200:
					response_json = response.json()
					if pluralized_entity_name in response_json:
						results = response_json[pluralized_entity_name]
						
						if len(results) != 0:
							entries.extend(results)
							next_page = current_page + 1

							pages.append(next_page)
			return entries
		except Exception as e:
			self._log_error(e)

	def _query_with_offset(self, entity, offsetter):
		pluralized_entity_name = "{}s".format(entity)
		query_uri = "{}/{}".format(
			self.api_endpoint,
			pluralized_entity_name,
		)

		try:
			entries = []
			offset_values = []
			last_offset_values = []

			# check the first page without offset
			response = self._get(query_uri)

			if response.status_code == 200:
				response_json = response.json()

				if pluralized_entity_name in response_json and len(response_json[pluralized_entity_name]) != 0:
					results = response_json[pluralized_entity_name]
				
					for result in results:
						offset_values.append(result[offsetter])

					last_offset_value = offset_values[-1]
					last_offset_values.append(last_offset_value)

				if offset_values:						
					entries.extend(results)
								
					while last_offset_values:
						current_page = last_offset_values.pop(0)

						next_page_url = f"{query_uri}?offset={current_page}"
						response = self._get(next_page_url)

						if response.status_code == 200:
							response_json = response.json()

							if pluralized_entity_name in response_json:
								results = response_json[pluralized_entity_name]

								if len(results) != 0:
									entries.extend(results)
									next_page = current_page + 100

									last_offset_values.append(next_page)	
			return entries
		except Exception as e:
			self._log_error(e)

	def _get(self, *args, **kwargs):
		try:
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
		except requests.exceptions.HTTPError as err:
			print(f"HTTP Error: {err}")
		except requests.exceptions.RequestException as err:
			print(f"An error occurred: {err}")
		except Exception as err:
			print(f"Unexpected error: {err}")

	def set_indicator(self, status):
		self.status = status
		self.save()
		frappe.db.commit()

	def get_tokens(self):
		token = self.oauth.fetch_token(
			token_url=self.token_endpoint, client_secret=self.client_secret, code=self.code
		)
		self.access_token = token["access_token"]
		self.refresh_token = token["refresh_token"]
		self.save()
	
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

	def get_tenant_id(self, **kwargs):
		try:
			kwargs["headers"] = {
				"Accept": "application/json",
				"Authorization": "Bearer {}".format(self.access_token),
			}

			query_uri = "https://api.xero.com/connections"
			#response = self._get(query_uri)
			response = requests.get(query_uri, **kwargs)

			response_string = response.json()

			return response_string
		except Exception as e:
			self._log_error(e, response.text)
	
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

	def _save_entries(self, entity, entries):
		entity_method_map = {
			"Account": self._save_account, #EN: Account
			"TaxRate": self._save_tax_rate, #EN: Sales and Purchase Tax
			"Journal": self._save_journal, #EN: Journal Entry: Xero-added transactions
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
	
	def _save_account(self, account):
		# Account Class in Xero
		root_account_mapping = {
			"ASSET": "Asset",
			"EQUITY": "Equity",
			"EXPENSE": "Expense",
			"LIABILITY": "Liability",
			"REVENUE": "Revenue"
		}
		
		try:
			account_type = account["Type"]
			if not frappe.db.exists(
				{"doctype": "Account", "xero_id": account["AccountID"], "company": self.company}
			):
				parent_account = encode_company_abbr(
					"{} - Xero".format(root_account_mapping[account["Class"]]), self.company
				)

				account_dict = {
					"doctype": "Account",
					"xero_id": account["AccountID"],
					"account_number": account["Code"],
					"account_name": self._get_unique_account_name(account["Name"]),
					"root_type": root_account_mapping[account["Class"]],
					"account_type": self._get_account_type(account),
					"company": self.company,
					"parent_account": parent_account,
					"is_group": 0
				}

				if account_type == "BANK":
					account_dict["account_currency"] = account["CurrencyCode"]
					account_dict["bank_account_number"] = account["BankAccountNumber"]

				frappe.get_doc(account_dict).insert()
		except Exception as e:
			self._log_error(e, account)

	def _save_tax_rate(self, tax_rate):
		try:
			if not frappe.db.exists(
				{
					"doctype": "Account",
					"xero_id": "TaxRate - {}".format(tax_rate["TaxType"]),
					"company": self.company,
				}
			):
				tax_rate_dict = {
					"doctype": "Account",
					"xero_id": "TaxRate - {}".format(tax_rate["TaxType"]),
					"account_name": "{} - Xero".format(tax_rate["Name"]),
					"root_type": "Liability",
					"parent_account": encode_company_abbr("{} - Xero".format("Liability"), self.company),
					"is_group": "0",
					"company": self.company,
					}
				frappe.get_doc(tax_rate_dict).insert()

		except Exception as e:
			self._log_error(e, tax_rate)

	def _save_journal(self, journal):
		# Journal is equivalent to a Xero-added journal entry
		accounts = []
		descriptions = []
		
		def _get_je_accounts(lines):
			# Converts JounalEntry lines to accounts list
			posting_type_field_mapping = {
				"Credit": "credit_in_account_currency",
				"Debit": "debit_in_account_currency",
			}

			for line in lines:
				# gets the description from one of the lines
				if "Description" in line:
					descriptions.append(line["Description"])

				# gives information if Xero amount is positive or negative
				# In Xero, the use of (+) and (-) signs only signify the placement of the amount (debit or credit column)
				# In ERPNext, amount will be saved as absolute values
				net_amount = line["NetAmount"]
				tax_amount = line["TaxAmount"]

				if tax_amount == 0: # no need to get absolute value yet if the amount is being compared to 0
					amount = net_amount
				else:
					if line["TaxType"] != "NONE":
						amount = net_amount

				account_name = self._get_account_name_by_code(
					line["AccountCode"]
				)
				# In Xero, the use of (+) and (-) signs only signify the placement of the amount (debit or credit column)
				# In ERPNext, amount will be saved as absolute values

				if amount > 0:
					posting_type = "Debit"
				elif amount < 0:
					posting_type = "Credit"

				accounts.append(
					{
						"account": account_name,
						posting_type_field_mapping[posting_type]: abs(amount),
						"cost_center": self.default_cost_center,
					}
				)

			return accounts
			
		xero_id = "Journal Entry - {}".format(journal["JournalID"])
		accounts = _get_je_accounts(journal["JournalLines"])
		posting_date = self.json_date_parser(journal["JournalDate"])
		
		self.__save_journal_entry(xero_id, accounts, descriptions, posting_date)

	def __save_journal_entry(self, xero_id, accounts, descriptions, posting_date):
		try:
			if not frappe.db.exists(
				{"doctype": "Journal Entry", "xero_id": xero_id, "company": self.company}
			):
				je_dict = {
					"doctype": "Journal Entry",
					"xero_id": xero_id,
					"company": self.company,
					"posting_date": posting_date,
					"accounts": accounts,
					"multi_currency": 1,
				}
				
				if len(descriptions) != 0:
					title = descriptions[0][:140]
					user_remark = ",".join(descriptions)
					je_dict["title"] = title
					je_dict["user_remark"] = user_remark
				je = frappe.get_doc(je_dict)
				je.insert()
				je.submit()

		except Exception as e:
			self._log_error(e,)

	def _publish(self, *args, **kwargs):
		frappe.publish_realtime("xero_progress_update", *args, **kwargs, user=self.modified_by)

	def _get_account_name_by_code(self, account_code):
		return frappe.get_all(
			"Account", filters={"account_number": account_code, "company": self.company}
		)[0]["name"]
	
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
			"Sales": "Sales",
			"Interest Income": "Interest Income",
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
			"DIRECTCOSTS": "Direct Costs",
			"EQUITY": "Equity",
			"EXPENSE": "Expense",
			"FIXED": "Fixed Asset",
			"INVENTORY": "Inventory",
			"LIABILITY": "Liability",
			"OTHERINCOME": "Other Income",
			"OVERHEADS": "Overhead",
			"PREPAYMENT": "Prepayment",
			"REVENUE": "Revenue",
			"SALES": "Sales",
			"TERMLIAB": "Non-current Liability",
			"NONCURRENT": "Non-current Asset"
		}

		xero_account_name = account["Name"]
		xero_account_type = account["Type"]

		if "SystemAccount" in xero_system_account_mapping:
			account_type = xero_system_account_mapping[account["SystemAccount"]]
		else:
			if xero_account_name in xero_common_account_name_mapping:
				account_type = xero_common_account_name_mapping[xero_account_name]
			else:
				account_type = xero_account_type_mapping[xero_account_type]
		return account_type
	
	def json_date_parser(self, json_date):
		match = re.search(r'\((\d+)\+(\d+)\)', json_date)

		if match:
			numeric_part = match.group(1)
			milliseconds = int(numeric_part)

			seconds = milliseconds / 1000.0
			date_object = datetime.utcfromtimestamp(seconds)

			offset_part = match.group(2)

			timezone_offset = int(offset_part) * 60
			date_object = date_object - timedelta(minutes=timezone_offset)

			formatted_date = date_object.strftime("%Y-%m-%d")

			return formatted_date