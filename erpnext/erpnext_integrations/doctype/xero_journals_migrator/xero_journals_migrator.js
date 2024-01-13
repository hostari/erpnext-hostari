// Copyright (c) 2024, Frappe Technologies Pvt. Ltd. and contributors
// For license information, please see license.txt

frappe.ui.form.on("Xero Journals Migrator", {
    connect: function(frm) {
		// OAuth requires user intervention to provide application access permissionsto requested scope
		// Here we open a new window and redirect user to the authorization url.
		// After user grants us permission to access. We will set authorization details on this doc which will force refresh.
		window.open(frm.doc.authorization_url)
	},
    fetch_data: function(frm) {
		response = frm.call("migrate")
        console.log(response)
	},
    onload: function(frm) {
        frm.trigger("set_indicator")
		var domain = frappe.urllib.get_base_url()
        var redirect_url = `${domain}/api/method/erpnext.erpnext_integrations.doctype.xero_journals_migrator.xero_journals_migrator.callback`
        if (frm.doc.redirect_url != redirect_url) {
			frm.set_value("redirect_url", redirect_url)
		}
        // Instead of changing percentage width and message of single progress bar
		// Show a different porgress bar for every action after some time remove the finished progress bar
 		// Former approach causes the progress bar to dance back and forth.
		frm.trigger("set_indicator")
        frappe.realtime.on("xero_progress_update", function (data) {
           frm.dashboard.show_progress(data.message, (data.count / data.total) * 100, data.message)
           if (data.count == data.total) {
               window.setTimeout( function(message) {frm.dashboard.hide_progress(message)}, 1500, data.messsage)
           }
       })
    },
    refresh: function(frm) {
		frm.trigger("set_indicator")
		if (!frm.doc.access_token) {
			// Unset access_token signifies that we don't have enough information to connect to Xero API and fetch data
			if (frm.doc.authorization_url) {
				frm.add_custom_button(__("Connect to Xero"), function () {
					frm.trigger("connect")
				});
			}
		}
		if (frm.doc.access_token) {
			// If we have access_token that means we also have refresh_token we don't need user intervention anymore
			// All we need now is a Company from erpnext
			frm.remove_custom_button(__("Connect to Xero"))

			frm.toggle_display("company_settings", 1)
			frm.set_df_property("company", "reqd", 1)
			if (frm.doc.company) {
					frm.add_custom_button(__("Fetch Data"), function () {
					frm.trigger("fetch_data")
				});
			}
		}
	},
    set_indicator: function(frm) {
		var indicator_map = {
			"Connecting to Xero": [__("Connecting to Xero"), "orange"],
			"Connected to Xero": [__("Connected to Xero"), "green"],
			"In Progress": [__("In Progress"), "orange"],
			"Complete": [__("Complete"), "green"],
			"Failed": [__("Failed"), "red"],
		}
		if (frm.doc.status) {
			var indicator = indicator_map[frm.doc.status]
			var label = indicator[0]
			var color = indicator[1]
			frm.page.set_indicator(label, color)
		}
	},
});