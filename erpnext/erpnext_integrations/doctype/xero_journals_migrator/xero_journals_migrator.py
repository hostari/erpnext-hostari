# Copyright (c) 2024, Frappe Technologies Pvt. Ltd. and contributors
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
				#self._query_by_pages(query_uri, pluralized_entity_name)
				self.query_with_pagination(entity)
			if entities_for_pagination[entity] == False and entities_for_offset[entity] == True:
				self._query_with_offset(entity, offsetter[entity])
			else:				
				response = self._get(query_uri)

				#self._save_entries(entity, content)

				if response.status_code == 200:
					response_json = response.json()
				
					self._log_error("Response", f"Response: {response_json}{type(response_json)}")
				else:
					self._log_error("Response", f"Error: {response.status_code} - {response.reason} {response.headers} {response.text} {query_uri}")
		except Exception as e:
			self._log_error(e)

	def _query_by_pages(self, query_uri, pluralized_entity_name):
		pages = [1]
		initial_response = self._get(f"{query_uri}?page={pages[0]}")

		if initial_response.status_code == 200:
			initial_response_json = initial_response.json()

			if pluralized_entity_name in initial_response_json and len(initial_response_json[pluralized_entity_name]) != 0:
				while pages:
					page = pages.pop(0)  # Get the first page from the list

					# Retrieve data for the current page
					response = self._get(f"{query_uri}?page={page}")

					if response.status_code == 200:
						response_json = response.json()
						self._log_error("Response", f"Response: {response_json}{type(response_json)} page{page}")
						if pluralized_entity_name in response_json and len(response_json[pluralized_entity_name]) != 0:
							next_page = page + 1
							uri_string = f"{query_uri}?page={next_page}"

							# Retrieve data for the next page
							content = self._get(uri_string)

							# Preprocess and save entries
							# self._preprocess_entries(entity, content)
							# self._save_entries(entity, content)
							if response.status_code == 200:
								content_json = content.json()
								self._log_error("Response", f"Response: {content_json}{type(content_json)} query uri{uri_string}")
								# Append the next page to pages
								pages.append(next_page)
							else:
								self._log_error("Response", f"Error: {content.status_code} - {content.reason} {content.headers} {content.text} {query_uri}")
					else:
						self._log_error("Response", f"Error: {response.status_code} - {response.reason} {response.headers} {response.text} {query_uri}")
		else:
			self._log_error("Response", f"Error: {initial_response.status_code} - {initial_response.reason} {initial_response.headers} {initial_response.text} {query_uri}")

	
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

				if pluralized_entity_name in response and response.status_code == 200:
					results = response.json()[pluralized_entity_name]
					current_page = pages.pop(0)

					if len(results) != 0:
						entries.extend(results)
						next_page = current_page + 1

						pages.append(next_page)	
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

	def _preprocess_entries(self, entity, entries):
		entity_method_map = {
			"TaxRate": self._preprocess_tax_rates,
		}
		preprocessor = entity_method_map.get(entity)
		if preprocessor:
			entries = preprocessor(entries)
		return entries
	
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

				#frappe.get_doc(account_dict).insert()
				self._log_error("Response", f"Response: account dict {account_dict}")
		except Exception as e:
			self._log_error(e, account)

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
				bank_account_dict = {
					"doctype": "Bank Account",
					"xero_id": account["AccountID"],
					"account_name": bank["name"],
					"account_type": account["BankAccountType"],
					"bank_account_no": account["BankAccountNumber"],
				}
				
				#frappe.get_doc(bank_account_dict).insert()

				self._log_error("Response", f"Response: bank account dict {bank_account_dict}")
				
		except Exception as e:
			self._log_error(e, account)
	
	def _create_bank(self, bank):
		try:
			if not frappe.db.exists(
				{"doctype": "Bank", "name": bank, "company": self.company}
			):
				bank_dict = {
					"doctype": "Bank",
					"bank_name": bank,	
				}
				#frappe.get_doc(bank_dict).insert()

				self._log_error("Response", f"Response: bank dict {bank_dict}")
		except Exception as e:
			self._log_error(e, bank)

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
				#frappe.get_doc(tax_rate_dict).insert()

				self._log_error("Response", f"Response: tax rate dict {tax_rate_dict}")

		except Exception as e:
			self._log_error(e, tax_rate)

	def _save_journal(self, journal):
		# Journal is equivalent to a Xero-added journal entry
		def _get_je_accounts(lines):
			# Converts JounalEntry lines to accounts list
			posting_type_field_mapping = {
				"Credit": "credit_in_account_currency",
				"Debit": "debit_in_account_currency",
			}

			accounts = []
			
			for line in lines:
				line_amount_abs_value = abs(line["LineAmount"])
				account_name = self._get_account_name_by_code(
					line["AccountCode"]
				)
				# In Xero, the use of (+) and (-) signs only signify the placement of the amount (debit or credit column)
				# In ERPNext, amount will be saved as absolute values

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

		xero_id = "Journal Entry - {}".format(journal["JournalID"])
		accounts = _get_je_accounts(journal["JournalLines"])
		posting_date = self.json_date_parser(journal["Date"])
		title = journal["Description"]
		self.__save_journal_entry(xero_id, accounts, title, posting_date)

	def __save_journal_entry(self, xero_id, accounts, title, posting_date):
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
					"accounts":  accounts,
					"title": title,
					}
				# je = frappe.get_doc(je_dict)
				# je.insert()
				# je.submit()

				self._log_error("Response", f"Response: journal entry dict {je_dict}")
		except Exception as e:
			self._log_error(e, [accounts, je_dict])

	def _publish(self, *args, **kwargs):
		frappe.publish_realtime("xero_progress_update", *args, **kwargs, user=self.modified_by)