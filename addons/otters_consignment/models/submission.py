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

    # === NIEUW: Jaar & Creatiedatum ===
    x_submission_year = fields.Integer(string="Jaar", compute='_compute_year', store=True, readonly=True)

    state = fields.Selection([
        ('draft', 'Nieuw'),
        ('received', 'Ontvangen'),
        ('online', 'Online'),
        ('done', 'Afgerond'),
        ('cancel', 'Geannuleerd'),
    ], string='Status', default='draft', tracking=True)

    product_ids = fields.One2many('product.template', 'submission_id', string="Ingezonden Producten")
    # NIEUWE TELLERS (Berekend en opgeslagen voor snelheid)
    product_count = fields.Integer(string="Aantal Producten", compute='_compute_counts', store=True)
    rejected_count = fields.Integer(string="Aantal Geweigerd", compute='_compute_counts', store=True)

    label_ids = fields.One2many('otters.consignment.label', 'submission_id', string="Verzendlabels")

    payout_method = fields.Selection(
        [('cash', 'Cash'), ('coupon', 'Coupon')],
        string="Payout Method",
        store=True,
        tracking=True,
        help="De uitbetaalmethode die definitief is vastgelegd voor deze inzending."
    )
    payout_percentage = fields.Float(
        string="Payout Percentage",
        store=True,
        tracking=True,
        help="Het uitbetalingspercentage dat definitief is vastgelegd voor deze inzending."
    )
    x_is_locked = fields.Boolean(string="Contract Vergrendeld", default=False, tracking=True, help="Indien aangevinkt, kunnen de uitbetalingsvoorwaarden niet meer gewijzigd worden.")

    # Tijdelijke velden voor het formulier
    x_sender_name = fields.Char(string="Naam", store=False)
    x_sender_email = fields.Char(string="E-mail", store=False)
    x_sender_street = fields.Char(string="Straat", store=False)
    x_sender_street2 = fields.Char(string="Bus / Toevoeging", store=False)
    x_sender_city = fields.Char(string="Stad", store=False)
    x_sender_postal_code = fields.Char(string="Postcode", store=False)
    x_sender_country_code = fields.Char(string="Landcode", store=False)
    x_payout_method_temp = fields.Selection([('cash', 'Cash'), ('coupon', 'Coupon')], string="Tijdelijke Payout", store=False)
    x_old_id = fields.Char(string="Oud Verzendzak ID", copy=False, readonly=True)


    label_count = fields.Integer(string="Aantal Labels", default=1, required=True)
    x_iban = fields.Char(string="IBAN Rekeningnummer")

    action_unaccepted = fields.Selection([
        ('donate', 'Schenken aan goed doel'),
        ('return', 'Terugsturen (€7,50)')
    ], string="Actie niet-weerhouden", default='donate', required=True)

    action_unsold = fields.Selection([
        ('donate', 'Schenken aan goed doel'),
        ('return', 'Terugsturen (€7,50)')
    ], string="Actie niet-verkocht (1 jaar)", default='donate', required=True)

    agreed_to_terms = fields.Boolean(string="Akkoord Algemene Voorwaarden", required=True, default=False)
    agreed_to_clothing_terms = fields.Boolean(string="Akkoord Kleding Voorwaarden", required=True, default=False)
    agreed_to_shipping_fee = fields.Boolean(string="Akkoord Verzendkosten (8eur)", required=True, default=False)

    rejected_line_ids = fields.One2many('otters.consignment.rejected.line', 'submission_id', string="Niet Weerhouden Items")

    @api.depends('product_ids', 'rejected_line_ids')
    def _compute_counts(self):
        for record in self:
            record.product_count = len(record.product_ids)
            record.rejected_count = len(record.rejected_line_ids)

    # 3. ACTIE: Handmatig vastleggen
    def action_lock_contract(self):
        self.write({'x_is_locked': True})

    # (Optioneel: actie om te ontgrendelen voor noodgevallen)
    def action_unlock_contract(self):
        self.write({'x_is_locked': False})

    def _compute_has_sales(self):
        for record in self:
            # 1. Haal alle varianten van de producten in deze inzending op
            variants = record.product_ids.product_variant_ids

            if not variants:
                record.x_has_sales = False
                continue

            # 2. Tel hoe vaak deze varianten voorkomen in bevestigde verkooporders
            sale_count = self.env['sale.order.line'].sudo().search_count([
                ('product_id', 'in', variants.ids),
                ('order_id.state', 'in', ['sale', 'done']) # Alleen bevestigde orders tellen
            ])

            # 3. Als teller > 0, dan zijn er verkopen en gaat het slot erop
            record.x_has_sales = sale_count > 0

    @api.onchange('payout_method')
    def _onchange_payout_method(self):
        if not self.payout_method:
            return

        ICP = self.env['ir.config_parameter'].sudo()
        if self.payout_method == 'cash':
            self.payout_percentage = float(ICP.get_param('otters_consignment.cash_payout_percentage', '0.3'))
        else:
            self.payout_percentage = float(ICP.get_param('otters_consignment.coupon_payout_percentage', '0.5'))

    @api.depends('submission_date')
    def _compute_year(self):
        for record in self:
            if record.submission_date:
                # NAAM GEWIJZIGD
                record.x_submission_year = record.submission_date.year
            else:
                record.x_submission_year = fields.Date.today().year

    def action_generate_sendcloud_label(self):
        self.ensure_one()
        if self._create_sendcloud_parcel():
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {'title': 'Succes', 'message': 'Label aangemaakt!', 'type': 'success', 'sticky': False}
            }

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

    @api.model_create_multi
    def create(self, vals_list):
        new_vals_list = []

        # We houden bij welke records van de website komen (op basis van index in de lijst)
        indices_from_website = set()

        for i, vals in enumerate(vals_list):
            # Check: Komt dit van de website? (Heeft het de tijdelijke velden?)
            if vals.get('x_sender_email'):
                indices_from_website.add(i) # Ja, zet index op de lijst voor automatische verwerking

                # --- PARTNER LOGICA (Website only) ---
                raw_email = vals.pop('x_sender_email', '').strip()
                temp_payout_method = vals.pop('x_payout_method_temp')

                name_val = vals.pop('x_sender_name', False)
                street_val = vals.pop('x_sender_street', False)
                street2_val = vals.pop('x_sender_street2', '')
                city_val = vals.pop('x_sender_city', False)
                zip_val = vals.pop('x_sender_postal_code', False)
                country_code_val = vals.pop('x_sender_country_code', 'BE')

                partner_vals = {
                    'name': name_val,
                    'email': raw_email,
                    'street': street_val,
                    'street2': street2_val,
                    'city': city_val,
                    'zip': zip_val,
                    'country_id': self.env['res.country'].search([('code', '=', country_code_val)], limit=1).id,
                }

                if temp_payout_method: partner_vals['x_payout_method'] = temp_payout_method
                Partner = self.env['res.partner'].sudo()
                partner = Partner.search([('email', '=ilike', raw_email)], limit=1)
                if partner: partner.write(partner_vals)
                else: partner = Partner.create(partner_vals)

                vals['supplier_id'] = partner.id

                # Cleanup overige x_sender velden
                for key in list(vals.keys()):
                    if key.startswith('x_sender_'): vals.pop(key, None)

                # Percentages instellen
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

                # IBAN opslaan
                iban_to_save = vals.get('x_iban')
                if iban_to_save and partner:
                    clean_iban = iban_to_save.replace(' ', '').strip()
                    existing_bank = self.env['res.partner.bank'].search([
                        ('acc_number', '=', clean_iban),
                        ('partner_id', '=', partner.id)
                    ], limit=1)
                    if not existing_bank:
                        self.env['res.partner.bank'].create({'acc_number': clean_iban, 'partner_id': partner.id})

            # Naam genereren (Prefix) - Dit gebeurt voor ZOWEL website als backend
            if vals.get('name', 'Nieuw') == 'Nieuw' and vals.get('supplier_id'):
                partner = self.env['res.partner'].browse(vals['supplier_id'])
                prefix = self._get_or_create_supplier_prefix(partner)
                next_number = self.env['ir.sequence'].next_by_code('otters.consignment.submission') or '00000'
                vals['name'] = f'{prefix}_{next_number}'

            new_vals_list.append(vals)

        # De daadwerkelijke aanmaak in de database
        submissions = super(ConsignmentSubmission, self).create(new_vals_list)

        # --- AUTOMATISATIE (Alleen als NIET migratie) ---
        if not self.env.context.get('skip_sendcloud'):

            # 1. MAIL TEMPLATE OPHALEN
            template = self.env.ref('otters_consignment.mail_template_consignment_label_order', raise_if_not_found=False)

            for i, submission in enumerate(submissions):

                # CRUCIALE CHECK: Is dit een website submission? (index staat in de set)
                # Zo nee (backend aanmaak), dan doen we NIETS.
                if i in indices_from_website:

                    if submission.supplier_id:
                        # A. Sendcloud Label
                        try:
                            for _ in range(submission.label_count):
                                submission.sudo()._create_sendcloud_parcel()
                        except Exception as e:
                            _logger.error(f"Sendcloud Fout: {e}")

                        # B. E-mail versturen
                        partner_email = submission.supplier_id.email
                        if template and partner_email:
                            try:
                                template.sudo().send_mail(submission.id, force_send=True)
                                _logger.info(f"Mail verstuurd naar {partner_email}")
                            except Exception as e:
                                _logger.error(f"CRASH BIJ VERZENDEN: {e}")
        else:
            _logger.info("Migratie bezig: Sendcloud en E-mails onderdrukt.")

        return submissions

    def write(self, vals):
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

    def _create_sendcloud_parcel(self):
        # (Sendcloud functie blijft ongewijzigd, maar voor volledigheid hier)
        self.ensure_one()
        partner = self.supplier_id
        submission = self
        post = {
            'phone': partner.phone,
            'street': partner.street,
            'street2': partner.street2,
            'city': partner.city,
            'postal_code': partner.zip,
            'country': partner.country_id.code,
        }
        _logger.info(f"Sendcloud Consignment: Start label aanmaak voor {submission.name}...")
        company = self.env.company
        api_key = company.sendcloud_public_key
        api_secret = company.sendcloud_secret_key

        # Als dit faalt, zie je het in de logs!
        if not api_key or not api_secret:
            _logger.error(f"Sendcloud Error: API keys ontbreken op bedrijf {company.name} (ID: {company.id})")
            return False

        ICP = self.env['ir.config_parameter'].sudo()
        shipping_id = ICP.get_param('otters_consignment.sendcloud_shipping_method_id')
        store_name = ICP.get_param('otters_consignment.store_name')
        store_street = ICP.get_param('otters_consignment.store_street')
        store_house_number = ICP.get_param('otters_consignment.store_house_number')
        store_city = ICP.get_param('otters_consignment.store_city')
        store_zip = ICP.get_param('otters_consignment.store_zip')
        store_country = ICP.get_param('otters_consignment.store_country_code')
        store_phone_raw = ICP.get_param('otters_consignment.store_phone')
        if not all([shipping_id, store_name, store_street, store_phone_raw]): return False
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
                "from_house_number": post.get('street2'),
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
            parcel_data = data.get('parcel', {})
            label_url = parcel_data.get('label', {}).get('label_printer')
            tracking_nr = parcel_data.get('tracking_number')
            if label_url:
                self.env['otters.consignment.label'].sudo().create({'submission_id': self.id, 'label_url': label_url, 'tracking_number': tracking_nr})
            return True
        except Exception as e:
            _logger.error(f"Sendcloud API Fout: {str(e)}")
            return False