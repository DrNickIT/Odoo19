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

        # 2. VEILIGE FUNCTIE OM PERCENTAGES OP TE HALEN
        def get_safe_percentage(key, default_val):
            val_str = ICP.get_param(key)

            # Als er niets in de database staat, gebruik default
            if not val_str:
                return int(default_val * 100)

            try:
                # Stap A: Maak de string schoon (vervang komma door punt)
                clean_val = str(val_str).replace(',', '.')

                # Stap B: Fix voor corrupte data (zoals '0.30.30.30')
                # Als er meer dan 1 punt in staat, pakken we alles tot de tweede punt
                if clean_val.count('.') > 1:
                    parts = clean_val.split('.')
                    clean_val = f"{parts[0]}.{parts[1]}"

                # Stap C: Converteer naar float (DIT MISTE JE!)
                float_val = float(clean_val)

                # Stap D: Keer 100 en naar integer
                return int(float_val * 100)

            except Exception as e:
                _logger.warning(f"Fout bij lezen percentage {key}: {e}. Default {default_val} gebruikt.")
                return int(default_val * 100)

        # 3. GEBRUIK DE FUNCTIE
        cash_perc_int = get_safe_percentage('otters_consignment.cash_payout_percentage', 0.3)
        coupon_perc_int = get_safe_percentage('otters_consignment.coupon_payout_percentage', 0.5)

        values = {
            'is_closed': is_closed,
            'closed_message': closed_message,
            'cash_percentage': cash_perc_int,
            'coupon_percentage': coupon_perc_int,
            'partner': {},
        }

        if not request.env.user._is_public():
            partner = request.env.user.partner_id
            bank_acc = partner.bank_ids[:1].acc_number if partner.bank_ids else ''

            values.update({
                'default_name': partner.name,
                'default_email': partner.email,
                'default_street': partner.street,
                'default_street2': partner.street2,
                'default_zip': partner.zip,
                'default_city': partner.city,
                'default_iban': bank_acc,
            })

        return request.render('otters_consignment.consignment_form_template', values)

    @http.route('/kleding-opsturen/bedankt', type='http', auth='public', website=True)
    def consignment_form_thankyou(self, **kw):
        return request.render('otters_consignment.consignment_thankyou_template', {})