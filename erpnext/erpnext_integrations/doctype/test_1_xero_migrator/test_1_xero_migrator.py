# # def _make_invoice_number_field(self, doctype):
# # 	if not frappe.get_meta(doctype).has_field("invoice_number"):
# # 		frappe.get_doc(
# # 			{
# # 				"doctype": "Custom Field",
# # 				"label": "Invoice Number",
# # 				"dt": doctype,
# # 				"fieldname": "invoice_number",
# # 				"fieldtype": "Data",
# # 			}
# # 		).insert()


# # # done

# # def _get_account_name_by_id(self, xero_id):
# # 	return frappe.get_all(
# # 		"Account", filters={"xero_id": xero_id, "company": self.company}
# # 	)[0]["name"]

# # def _get_account_name_by_code(self, account_code):
# # 	return frappe.get_all(
# # 		"Account", filters={"account_number": account_code, "company": self.company}
# # 	)[0]["name"]

# # def _save_tax_rate(self, tax_rate):
# # 	try:
# # 		if not frappe.db.exists(
# # 			{
# # 				"doctype": "Account",
# # 				"xero_id": "TaxRate - {}".format(tax_rate["TaxType"]),
# # 				"company": self.company,
# # 			}
# # 		):
# # 			frappe.get_doc(
# # 				{
# # 					"doctype": "Account",
# # 					"xero_id": "TaxRate - {}".format(tax_rate["TaxType"]),
# # 					"account_name": "{} - Xero".format(tax_rate["Name"]),
# # 					"root_type": "Liability",
# # 					"parent_account": encode_company_abbr("{} - Xero".format("Liability"), self.company),
# # 					"is_group": "0",
# # 					"company": self.company,
# # 				}
# # 			).insert()
# # 	except Exception as e:
# # 		self._log_error(e, tax_rate)

# # def _preprocess_tax_rates(self, tax_rates):
# # 	self.tax_rates = {tax_rate["Type"]: tax_rate for tax_rate in tax_rates}
# # 	return tax_rates

# # def _save_contact(self, contact):
# # 	try:
# # 		if contact["IsCustomer"]:
# # 			self._save_customer(contact)
# # 		elif contact["IsSupplier"]:
# # 			self._save_supplier(contact)
# # 	except Exception as e:
# # 		self._log_error(e, contact)

# # def _save_customer(self, contact):
# # 	try:
# # 		if not frappe.db.exists(
# # 			{"doctype": "Customer", "xero_id": contact["ContactID"], "company": self.company}
# # 		):
# # 			try:
# # 				receivable_account = frappe.get_all(
# # 					"Account",
# # 					filters={
# # 						"account_type": "Receivable",
# # 						"account_currency": contact["DefaultCurrency"],
# # 						"company": self.company,
# # 					},
# # 				)[0]["name"]
# # 			except Exception:
# # 				receivable_account = None
# # 			erpcustomer = frappe.get_doc(
# # 				{
# # 					"doctype": "Customer",
# # 					"xero_id": contact["ContactID"],
# # 					"customer_name": encode_company_abbr(contact["Name"], self.company),
# # 					"customer_type": "Individual",
# # 					"customer_group": "Commercial",
# # 					"default_currency": contact["DefaultCurrency"],
# # 					"accounts": [{"company": self.company, "account": receivable_account}],
# # 					"territory": "All Territories",
# # 					"company": self.company,
# # 				}
# # 			).insert()
# # 			self._create_address(erpcustomer, "Customer", contact["Addresses"])
# # 	except Exception as e:
# # 		self._log_error(e, contact)

# # def _save_supplier(self, contact):
# # 	try:
# # 		if not frappe.db.exists(
# # 			{"doctype": "Supplier", "xero_id": contact["ContactID"], "company": self.company}
# # 		):
# # 			erpsupplier = frappe.get_doc(
# # 				{
# # 					"doctype": "Supplier",
# # 					"xero_id": contact["ContactID"],
# # 					"supplier_name": encode_company_abbr(contact["Name"], self.company),
# # 					"supplier_group": "All Supplier Groups",
# # 					"company": self.company,
# # 				}
# # 			).insert()
# # 			self._create_address(erpsupplier, "Supplier", contact["Addresses"])
# # 	except Exception as e:
# # 		self._log_error(e, contact)

# # def _create_address(self, entity, doctype, addresses):
# # 	try:
# # 		for index, address in enumerate(addresses):
# # 			if not frappe.db.exists({"doctype": "Address", "xero_id": "{} Address{} - Xero".format(entity.name, index)}):
# # 				frappe.get_doc(
# # 					{
# # 						"doctype": "Address",
# # 						"xero_id": "{} Address{} - Xero".format(entity.name, index),
# # 						"address_title": entity.name,
# # 						"address_type": "Other",
# # 						"address_line1": address["AddressLine1"],
# # 						"pincode": address["PostalCode"],
# # 						"city": address["City"],
# # 						"links": [{"link_doctype": doctype, "link_name": entity.name}],
# # 					}
# # 				).insert()
# # 	except Exception as e:
# # 		self._log_error(e, address)

