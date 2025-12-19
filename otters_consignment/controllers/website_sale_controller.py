# -*- coding: utf-8 -*-
import logging
from odoo.addons.website_sale.controllers.main import WebsiteSale
from odoo.http import request

# Maak een logger aan
_logger = logging.getLogger(__name__)
class OttersWebsiteSale(WebsiteSale):

    def _get_mandatory_billing_address_fields(self, country_sudo):
        mandatory_fields = super(OttersWebsiteSale, self)._get_mandatory_billing_address_fields(country_sudo)

        if 'phone' in mandatory_fields:
            mandatory_fields.remove('phone')

        return mandatory_fields

    def _get_mandatory_delivery_address_fields(self, country_sudo):
        mandatory_fields = super(OttersWebsiteSale, self)._get_mandatory_delivery_address_fields(country_sudo)

        if 'phone' in mandatory_fields:
            mandatory_fields.remove('phone')

        return mandatory_fields