# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.tools.translate import _
import logging
import re
import requests
import base64
import json
from odoo.http import request
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

class ConsignmentSubmission(models.Model):
    _name = 'otters.consignment.submission'
    _description = 'Beheert de inzendingen van kleding door leveranciers.'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'portal.mixin']

    # --- VELDEN ---
    name = fields.Char(string="Inzending ID", required=True, readonly=True, default='Nieuw', copy=False)
    supplier_id = fields.Many2one('res.partner', string="Leverancier", required=True, tracking=True)
    submission_date = fields.Date(string="Inzendingsdatum", default=fields.Date.context_today, required=True, tracking=True)
    state = fields.Selection([('draft', 'Concept'), ('received', 'Ontvangen'), ('processing', 'In Behandeling'), ('sold', 'Verkocht'), ('done', 'Afgehandeld')], string='Status', default='draft', required=True, tracking=True)
    product_ids = fields.One2many('product.template', 'submission_id', string="Ingezonden Producten")

    sendcloud_label_url = fields.Char(string="Sendcloud Label URL", readonly=True, copy=False)

    payout_method = fields.Selection([('cash', 'Cash'), ('coupon', 'Coupon')], string="Payout Method", store=True, readonly=True, tracking=True)
    payout_percentage = fields.Float(string="Payout Percentage", store=True, readonly=True, tracking=True)

    # Tijdelijke velden voor het formulier
    x_sender_name = fields.Char(string="Naam", store=False)
    x_sender_email = fields.Char(string="E-mail", store=False)
    x_sender_phone = fields.Char(string="Telefoon", store=False)
    x_sender_street = fields.Char(string="Straat", store=False)
    x_sender_house_number = fields.Char(string="Huisnummer", store=False)
    x_sender_city = fields.Char(string="Stad", store=False)
    x_sender_postal_code = fields.Char(string="Postcode", store=False)
    x_sender_country_code = fields.Char(string="Landcode", store=False)
    x_payout_method_temp = fields.Selection([('cash', 'Cash'), ('coupon', 'Coupon')], string="Tijdelijke Payout", store=False)

    # --- KNOPPEN ACTIES ---
    def action_generate_sendcloud_label(self):
        """ Knop: Handmatig label maken """
        self.ensure_one()
        if self._create_sendcloud_parcel():
            # Melding tonen aan de gebruiker
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {'title': 'Succes', 'message': 'Label aangemaakt!', 'type': 'success', 'sticky': False}
            }

    def action_open_label(self):
        """ Knop: Open Label in nieuw tabblad """
        self.ensure_one()
        if self.sendcloud_label_url:
            return {
                'type': 'ir.actions.act_url',
                'url': self.sendcloud_label_url,
                'target': 'new',
            }

    # --- HELPER FUNCTIES ---
    def _get_sold_products(self):
        self = self.sudo()
        product_variant_ids = self.product_ids.product_variant_ids.ids
        if not product_variant_ids: return self.env['product.template']
        sold_lines = self.env['sale.order.line'].sudo().search([
            ('product_id', 'in', product_variant_ids),
            ('order_id.state', 'in', ['sale', 'done']),
            ('qty_invoiced', '>', 0),
        ])
        return self.product_ids & sold_lines.mapped('product_template_id')

    def _get_or_create_supplier_prefix(self, supplier):
        if supplier.x_consignment_prefix: return supplier.x_consignment_prefix
        if not supplier.name: return "PARTNER"
        parts = supplier.name.strip().split()
        prefix_base = ""
        if len(parts) >= 2:
            fn = re.sub(r'[^A-Z0-9]', '', parts[0][:2].upper())
            ln_base = re.sub(r'[^A-Z0-9]', '', parts[-1].upper())
            for i in range(2, len(ln_base) + 1):
                prefix_try = fn + ln_base[:i]
                if not prefix_try: continue
                if not self.env['res.partner'].search_count([('x_consignment_prefix', '=', prefix_try)]):
                    prefix_base = prefix_try
                    break
            if not prefix_base: prefix_base = fn + ln_base + str(supplier.id)
        elif len(parts) == 1 and parts[0]:
            prefix_base = re.sub(r'[^A-Z0-9]', '', parts[0][:4].upper())
        if not prefix_base: prefix_base = "INV"
        supplier.write({'x_consignment_prefix': prefix_base})
        return prefix_base

    def _format_phone_be(self, phone_number):
        if not phone_number: return ""
        clean_phone = re.sub(r'\D', '', phone_number)
        if clean_phone.startswith('32'): return f"+{clean_phone}"
        if clean_phone.startswith('0'): return f"+32{clean_phone[1:]}"
        return f"+32{clean_phone}"

    # --- CREATE & WRITE ---
    @api.model_create_multi
    def create(self, vals_list):
        # ... (Jouw bestaande logica voor partner aanmaken/updaten) ...
        new_vals_list = []
        for vals in vals_list:
            if vals.get('x_sender_email'):
                sender_email = vals.pop('x_sender_email')
                temp_payout_method = vals.pop('x_payout_method_temp')
                partner_vals = {
                    'name': vals.pop('x_sender_name'),
                    'email': sender_email,
                    'phone': vals.pop('x_sender_phone'),
                    'street': vals.pop('x_sender_street'),
                    'street2': vals.pop('x_sender_house_number'),
                    'city': vals.pop('x_sender_city'),
                    'zip': vals.pop('x_sender_postal_code'),
                    'country_id': self.env['res.country'].search([('code', '=', vals.pop('x_sender_country_code', 'BE'))], limit=1).id,
                }
                if temp_payout_method: partner_vals['x_payout_method'] = temp_payout_method

                Partner = self.env['res.partner'].sudo()
                partner = Partner.search([('email', '=ilike', sender_email)], limit=1)
                if partner: partner.write(partner_vals)
                else: partner = Partner.create(partner_vals)

                vals['supplier_id'] = partner.id
                for key in list(vals.keys()):
                    if key.startswith('x_sender_'): vals.pop(key, None)

                if temp_payout_method:
                    ICP = self.env['ir.config_parameter'].sudo()
                    cash_perc = float(ICP.get_param('otters_consignment.cash_payout_percentage', '0.3'))
                    coupon_perc = float(ICP.get_param('otters_consignment.coupon_payout_percentage', '0.5'))
                    if temp_payout_method == 'cash':
                        partner.sudo().write({'x_cash_payout_percentage': cash_perc, 'x_coupon_payout_percentage': 0.0})
                        vals['payout_percentage'] = cash_perc
                    else:
                        partner.sudo().write({'x_cash_payout_percentage': 0.0, 'x_coupon_payout_percentage': coupon_perc})
                        vals['payout_percentage'] = coupon_perc
                    vals['payout_method'] = temp_payout_method

            if vals.get('name', 'Nieuw') == 'Nieuw' and vals.get('supplier_id'):
                partner = self.env['res.partner'].browse(vals['supplier_id'])
                prefix = self._get_or_create_supplier_prefix(partner)
                next_number = self.env['ir.sequence'].next_by_code('otters.consignment.submission') or '00000'
                vals['name'] = f'{prefix}_{next_number}'
            new_vals_list.append(vals)

        submissions = super(ConsignmentSubmission, self).create(new_vals_list)

        # ### CHECK DIT: DE AUTOMATISCHE TRIGGER ###
        # Dit stuk zorgt ervoor dat het label direct wordt gemaakt bij het opslaan
        for submission in submissions:
            if submission.supplier_id:
                try:
                    # We roepen de functie aan. Als dit faalt, wordt het gelogd maar crasht de website niet.
                    submission.sudo()._create_sendcloud_parcel()
                except Exception as e:
                    _logger.error(f"FATALE FOUT: Sendcloud API-call mislukt voor inzending {submission.name}: {e}")

        return submissions

    def write(self, vals):
        # ... (Jouw bestaande write logica voor archiveren) ...
        removed_template_ids = []
        if 'product_ids' in vals:
            new_commands = []
            for command in vals['product_ids']:
                if command[0] == 2 and command[1]:
                    removed_template_ids.append(command[1])
                    new_commands.append((3, command[1], False))
                else: new_commands.append(command)
            if removed_template_ids: vals['product_ids'] = new_commands
        res = super(ConsignmentSubmission, self).write(vals)
        if removed_template_ids:
            self.env['product.template'].browse(removed_template_ids).write({'active': False})
        return res

    # --- SENDCLOUD LOGICA ---
    def _create_sendcloud_parcel(self):
        self.ensure_one()
        partner = self.supplier_id
        submission = self

        post = {
            'phone': partner.phone,
            'street': partner.street,
            'house_number': partner.street2,
            'city': partner.city,
            'postal_code': partner.zip,
            'country': partner.country_id.code,
        }

        _logger.info(f"Sendcloud Consignment: Start label aanmaak voor {submission.name}...")

        # ### CHECK DIT: OPHALEN KEYS ###
        # We gebruiken self.env.company (veiligste manier in backend code)
        company = self.env.company
        api_key = company.sendcloud_public_key
        api_secret = company.sendcloud_secret_key

        # Als dit faalt, zie je het in de logs!
        if not api_key or not api_secret:
            _logger.error(f"Sendcloud Error: API keys ontbreken op bedrijf {company.name} (ID: {company.id})")
            return False

        ICP = self.env['ir.config_parameter'].sudo()
        shipping_id = ICP.get_param('otters_consignment.sendcloud_shipping_method_id')

        # ... Ophalen winkel adres ...
        store_name = ICP.get_param('otters_consignment.store_name')
        store_street = ICP.get_param('otters_consignment.store_street')
        store_house_number = ICP.get_param('otters_consignment.store_house_number')
        store_city = ICP.get_param('otters_consignment.store_city')
        store_zip = ICP.get_param('otters_consignment.store_zip')
        store_country = ICP.get_param('otters_consignment.store_country_code')
        store_phone_raw = ICP.get_param('otters_consignment.store_phone')

        if not all([shipping_id, store_name, store_street, store_phone_raw]):
            _logger.error("Sendcloud Error: Winkeladres of verzendmethode ontbreekt in instellingen.")
            return False

        url = "https://panel.sendcloud.sc/api/v2/parcels"
        auth = (api_key, api_secret)
        headers = {"Content-Type": "application/json"}

        customer_phone_formatted = self._format_phone_be(post.get('phone'))
        store_phone_formatted = self._format_phone_be(store_phone_raw)

        payload = {
            "parcel": {
                "request_label": False,
                "is_return": False,
                "order_number": submission.name,
                "weight": "5.000",
                "shipping_method": int(shipping_id),
                "name": store_name,
                "company_name": store_name,
                "address": store_street,
                "house_number": store_house_number,
                "city": store_city,
                "postal_code": store_zip,
                "country": store_country,
                "telephone": store_phone_formatted,
                "from_name": partner.name,
                "from_address_1": post.get('street'),
                "from_house_number": post.get('house_number'),
                "from_city": post.get('city'),
                "from_postal_code": post.get('postal_code'),
                "from_country": post.get('country'),
                "from_telephone": customer_phone_formatted,
                "from_email": partner.email
            }
        }

        try:
            response = requests.post(url, headers=headers, json=payload, auth=auth)
            response.raise_for_status()
            data = response.json()
            label_url = data.get('parcel', {}).get('label', {}).get('label_printer')

            _logger.info(f"Sendcloud Succes: Label gemaakt! URL: {label_url}")

            # OPSLAAN
            submission.write({'sendcloud_label_url': label_url})
            return True

        except Exception as e:
            _logger.error(f"Sendcloud API Fout: {str(e)}")
            if 'response' in locals() and response:
                _logger.error(f"Response body: {response.text}")
            return False