# # def _save_item(self, item):
# # 	try:
# # 		if not frappe.db.exists(
# # 			{"doctype": "Item", "xero_id": item["ItemID"], "company": self.company}
# # 		):
# # 			item_dict = {
# # 				"doctype": "Item",
# # 				"xero_id": item["ItemID"],
# # 				"item_code":encode_company_abbr(item["Code"], self.company),
# # 				"stock_uom": "Unit",
# # 				"is_stock_item": 0,
# # 				"item_name": encode_company_abbr(item["Name"], self.company),
# # 				"company": self.company,
# # 				"item_group": "All Item Groups",
# # 				"item_defaults": [{"company": self.company, "default_warehouse": self.default_warehouse}]
# # 			}
# # 			if "PurchaseDetails" in item:
# # 				if item["IsTrackedAsInventory"]:
# # 					account_code = item["PurchaseDetails"]["COGSAccountCode"]
# # 				else:
# # 					account_code = item["PurchaseDetails"]["AccountCode"]
# # 				expense_account = self._get_account_name_by_code(account_code)
# # 				item_dict["item_defaults"][0]["expense_account"] = expense_account
# # 			if "SalesDetails" in item:
# # 				income_account = self._get_account_name_by_code(item["SalesDetails"]["AccountCode"])
# # 				item_dict["item_defaults"][0]["income_account"] = income_account
# # 			frappe.get_doc(item_dict).insert()
# # 	except Exception as e:
# # 		self._log_error(e, item)

# # def _save_asset(self, asset):
# # 	try:
# # 		self._log_error("Saving asset", asset)
# # 		if not frappe.db.exists(
# # 			{"doctype": "Asset", "xero_id": asset["assetId"], "company": self.company}
# # 		):
# # 			depreciation_rate = asset["depreciationRate"]
# # 			purchase_price = asset["purchasePrice"]
# # 			total_number_of_depreciations = 1/depreciation_rate

# # 			depreciation_method_mapping = {
# # 				"NoDepreciation": "None",
# # 				"StraightLine": "Straight Line",
# # 				"DiminishingValue100": "Manual",
# # 				"DiminishingValue150": "Manual",
# # 				"DiminishingValue200": "Manual",
# # 				"FullDepreciation": "Full Depreciation"
# # 			}

# # 			finance_books = []
# # 			finance_books.append({
# # 				"total_number_of_depreciations": total_number_of_depreciations,
# # 				"frequency_of_depreciation": 12,
# # 				"depreciation_posting_date": asset["bookDepreciationDetail"]["depreciationStartDate"]
# # 			})


# # 			asset_dict = {
# # 				"doctype": "Asset",
# # 				"item": self._get_asset_item(asset),
# # 				"is_existing_asset": 1,
# # 				"available_for_use_date": asset["bookDepreciationDetail"]["depreciationStartDate"],
# # 				"gross_purchase_amount": purchase_price,
# # 				"location": self.company,
# # 				"purchase_date": asset["purchaseDate"],
# # 			}

# # 			if not depreciation_method_mapping["bookDepreciationSetting"]["depreciationMethod"] == "None":
# # 				if depreciation_method_mapping["bookDepreciationSetting"]["depreciationMethod"] == "Full Depreciation":
# # 					asset_dict["is_fully_depreciated"] = 1
# # 				else:
# # 					asset_dict["calculate_depreciation"] = 1
# # 					asset_dict["finance_books"] = finance_books
# # 			frappe.get_doc().insert(asset_dict)

# # 	except Exception as e:
# # 		self._log_error(e, asset)

# # def _get_asset_item(self, asset):
# # 	try:
# # 		if not frappe.db.exists(
# # 			{"doctype": "Item", "item_name": asset["assetName"], "company": self.company}
# # 		):
# # 			item_dict = {
# # 				"doctype": "Item",
# # 				"xero_id": asset["AssetID"],
# # 				"item_code": asset["assetNumber"],
# # 				"stock_uom": "Unit",
# # 				"is_stock_item": 0,
# # 				"item_name": asset["assetName"],
# # 				"company": self.company,
# # 				"item_group": "All Item Groups",
# # 				"item_defaults": [{"company": self.company, "default_warehouse": self.default_warehouse}]
# # 			}
# # 			asset = frappe.get_doc(item_dict).insert()

# # 			asset["item_name"]
# # 		else:
# # 			frappe.get_all("Item", filters={"item_name": asset["assetName"], "company": self.company})[0]["item_name"]
# # 	except Exception as e:
# # 		self._log_error(e, asset)

# # # def __get(self, *args, **kwargs):
# # # 	kwargs["headers"] = {
# # # 		"Accept": "application/json",
# # # 		"Authorization": "Bearer {}".format(self.access_token),
# # # 		"Xero-tenant-id": self.xero_tenant_id
# # # 	}
# # # 	response = requests.get(*args, **kwargs)
# # # 	# HTTP Status code 401 here means that the access_token is expired
# # # 	# We can refresh tokens and retry
# # # 	# However limitless recursion does look dangerous
# # # 	# if response.status_code == 401:
# # # 	# 	self._refresh_tokens()
# # # 	# 	response = self._get(*args, **kwargs)

