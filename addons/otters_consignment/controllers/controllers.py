# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import request
import logging

_logger = logging.getLogger(__name__)

class ConsignmentController(http.Controller):

    @http.route('/kleding-opsturen', type='http', auth='public', website=True)
    def consignment_form(self, **kw):
        # 1. Standaard percentages ophalen (had je al)
        ICP = request.env['ir.config_parameter'].sudo()
        cash_perc_float = float(ICP.get_param('otters_consignment.cash_payout_percentage', '0.3'))
        coupon_perc_float = float(ICP.get_param('otters_consignment.coupon_payout_percentage', '0.5'))

        # 2. Start met lege waarden
        values = {
            'cash_percentage': cash_perc_float * 100,
            'coupon_percentage': coupon_perc_float * 100,
            'partner': {}, # Leeg object als fallback
        }

        # 3. Check of gebruiker is ingelogd (niet 'Public User')
        if not request.env.user._is_public():
            partner = request.env.user.partner_id

            # We zoeken ook alvast of er een bankrekening bekend is
            bank_acc = partner.bank_ids[:1].acc_number if partner.bank_ids else ''

            values.update({
                'default_name': partner.name,
                'default_email': partner.email,
                'default_street': partner.street,
                'default_street2': partner.street2, # Vaak gebruikt voor huisnummer/bus
                'default_zip': partner.zip,
                'default_city': partner.city,
                'default_iban': bank_acc,
            })

        return request.render('otters_consignment.consignment_form_template', values)

    @http.route('/kleding-opsturen/bedankt', type='http', auth='public', website=True)
    def consignment_form_thankyou(self, **kw):
        return request.render('otters_consignment.consignment_thankyou_template', {})