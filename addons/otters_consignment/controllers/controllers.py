# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import request
import requests
import base64
import json
import logging
import re  # Importeren van regular expressions

_logger = logging.getLogger(__name__)

class ConsignmentController(http.Controller):

    @http.route('/kleding-opsturen', type='http', auth='public', website=True)
    def consignment_form(self, **kw):
        ICP = request.env['ir.config_parameter'].sudo()
        cash_perc_float = float(ICP.get_param('otters_consignment.cash_payout_percentage', '0.3'))
        coupon_perc_float = float(ICP.get_param('otters_consignment.coupon_payout_percentage', '0.5'))
        render_values = {
            'cash_percentage': cash_perc_float * 100,
            'coupon_percentage': coupon_perc_float * 100,
        }
        return request.render('otters_consignment.consignment_form_template', render_values)

    @http.route('/kleding-opsturen/bedankt', type='http', auth='public', website=True)
    def consignment_form_thankyou(self, **kw):
        return request.render('otters_consignment.consignment_thankyou_template', {})