# # # 	return response

# # def _get(self, *args, **kwargs):
# # 	try:
# # 		kwargs["headers"] = {
# # 			"Accept": "application/json",
# # 			"Authorization": "Bearer {}".format(self.access_token),
# # 			"Xero-tenant-id": self.xero_tenant_id
# # 		}

# # 		response = requests.get(*args, **kwargs)
# # 		# response = requests.get(*args, **kwargs)
# # 		# HTTP Status code 401 here means that the access_token is expired
# # 		# We can refresh tokens and retry
# # 		# However limitless recursion does look dangerous
# # 		if response.status_code == 401:
# # 			self._refresh_tokens()
# # 			response = self._get(*args, **kwargs)

# # 		return response
# # 	except requests.exceptions.HTTPError as err:
# # 		print(f"HTTP Error: {err}")
# # 	except requests.exceptions.RequestException as err:
# # 		print(f"An error occurred: {err}")
# # 	except Exception as err:
# # 		print(f"Unexpected error: {err}")

# # def _get_unique_account_name(self, xero_name, number=0):
# # 	if number:
# # 		xero_account_name = "{} - {} - Xero".format(xero_name, number)
# # 	else:
# # 		xero_account_name = "{} - Xero".format(xero_name)
# # 	company_encoded_account_name = encode_company_abbr(xero_account_name, self.company)
# # 	if frappe.db.exists(
# # 		{"doctype": "Account", "name": company_encoded_account_name, "company": self.company}
# # 	):
# # 		unique_account_name = self._get_unique_account_name(xero_name, number + 1)
# # 	else:
# # 		unique_account_name = xero_account_name
# # 	return unique_account_name

# # def _log_error(self, execption, data=""):
# # 	frappe.log_error(
# # 		title="Xero Migration Error",
# # 		message="\n".join(
# # 			[
# # 				"Data",
# # 				json.dumps(data, sort_keys=True, indent=4, separators=(",", ": ")),
# # 				"Exception",
# # 				traceback.format_exc(),
# # 			]
# # 		),
# # 	)

# # def set_indicator(self, status):
# # 	self.status = status
# # 	self.save()
# # 	frappe.db.commit()

# # def _get_bank_transaction_line_items(self, bank_transaction_line_items):
# # 	for line_item in bank_transaction_line_items:
# # 		frappe.get_doc(
# # 			{
# # 				"doctype": "Payment Entry",
# # 				"xero_id": line_item["LineItemID"],
# # 				"payment_name": line_item["Description"],

# # 			}
# # 		).insert()

# # def process_bank_transaction(self, bank_transaction):
# # 	# check bank_account_transaction.py: do we need to clear the payment_entries when thes
# # 	# transaction has been reconciled?
# # 	status_mapping = {
# # 		"PAID": "Settled",
# # 		"DELETED": "Cancelled"
# # 	}

# # 	if bank_transaction["IsReconciled"] == "true":
# # 		status_mapping[bank_transaction["Status"]] = "Reconciled"
# # 	else:
# # 		status_mapping[bank_transaction["Status"]] = "Unreconciled"

# # 	bank_account_details = frappe.get_list(
# # 		"Account",
# # 		filters={"bank_account_number": bank_transaction["BankAccount"]["Name"],
# # 		},
# # 	)

# # 	# skip Deposit and Withdrawal
# # 	bank_transaction_dict = {
# # 		"doctype": "Bank Transaction",
# # 		"xero_id": bank_transaction["BankTransactionID"],
# # 		"transaction_id": bank_transaction["BankTransactionID"],
# # 		"transaction_type": bank_transaction["Type"],
# # 		"company": self.company,
# # 		"date": bank_transaction["DateString"],
# # 		"status": status_mapping[bank_transaction["Status"]],
# # 		"bank_account": bank_transaction["BankAccount"]["Name"],
# # 		"bank_party_account_number": self._get_bank_account_number(bank_account_details),
# # 		"currency": bank_transaction["CurrencyCode"],
# # 		"reference_number": bank_transaction["Reference"],
# # 		"payment_entries": self._get_bank_transaction_line_items(bank_transaction["LineItems"]),
# # 		"allocated_amount": bank_transaction["Total"],
# # 	}

# # 	frappe.get_doc(
# # 		bank_transaction_dict
# # 	).insert()

# # # Retrieve sales invoices or purchase bills
# # # Saving an Invoice as Sales or Purchase automatically designates the amounts to the correct column
# # def _save_invoice(self, invoice):
# # 	invoice_type = invoice["Type"]

# # 	# A bill – commonly known as an Accounts Payable or supplier invoice
# # 	if invoice_type == "ACCPAY":
# # 		xero_id = "Purchase Invoice - {}".format(invoice["InvoiceID"])
# # 		self._save_purchase_invoice(invoice, xero_id)

