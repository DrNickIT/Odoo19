# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import request
import logging

_logger = logging.getLogger(__name__)

class ConsignmentController(http.Controller):

    @http.route('/kleding-opsturen', type='http', auth='public', website=True)
    def consignment_form(self, **kw):
        ICP = request.env['ir.config_parameter'].sudo()
        # 1. CHECK STATUS
        is_closed = ICP.get_param('otters_consignment.is_closed')
        closed_message = ICP.get_param('otters_consignment.closed_message', 'Tijdelijk gesloten.')

        cash_perc_float = ICP.get_param('otters_consignment.cash_payout_percentage', '0.3')
        coupon_perc_float = ICP.get_param('otters_consignment.coupon_payout_percentage', '0.5')

        values = {
            'is_closed': is_closed,       # Geef door aan template
            'closed_message': closed_message, # Geef bericht door
            'cash_percentage': int(cash_perc_float * 100),
            'coupon_percentage': int(coupon_perc_float * 100),
            'partner': {},
        }

        if not request.env.user._is_public():
            partner = request.env.user.partner_id
            bank_acc = partner.bank_ids[:1].acc_number if partner.bank_ids else ''

            values.update({
                'default_name': partner.name,
                'default_email': partner.email,
                'default_street': partner.street,   # Bevat "Krokusstraat 16"
                'default_street2': partner.street2, # Bevat "Bus 2"
                'default_zip': partner.zip,
                'default_city': partner.city,
                'default_iban': bank_acc,
            })

        return request.render('otters_consignment.consignment_form_template', values)

    @http.route('/kleding-opsturen/bedankt', type='http', auth='public', website=True)
    def consignment_form_thankyou(self, **kw):
        return request.render('otters_consignment.consignment_thankyou_template', {})