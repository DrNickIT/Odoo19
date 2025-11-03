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

    @http.route('/kleding-opsturen/check-partner', type='jsonrpc', auth='public', website=True, methods=['POST'], csrf=False)
    def check_partner_payout(self, **kw):
        email = kw.get('email')
        if not email:
            return {'payout_method_set': False}
        partner = request.env['res.partner'].sudo().search([('email', '=ilike', email.strip())], limit=1)
        if partner and partner.x_payout_method:
            return {'payout_method_set': True}
        return {'payout_method_set': False}

    @http.route('/kleding-opsturen/submit', type='http', auth='public', website=True, csrf=True, methods=['POST'])
    def consignment_form_submit(self, **post):
        # --- STAP 1: PARTNER AANMAKEN/UPDATEN ---
        email = post.get('email')
        name = post.get('contact_name')
        payout_method = post.get('payout_method')
        country_id = request.env['res.country'].sudo().search([('code', '=', post.get('country'))], limit=1).id
        street_val = f"{post.get('street')} {post.get('house_number')}"
        partner_vals = {
            'name': name, 'email': email, 'street': street_val,
            'city': post.get('city'), 'zip': post.get('postal_code'),
            'country_id': country_id, 'phone': post.get('phone')
        }
        Partner = request.env['res.partner'].sudo()
        ICP = request.env['ir.config_parameter'].sudo()
        partner = Partner.search([('email', '=ilike', email.strip())], limit=1)
        if not partner:
            default_cash = float(ICP.get_param('otters_consignment.cash_payout_percentage', '0.3'))
            default_coupon = float(ICP.get_param('otters_consignment.coupon_payout_percentage', '0.5'))
            partner_vals.update({
                'x_payout_method': payout_method,
                'x_cash_payout_percentage': default_cash,
                'x_coupon_payout_percentage': default_coupon
            })
            partner = Partner.create(partner_vals)
        else:
            write_vals = partner_vals.copy()
            if not partner.x_payout_method and payout_method:
                write_vals['x_payout_method'] = payout_method
            partner.write(write_vals)

        # --- STAP 2: INZENDING AANMAKEN ---
        submission = request.env['otters.consignment.submission'].sudo().create({
            'supplier_id': partner.id,
            'payout_method': partner.x_payout_method,
            'payout_percentage': (
                partner.x_cash_payout_percentage
                if partner.x_payout_method == 'cash'
                else partner.x_coupon_payout_percentage
            ),
        })

        # --- STAP 3: SENDCLOUD LABEL AANMAKEN ---
        try:
            self._create_sendcloud_label(partner, submission, post)
        except Exception as e:
            _logger.error(f"Failed to create Sendcloud label for submission {submission.name}: {e}")

        # --- STAP 4: DOORSTUREN ---
        return request.redirect('/kleding-opsturen/bedankt')

    def _format_phone_be(self, phone_number):
        """Zet een Belgisch telefoonnummer om naar E.164-formaat."""
        if not phone_number:
            return "" # Stuur een lege string, geen 'None'
        clean_phone = re.sub(r'\D', '', phone_number)
        if clean_phone.startswith('32'):
            return f"+{clean_phone}"
        if clean_phone.startswith('0'):
            return f"+32{clean_phone[1:]}"
        return f"+32{clean_phone}"

    # --- *** HIER IS DE DEFINITIEVE, WERKENDE FUNCTIE *** ---
    def _create_sendcloud_label(self, partner, submission, post):
        _logger.info(f"Attempting to create Sendcloud label via V2/PARCELS endpoint for {submission.name}...")

        # Haal de API-sleutels en config op uit Odoo
        ICP = request.env['ir.config_parameter'].sudo()
        api_key = ICP.get_param('otters_consignment.sendcloud_api_key')
        api_secret = ICP.get_param('otters_consignment.sendcloud_api_secret')

        # We gebruiken nu weer 'shipping_method_id' (het getal, bv. 8)
        shipping_id = ICP.get_param('otters_consignment.sendcloud_shipping_method_id')

        # Haal de adresgegevens van de WINKEL (ontvanger) op
        store_name = ICP.get_param('otters_consignment.store_name')
        store_street = ICP.get_param('otters_consignment.store_street')
        store_house_number = ICP.get_param('otters_consignment.store_house_number')
        store_city = ICP.get_param('otters_consignment.store_city')
        store_zip = ICP.get_param('otters_consignment.store_zip')
        store_country = ICP.get_param('otters_consignment.store_country_code')
        store_phone_raw = ICP.get_param('otters_consignment.store_phone')

        if not all([api_key, api_secret, shipping_id, store_name, store_street, store_phone_raw]):
            _logger.error("Sendcloud config (API keys, shipping_method_ID, or store address) is incomplete.")
            return

        # We gebruiken de V2/PARCELS endpoint
        url = "https://panel.sendcloud.sc/api/v2/parcels"
        auth = base64.b64encode(f"{api_key}:{api_secret}".encode('utf-8')).decode('ascii')
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Basic {auth}"
        }

        # Formatteer de telefoonnummers
        customer_phone_formatted = self._format_phone_be(post.get('phone'))
        store_phone_formatted = self._format_phone_be(store_phone_raw)

        # De werkende payload-structuur
        payload = {
            "parcel": {
                "request_label": True,
                "is_return": False, # Zoals je hebt getest
                "order_number": submission.name,
                "weight": "5.000",
                "shipping_method": int(shipping_id),

                # --- De WINKEL (Ontvanger) ---
                "name": store_name,
                "company_name": store_name,
                "address": store_street,
                "house_number": store_house_number,
                "city": store_city,
                "postal_code": store_zip,
                "country": store_country, # bv. "BE"
                "telephone": store_phone_formatted,

                # --- De KLANT (Afzender) ---
                "from_name": partner.name,
                "from_address_1": post.get('street'), # Jouw 'from_address_1' fix
                "from_house_number": post.get('house_number'),
                "from_city": post.get('city'),
                "from_postal_code": post.get('postal_code'),
                "from_country": post.get('country'), # bv. "BE"
                "from_telephone": customer_phone_formatted,
                "from_email": partner.email
            }
        }

        _logger.info(f"--- VERZENDE SENDCLOUD V2 PAYLOAD (naar /parcels) ---")
        _logger.info(json.dumps(payload, indent=2))
        _logger.info(f"-------------------------------------------------------")

        # Maak de API-call
        response = requests.post(url, headers=headers, data=json.dumps(payload))

        if response.status_code == 200 or response.status_code == 201:
            # SUCCES!
            data = response.json()
            # De V2 response-structuur
            label_url = data.get('parcel', {}).get('label', {}).get('label_printer')
            _logger.info(f"Sendcloud V2 LABEL created! URL: {label_url}")

        else:
            # FOUT!
            _logger.error(f"Sendcloud V2 API error: {response.status_code} - {response.text}")
            raise Exception(f"Sendcloud V2 API error: {response.text}")


    @http.route('/kleding-opsturen/bedankt', type='http', auth='public', website=True)
    def consignment_form_thankyou(self, **kw):
        return request.render('otters_consignment.consignment_thankyou_template', {})