# # 	# A sales invoice – commonly known as an Accounts Receivable or customer invoice
# # 	elif invoice_type == "ACCREC":
# # 		xero_id = "Sales Invoice - {}".format(invoice["InvoiceID"])
# # 		self._save_sales_invoice(invoice, xero_id)

# # # is_pos=True signifies Sales Receipt, POS Sales Invoice
# # # setting is_pos to True adds Payments section
# # def _save_sales_invoice(self, invoice, xero_id, is_return=False):
# # 	try:
# # 		if len(invoice["Payments"]) != 0:
# # 			is_pos = True
# # 		else:
# # 			is_pos = False

# # 		items = []
# # 		payments = []
# # 		taxes = []

# # 		invoice_number = invoice["InvoiceNumber"]
# # 		if not frappe.db.exists(
# # 			{"doctype": "Sales Invoice", "xero_id": xero_id, "company": self.company}
# # 		):
# # 			invoice_dict = {
# # 				"doctype": "Sales Invoice",
# # 				"xero_id": xero_id,
# # 				"invoice_number": invoice_number,
# # 				"currency": invoice["CurrencyCode"],
# # 				"conversion_rate": invoice["CurrencyRate"],
# # 				"posting_date": self.get_date_object(invoice["DateString"]),
# # 				"due_date": self.get_date_object(invoice["DueDateString"]),
# # 				"customer": frappe.get_all(
# # 					"Customer",
# # 					filters={
# # 						"xero_id": invoice["Contact"]["ContactID"],
# # 						"company": self.company,
# # 					},
# # 				)[0]["name"],
# # 				"is_return": is_return,
# # 				"is_pos": is_pos,
# # 				"set_posting_time": "1",
# # 				"disable_rounded_total": 1,
# # 				"company": self.company,
# # 				"items": items,
# # 				"taxes": taxes,
# # 				"payments": payments
# # 			}

# # 			for line_item in invoice["LineItems"]:
# # 				item = self._get_si_item(line_item)
# # 				items.append(item)

# # 				if invoice["LineAmountTypes"] == "Inclusive":
# # 					tax = self._get_tax(line_item)
# # 					taxes.append(tax)

# # 			if "Payments" in invoice and len(invoice["Payments"]) != 0:
# # 				for payment in invoice["Payments"]:
# # 					payment = self._get_sales_invoice_payment(invoice["LineItems"][0], is_return=is_return, is_pos=True)
# # 					payments.append(payment)

# # 			if "TotalTax" in invoice:
# # 				invoice_dict["total_taxes_and_charges"]: invoice["TotalTax"]

# # 			invoice_doc = frappe.get_doc(invoice_dict)
# # 			invoice_doc.insert()
# # 			invoice_doc.submit()
# # 	except Exception as e:
# # 		self._log_error(e, invoice)

# # def _get_si_item(self, line_item, is_return=False):
# # 	item = frappe.db.get_all(
# # 		"Item",
# # 		filters={
# # 			"xero_id": line_item["Item"]["ItemID"],
# # 			"company": self.company,
# # 		},
# # 		fields=["name", "code"],
# # 	)[0]
# # 	item = {
# # 				"item_name": item["name"],
# # 				"item_code": item["code"],
# # 				"conversion_factor": 1,
# # 				"description": line_item["Description"],
# # 				"qty": line_item["Quantity"],
# # 				"price_list_rate": line_item["UnitAmount"],
# # 				"cost_center": self.default_cost_center,
# # 				"warehouse": self.default_warehouse,
# # 				"item_tax_rate": json.dumps(self._get_item_taxes(line_item["TaxType"], line_item["TaxAmount"])),
# # 				"income_account": self._get_account_name_by_id(line_item["AccountId"])
# # 			}
# # 	if is_return:
# # 		item["qty"] *= -1
# # 	return item

# # def _get_pi_items(self, invoice, is_return=False):
# # 	items = []
# # 	for line_item in invoice["LineItems"]:
# # 		item = frappe.db.get_all(
# # 			"Item",
# # 			filters={
# # 				"xero_id": line_item["Item"]["ItemID"],
# # 				"company": self.company,
# # 			},
# # 			fields=["name", "code"],
# # 		)[0]
# # 		items.append(
# # 			{
# # 				"item_name": item["name"],
# # 				"item_code": item["code"],
# # 				"conversion_factor": 1,
# # 				"description": line_item["Description"],
# # 				"qty": line_item["Quantity"],
# # 				"price_list_rate": line_item["UnitAmount"],
# # 				"cost_center": self.default_cost_center,
# # 				"warehouse": self.default_warehouse,
# # 				"item_tax_rate": json.dumps(self._get_item_taxes(line_item["TaxType"], line_item["TaxAmount"])),
# # 				"expense_account": self._get_account_name_by_id(line_item["AccountId"])
# # 			}
# # 		)
# # 	if is_return:
# # 		items[-1]["qty"] *= -1

# # 	return items

# # def _save_purchase_invoice(self, invoice, xero_id, is_return=False):
# # 	try:
# # 		if len(invoice["Payments"]) != 0:
# # 			is_paid = True
# # 		else:
# # 			is_paid = False

# # 		items = []
# # 		payments = []
# # 		taxes = []

# # 		invoice_number = invoice["InvoiceNumber"]
# # 		if not frappe.db.exists(
# # 			{"doctype": "Purchase Invoice", "xero_id": xero_id, "company": self.company}
# # 		):
# # 			invoice_dict = {
# # 				"doctype": "Purchase Invoice",
# # 				"xero_id": xero_id,
# # 				"invoice_number": invoice_number,
# # 				"currency": invoice["CurrencyCode"],
# # 				"conversion_rate": invoice["CurrencyRate"],
# # 				"posting_date": self.get_date_object(invoice["DateString"]),
# # 				"due_date": self.get_date_object(invoice["DueDateString"]),
# # 				"customer": frappe.get_all(
# # 					"Supplier",
# # 					filters={
# # 						"xero_id": invoice["Contact"]["ContactID"],
# # 						"company": self.company,
# # 					},
# # 				)[0]["name"],
# # 				"is_pos": is_paid,
# # 				"is_return": is_return,
# # 				"set_posting_time": "1",
# # 				"disable_rounded_total": 1,
# # 				"company": self.company,
# # 				"items": items,
# # 				"taxes": taxes,
# # 				"payments": payments
# # 			}

# # 			for line_item in invoice["LineItems"]:
# # 				item = self._get_pi_item(line_item)
# # 				items.append(item)

# # 				if invoice["LineAmountTypes"] == "Inclusive":
# # 					tax = self._get_tax(line_item)
# # 					taxes.append(tax)

# # 			if "Payments" in invoice and len(invoice["Payments"]) != 0:
# # 				for payment in invoice["Payments"]:
# # 					payment = self._get_purchase_invoice_payment(invoice["LineItems"][0], is_return=is_return, is_pos=True)
# # 					payments.append(payment)

# # 			if "TotalTax" in invoice:
# # 				invoice_dict["total_taxes_and_charges"]: invoice["TotalTax"]

# # 			invoice_doc = frappe.get_doc(invoice_dict)
# # 			invoice_doc.insert()
# # 			invoice_doc.submit()
# # 	except Exception as e:
# # 		self._log_error(e, invoice)

# # def _get_item_taxes(self, tax_type, tax_amount):
# # 	item_taxes = {}
# # 	if tax_type != "NONE":
# # 		tax_head = self._get_account_name_by_id("TaxRate - {}".format(tax_type))
# # 		tax_rate = tax_amount
# # 		item_taxes[tax_head] = tax_rate["RateValue"]
# # 	return item_taxes

# # def _get_tax(self, line_item):
# # 	account_head = self._get_account_name_by_id("TaxRate - {}".format(line_item["TaxType"]))
# # 	tax ={
# # 			"charge_type": "Actual",
# # 			"account_head": account_head,
# # 			"description": account_head,
# # 			"cost_center": self.default_cost_center,
# # 			"amount": line_item["TaxAmount"],
# # 		}
# # 	return tax

# # def _get_sales_invoice_payment(self, line_item, is_return=False, is_pos=False):
# # 	# to get payments first
# # 	if is_pos:
# # 		amount = line_item["LineAmount"]
# # 		if is_return:
# # 			amount = -amount
# # 		return [
# # 			{
# # 				"mode_of_payment": "Cash",
# # 				"account": self._get_account_name_by_id(line_item["AccountId"]),
# # 				"amount": amount,
# # 			}
# # 		]

# # def _get_purchase_invoice_payment(self, line_item, is_return=False, is_paid=False):
# # 	if is_paid:
# # 		amount = line_item["LineAmount"]
# # 		if is_return:
# # 			amount = -amount
# # 		return [
# # 			{
# # 				"mode_of_payment": "Cash",
# # 				"account": self._get_account_name_by_id(line_item["AccountId"]),
# # 				"amount": amount,
# # 			}
# # 		]

# # def _save_journal(self, journal):
# # 	# Journal is equivalent to a Xero-added journal entry
# # 	def _get_je_accounts(lines):
# # 		# Converts JounalEntry lines to accounts list
# # 		posting_type_field_mapping = {
# # 			"Credit": "credit_in_account_currency",
# # 			"Debit": "debit_in_account_currency",
# # 		}

# # 		accounts = []

# # 		for line in lines:
# # 			line_amount_abs_value = abs(line["LineAmount"])
# # 			account_name = self._get_account_name_by_code(
# # 				line["AccountCode"]
# # 			)
# # 			# In Xero, the use of (+) and (-) signs only signify the placement of the amount (debit or credit column)
# # 			# In ERPNext, amount will be saved as absolute values

# # 			if line["LineAmount"] > 0:
# # 				posting_type = "Debit"
# # 			elif line["LineAmount"] < 0:
# # 				posting_type = "Credit"

# # 			accounts.append(
# # 				{
# # 					"account": account_name,
# # 					posting_type_field_mapping[posting_type]: line_amount_abs_value,
# # 					"cost_center": self.default_cost_center,
# # 				}
# # 			)
# # 		return accounts

# # 	xero_id = "Journal Entry - {}".format(journal["JournalID"])
# # 	accounts = _get_je_accounts(journal["JournalLines"])
# # 	posting_date = self.json_date_parser(journal["Date"])
# # 	title = journal["Description"]
# # 	self.__save_journal_entry(xero_id, accounts, title, posting_date)

# # def __save_journal_entry(self, xero_id, accounts, title, posting_date):
# # 	try:
# # 		if not frappe.db.exists(
# # 			{"doctype": "Journal Entry", "xero_id": xero_id, "company": self.company}
# # 		):
# # 			je = frappe.get_doc(
# # 				{
# # 					"doctype": "Journal Entry",
# # 					"xero_id": xero_id,
# # 					"company": self.company,
# # 					"posting_date": posting_date,
# # 					"accounts": accounts,
# # 					"multi_currency": 1,
# # 					"accounts":  accounts,
# # 					"title": title,
# # 				}
# # 			)
# # 			je.insert()
# # 			je.submit()
# # 	except Exception as e:
# # 		self._log_error(e, [accounts, json.loads(je.as_json())])

# # def _save_bank_transaction(self, bank_transaction):
# # 	try:
# # 		if bank_transaction["IsReconciled"] == "true" and bank_transaction["Status"] == "Authorised":
# # 			status = "Reconciled"
# # 		elif bank_transaction["IsReconciled"] == "false" and bank_transaction["Status"] == "Authorised":
# # 			status = "Unreconciled"
# # 		elif bank_transaction["Status"] == "Cancelled":
# # 			status = "Cancelled"

# # 		field_for_transaction_amount_mapping = {
# # 			"RECEIVE": "Deposit",
# # 			"SPEND": "Withdrawal"
# # 		}

# # 		if bank_transaction["Type"].find('RECEIVE') != -1:
# # 			field_type = field_for_transaction_amount_mapping["RECEIVE"]
# # 		else:
# # 			field_type = field_for_transaction_amount_mapping["DEPOSIT"]

# # 		xero_id = "Bank Transaction - {}".format(bank_transaction["BankTransactionID"])

# # 		if not frappe.db.exists(
# # 			{"doctype": "Bank Transaction", "xero_id": bank_transaction["BankTransactionID"], "company": self.company}
# # 		):
# # 			bank_transaction_dict = {
# # 				"doctype": "Bank Transaction",
# # 				"xero_id": xero_id,
# # 				"status": status,
# # 				"transaction_id": bank_transaction["BankTransactionID"],
# # 				"transaction_type": bank_transaction["Type"],
# # 				field_type: bank_transaction["Total"],
# # 				"company": self.company,
# # 				"date": bank_transaction["DateString"],
# # 				"bank_account": bank_transaction["BankAccount"]["Name"],
# # 				"currency": bank_transaction["CurrencyCode"],
# # 				"allocated_amount": bank_transaction["Total"],
# # 			}

# # 			if "Reference" in bank_transaction:
# # 				bank_transaction_dict["reference_number"] = bank_transaction["Reference"]

# # 			frappe.get_doc(bank_transaction_dict).insert()

# # 	except Exception as e:
# # 		self._log_error(e, bank_transaction)

# # # Xero: Payment vs Prepayment
# # # Payment: after the invoice has been issued (https://central.xero.com/s/article/Record-payment-of-a-sales-invoice)
# # # Prepayment: before invoice has been issued (https://central.xero.com/s/article/Record-a-prepayment)
# # def _save_payment(self, payment):
# # 	try:
# # 		invoice_id = payment["Invoice"]["InvoiceID"]

# # 		payment_type_mapping = {
# # 			"ACCRECPAYMENT": "Receive",
# # 			"ACCRECPAYMENT": "Pay",
# # 			"ARCREDITPAYMENT": "Pay",
# # 			"APCREDITPAYMENT": "Receive Refund",
# # 			"AROVERPAYMENTPAYMENT": "Pay Refund",
# # 			"ARPREPAYMENTPAYMENT": "Pay Refund",
# # 			"APPREPAYMENTPAYMENT": "Receive Refund",
# # 			"APOVERPAYMENTPAYMENT": "Receive Refund"
# # 		}
# # 		payment_type = payment_type_mapping[payment["PaymentType"]]
# # 		if payment_type == "Receive":
# # 			self._save_sales_invoice_payment(payment_type, invoice_id, payment)
# # 		elif payment_type == "Pay":
# # 			self._save_purchase_invoice_payment(payment_type, invoice_id, payment)
# # 	except Exception as e:
# # 		self._log_error(e, payment)

# # def _save_sales_invoice_payment(self, invoice_id, payment):
# # 	if frappe.db.exists(
# # 		{"doctype": "Sales Invoice", "xero_id": invoice_id, "company": self.company}
# # 	):
# # 		invoice = frappe.get_all(
# # 			"Sales Invoice",
# # 			filters={
# # 				"xero_id": invoice_id,
# # 				"company": self.company,
# # 			},
# # 			fields=["name", "customer", "debit_to"],
# # 		)[0]
# # 		xero_id = "Sales Receipt - {}".format(payment["PaymentId"])
# # 		self.__save_sales_invoice_payment(invoice, payment, xero_id)

# # # Also Sales Receipt
# # def __save_sales_invoice_payment(self, invoice, payment, xero_id, is_pos=True, is_return=False):
# # 	try:
# # 		invoice_number = payment["Invoice"]["InvoiceNumber"]
# # 		if not frappe.db.exists(
# # 			{"doctype": "Sales Invoice", "xero_id": xero_id, "company": self.company}
# # 		):
# # 			line_item = {
# # 				"LineAmount": payment["Amount"],
# # 				"AccountId": payment["Account"]["AccountID"]
# # 			}

# # 			invoice_dict = {
# # 				"doctype": "Sales Invoice",
# # 				"xero_id": xero_id,
# # 				"invoice_number": invoice_number,
# # 				"currency": invoice["currency"],
# # 				"conversion_rate": invoice["conversion_rate"],
# # 				"posting_date": self.get_date_object(invoice["DateString"]),
# # 				"due_date": self.get_date_object(invoice["DueDateString"]),
# # 				"customer": frappe.get_all(
# # 					"Customer",
# # 					filters={
# # 						"xero_id": invoice["Contact"]["ContactID"],
# # 						"company": self.company,
# # 					},
# # 				)[0]["name"],
# # 				"is_return": is_return,
# # 				"is_pos": is_pos,
# # 				"set_posting_time": "1",
# # 				"disable_rounded_total": 1,
# # 				"company": self.company,
# # 				"items": invoice["items"],
# # 				"taxes": invoice["taxes"],
# # 				"payments": self._get_sales_invoice_payment(line_item, is_return=is_return, is_pos=True)
# # 			}

# # 			invoice_doc = frappe.get_doc(invoice_dict)
# # 			invoice_doc.insert()
# # 			invoice_doc.submit()

# # 	except Exception as e:
# # 		self._log_error(e, payment)

# # def _save_purchase_invoice_payment(self, invoice_id, payment):
# # 	if frappe.db.exists(
# # 		{"doctype": "Purchase Invoice", "xero_id": invoice_id, "company": self.company}
# # 	):
# # 		invoice = frappe.get_all(
# # 			"Purchase Invoice",
# # 			filters={
# # 				"xero_id": invoice_id,
# # 				"company": self.company,
# # 			},
# # 			fields=["name", "customer", "credit_to"],
# # 		)[0]
# # 		xero_id = "Purchase Receipt - {}".format(payment["PaymentId"])
# # 		self.__save_purchase_invoice_payment(invoice, payment, xero_id)

# # def __save_purchase_invoice_payment(self, invoice, payment, xero_id, is_paid=True, is_return=False):
# # 	try:
# # 		invoice_number = payment["Invoice"]["InvoiceNumber"]
# # 		if not frappe.db.exists(
# # 			{"doctype": "Purchase Invoice", "xero_id": xero_id, "company": self.company}
# # 		):
# # 			line_item = {
# # 				"LineAmount": payment["Amount"],
# # 				"AccountId": payment["Account"]["AccountID"]
# # 			}

# # 			invoice_dict = {
# # 				"doctype": "Purchase Invoice",
# # 				"xero_id": xero_id,
# # 				"invoice_number": invoice_number,
# # 				"currency": invoice["currency"],
# # 				"conversion_rate": invoice["conversion_rate"],
# # 				"posting_date": self.get_date_object(invoice["DateString"]),
# # 				"due_date": self.get_date_object(invoice["DueDateString"]),
# # 				"customer": frappe.get_all(
# # 					"Customer",
# # 					filters={
# # 						"xero_id": invoice["Contact"]["ContactID"],
# # 						"company": self.company,
# # 					},
# # 				)[0]["name"],
# # 				"is_return": is_return,
# # 				"is_paid": is_paid,
# # 				"set_posting_time": "1",
# # 				"disable_rounded_total": 1,
# # 				"company": self.company,
# # 				"items": invoice["items"],
# # 				"taxes": invoice["taxes"],
# # 				"payments": self._get_purchase_invoice_payment(line_item, is_return=is_return, is_paid=True)
# # 			}

# # 			invoice_doc = frappe.get_doc(invoice_dict)
# # 			invoice_doc.insert()
# # 			invoice_doc.submit()

# # 	except Exception as e:
# # 		self._log_error(e, payment)

# # def _save_credit_note(self, credit_note):
# # 	xero_id = "Credit Note - {}".format(credit_note["CreditNoteID"])

# # 	if credit_note["Type"] == "ACCRECCREDIT":
# # 		self._save_sales_invoice_credit_note(xero_id, credit_note)
# # 	elif credit_note["Type"] == "ACCPAYCREDIT":
# # 		self._save_purchase_invoice_credit_note(xero_id, credit_note)

# # def _save_sales_invoice_credit_note(self, xero_id, credit_note, is_return=True):
# # 	try:
# # 		if credit_note["Status"] == "PAID":
# # 			is_pos=True
# # 		else:
# # 			is_pos=False

# # 		payments = []

# # 		for allocation in credit_note["Allocations"]:
# # 			sales_invoice = frappe.get_all(
# # 				"Sales Invoice",
# # 				filters={
# # 					"xero_id": allocation["Invoice"]["InvoiceNumber"],
# # 					"company": self.company,
# # 				},
# # 			)[0],
# # 			if not frappe.db.exists(
# # 				{"doctype": "Sales Invoice", "xero_id": xero_id, "company": self.company}
# # 			):
# # 				invoice_dict = {
# # 					"doctype": "Sales Invoice",
# # 					"xero_id": xero_id,
# # 					"is_return": is_return,
# # 					"is_pos": is_pos,
# # 					"return_against": sales_invoice["name"]
# # 				}

# # 				if credit_note["Status"] == "PAID":
# # 					payment = {
# # 						"mode_of_payment": "Cash",
# # 						"amount": allocation["Amount"]
# # 					}
# # 					payments.append(payment)

# # 				if len(payments) != 0:
# # 					invoice_dict["payments"] = payments

# # 				invoice_doc = frappe.get_doc(invoice_dict)
# # 				invoice_doc.insert()
# # 				invoice_doc.submit()
# # 	except Exception as e:
# # 		self._log_error(e, credit_note)

# # def _save_purchase_invoice_credit_note(self, xero_id, credit_note, is_return=True):
# # 	try:
# # 		if credit_note["Status"] == "PAID":
# # 			is_paid=True
# # 		else:
# # 			is_paid=False

# # 		payments = []

# # 		for allocation in credit_note["Allocations"]:
# # 			purchase_invoice = frappe.get_all(
# # 				"Purchase Invoice",
# # 				filters={
# # 					"xero_id": allocation["CustomerRef"]["InvoiceID"],
# # 					"company": self.company,
# # 				},
# # 			)[0],
# # 		if not frappe.db.exists(
# # 			{"doctype": "Purchase Invoice", "xero_id": xero_id, "company": self.company}
# # 		):
# # 			invoice_dict = {
# # 				"doctype": "Purchase Invoice",
# # 				"xero_id": xero_id,
# # 				"is_return": is_return,
# # 				"is_paid": is_paid,
# # 				"return_against": purchase_invoice["name"]
# # 			}

# # 			if credit_note["Status"] == "PAID":
# # 				payment = {
# # 					"mode_of_payment": "Cash",
# # 					"amount": allocation["Amount"]
# # 				}
# # 				payments.append(payment)

# # 			if len(payments) != 0:
# # 				invoice_dict["payments"] = payments

# # 			invoice_doc = frappe.get_doc(invoice_dict)
# # 			invoice_doc.insert()
# # 			invoice_doc.submit()
# # 	except Exception as e:
# # 		self._log_error(e, credit_note)

# # def _create_bank_account(self, account):
# # 	try:

# # 		if frappe.db.exists(
# # 			{"doctype": "Bank", "xero_id":  account["AccountID"], "company": self.company}
# # 		):
# # 			bank = frappe.get_all(
# # 				"Bank",
# # 				filters={
# # 					"name": account["Name"],
# # 					"company": self.company,
# # 				},
# # 				fields=["name", "customer", "debit_to"],
# # 			)[0]
# # 		else:
# # 			bank = self._create_bank(account["Name"])

# # 		if not frappe.db.exists(
# # 			{"doctype": "Bank Account", "xero_id": account["AccountID"], "company": self.company}
# # 		):
# # 			frappe.get_doc({
# # 				"doctype": "Bank Account",
# # 				"xero_id": account["AccountID"],
# 				"account_name": bank["name"],
# 				"account_type": account["BankAccountType"],
# 				"bank_account_no": account["BankAccountNumber"],
# 			}).insert()

# 	except Exception as e:
# 		self._log_error(e, account)

# def _create_bank(self, bank):
# 	try:
# 		if not frappe.db.exists(
# 			{"doctype": "Bank", "name": bank, "company": self.company}
# 		):
# 			frappe.get_doc({
# 				"doctype": "Bank",
# 				"bank_name": bank,
# 			}).insert()
# 	except Exception as e:
# 		self._log_error(e, bank)

# def get_date_from_timestamp(self, timestamp_string):
# 	timestamp = int(timestamp_string.split('(')[1].split('+')[0])
# 	date_object = datetime.utcfromtimestamp(timestamp / 1000.0)

# 	date_object.date().strftime("%m-%d-%Y")

# def get_date_object(self, date_time_string):
# 	date_time_object = self.date_and_time_parser(self, date_time_string)
# 	extracted_date = date_time_object.date()

# 	extracted_date.strftime("%m-%d-%Y")

# def get_time_object(self, date_time_string):
# 	date_time_object = date_time_string.date()
# 	date_time_object.time()

# def date_and_time_parser(self, date_time_string):
# 	date_time_string = "2009-05-27 00:00:00"

# 	try:
# 		datetime.strptime(date_time_string, "%Y-%m-%dT%H:%M:%S")

# 	except ValueError:
# 		# If parsing fails, the string does not match the specified format
# 		pass
