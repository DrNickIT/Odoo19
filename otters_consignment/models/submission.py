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

    _sql_constraints = [
        ('name_unique', 'UNIQUE(name)', 'Het Inzending ID moet uniek zijn!'),
    ]

    # --- 1. BASIS VELDEN ---
    name = fields.Char(string="Inzending ID", required=True, readonly=True, default='Nieuw', copy=False)
    supplier_id = fields.Many2one('res.partner', string="Leverancier", required=True, tracking=True)
    submission_date = fields.Date(string="Inzendingsdatum", default=fields.Date.context_today, required=True, tracking=True)

    x_submission_year = fields.Integer(string="Jaar", compute='_compute_year', store=True, readonly=True)

    state = fields.Selection([
        ('draft', 'Nieuw'),
        ('received', 'Ontvangen'),
        ('online', 'Online'),
        ('done', 'Afgerond'),
        ('cancel', 'Geannuleerd'),
    ], string='Status', default='draft', tracking=True)

    # --- 2. RELATIES & TELLERS ---
    product_ids = fields.One2many('product.template', 'submission_id', string="Ingezonden Producten")
    product_count = fields.Integer(string="Aantal Producten", compute='_compute_counts', store=True)

    rejected_line_ids = fields.One2many('otters.consignment.rejected.line', 'submission_id', string="Niet Weerhouden Items")
    rejected_count = fields.Integer(string="Aantal Geweigerd", compute='_compute_counts', store=True)

    label_ids = fields.One2many('otters.consignment.label', 'submission_id', string="Verzendlabels")

    # --- 3. FINANCIEEL & CONTRACT ---
    payout_method = fields.Selection(
        [('cash', 'Cash'), ('coupon', 'Coupon')],
        string="Payout Method",
        store=True, tracking=True
    )
    payout_percentage = fields.Float(string="Payout Percentage", store=True, tracking=True)

    discount_percentage = fields.Integer(string="Korting (%)", default=0)
    discount_reason = fields.Char(string="Reden Korting")

    x_iban = fields.Char(string="IBAN Rekeningnummer")

    # --- 4. VOORWAARDEN & KEUZES ---
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

    # --- 5. TIJDELIJKE VELDEN (Website Formulier Tunnel) ---
    x_sender_name = fields.Char(store=False)
    x_sender_email = fields.Char(store=False)
    x_sender_street = fields.Char(store=False)
    x_sender_street2 = fields.Char(store=False)
    x_sender_city = fields.Char(store=False)
    x_sender_postal_code = fields.Char(store=False)
    x_sender_country_code = fields.Char(store=False)
    x_payout_method_temp = fields.Selection([('cash', 'Cash'), ('coupon', 'Coupon')], store=False)
    x_old_id = fields.Char(string="Oud Verzendzak ID", copy=False, readonly=True)

    label_count = fields.Integer(string="Aantal Zakken", default=1, required=True)


    # =================================================================================
    # LOGICA
    # =================================================================================

    @api.depends('product_ids', 'rejected_line_ids')
    def _compute_counts(self):
        for record in self:
            record.product_count = len(record.product_ids)
            record.rejected_count = len(record.rejected_line_ids)

    @api.depends('submission_date')
    def _compute_year(self):
        for record in self:
            record.x_submission_year = record.submission_date.year if record.submission_date else fields.Date.today().year

    @api.onchange('payout_method')
    def _onchange_payout_method(self):
        if not self.payout_method: return
        ICP = self.env['ir.config_parameter'].sudo()
        if self.payout_method == 'cash':
            self.payout_percentage = float(ICP.get_param('otters_consignment.cash_payout_percentage', '0.3'))
        else:
            self.payout_percentage = float(ICP.get_param('otters_consignment.coupon_payout_percentage', '0.5'))

    # =================================================================================
    # CREATE MET SPLIT LOGICA
    # =================================================================================

    @api.model_create_multi
    def create(self, vals_list):
        expanded_vals_list = []
        website_submission_indices = []
        total_bags_requested = 0
        is_website_request = False

        for vals in vals_list:
            is_website = bool(vals.get('x_sender_email'))
            count = int(vals.get('label_count', 1))

            if is_website:
                is_website_request = True
                total_bags_requested += count

            if is_website and count > 1:
                for _ in range(count):
                    new_vals = vals.copy()
                    new_vals['label_count'] = 1
                    expanded_vals_list.append(new_vals)
                    website_submission_indices.append(len(expanded_vals_list) - 1)
            else:
                expanded_vals_list.append(vals)
                if is_website:
                    website_submission_indices.append(len(expanded_vals_list) - 1)

        for i, vals in enumerate(expanded_vals_list):
            if i in website_submission_indices:
                self._process_partner_data(vals)

            if vals.get('name', 'Nieuw') == 'Nieuw' and vals.get('supplier_id'):
                partner = self.env['res.partner'].browse(vals['supplier_id'])
                prefix = self._get_or_create_supplier_prefix(partner)
                next_number = self.env['ir.sequence'].next_by_code('otters.consignment.submission') or '00000'
                vals['name'] = f'{prefix}_{next_number}'

        submissions = super(ConsignmentSubmission, self).create(expanded_vals_list)

        if is_website_request and not self.env.context.get('skip_sendcloud') and submissions:
            primary_submission = submissions[0]

            # Klant mail
            template_customer = self.env.ref('otters_consignment.mail_template_consignment_confirmation', raise_if_not_found=False)
            if template_customer and primary_submission.supplier_id.email:
                try:
                    template_customer.with_context(total_bags=total_bags_requested).sudo().send_mail(primary_submission.id, force_send=True)
                except Exception as e:
                    _logger.error(f"Fout mail klant: {e}")

            # Admin mail
            template_admin = self.env.ref('otters_consignment.mail_template_consignment_admin_alert', raise_if_not_found=False)
            company_email = self.env.company.email
            if template_admin and company_email:
                try:
                    template_admin.with_context(total_bags=total_bags_requested).sudo().send_mail(primary_submission.id, force_send=True)
                except Exception as e:
                    _logger.error(f"Fout mail admin: {e}")

        # Singleton fix voor website controller
        if len(vals_list) == 1 and len(submissions) > 1:
            return submissions[0]

        return submissions

    def _process_partner_data(self, vals):
        raw_email = vals.pop('x_sender_email', '').strip()
        temp_payout_method = vals.pop('x_payout_method_temp', False)
        name_val = vals.pop('x_sender_name', False)
        street_val = vals.pop('x_sender_street', False)
        street2_val = vals.pop('x_sender_street2', '')
        city_val = vals.pop('x_sender_city', False)
        zip_val = vals.pop('x_sender_postal_code', False)
        country_code_val = vals.pop('x_sender_country_code', 'BE')
        partner_vals = {
            'name': name_val, 'email': raw_email,
            'street': street_val, 'street2': street2_val,
            'city': city_val, 'zip': zip_val,
            'country_id': self.env['res.country'].search([('code', '=', country_code_val)], limit=1).id,
        }
        Partner = self.env['res.partner'].sudo()
        partner = False
        current_user = self.env.user
        is_real_customer = not current_user._is_public() and not current_user.has_group('base.group_user')
        if is_real_customer:
            partner = current_user.partner_id
            partner.write(partner_vals)
        else:
            if raw_email:
                found_partners = Partner.search([('email', '=ilike', raw_email)])
                for p in found_partners:
                    if not any(u.has_group('base.group_user') for u in p.user_ids):
                        partner = p
                        break
                if partner: partner.write(partner_vals)
                else: partner = Partner.create(partner_vals)
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
        iban_to_save = vals.get('x_iban')
        if iban_to_save and partner:
            clean_iban = iban_to_save.replace(' ', '').strip()
            existing_bank = self.env['res.partner.bank'].search([('acc_number', '=', clean_iban), ('partner_id', '=', partner.id)], limit=1)
            if not existing_bank: self.env['res.partner.bank'].create({'acc_number': clean_iban, 'partner_id': partner.id})

    # =================================================================================
    # ACTIONS
    # =================================================================================

    def action_generate_sendcloud_label(self):
        self.ensure_one()
        if self._create_sendcloud_parcel():
            template_label = self.env.ref('otters_consignment.mail_template_consignment_label_send', raise_if_not_found=False)
            if template_label and self.supplier_id.email:
                try:
                    template_label.sudo().send_mail(self.id, force_send=True)
                    return {
                        'type': 'ir.actions.client',
                        'tag': 'display_notification',
                        'params': {'title': 'Succes', 'message': 'Label aangemaakt en gemaild naar de klant!', 'type': 'success', 'sticky': False}
                    }
                except Exception as e:
                    return {
                        'type': 'ir.actions.client',
                        'tag': 'display_notification',
                        'params': {'title': 'Label OK, Mail Fout', 'message': f'Label is gemaakt, maar mail faalde: {e}', 'type': 'warning', 'sticky': True}
                    }
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {'title': 'Succes', 'message': 'Label aangemaakt! (Geen mail verstuurd)', 'type': 'success', 'sticky': False}
            }
        else:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {'title': 'Fout', 'message': 'Kon geen label aanmaken. Check logs.', 'type': 'danger', 'sticky': True}
            }

    def _create_sendcloud_parcel(self):
        self.ensure_one()
        partner = self.supplier_id
        submission = self
        post = {'phone': partner.phone, 'street': partner.street, 'street2': partner.street2, 'city': partner.city, 'postal_code': partner.zip, 'country': partner.country_id.code}
        company = self.env.company
        api_key = company.sendcloud_public_key
        api_secret = company.sendcloud_secret_key
        if not api_key or not api_secret: return False
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
        payload = {"parcel": {"request_label": False, "is_return": False, "order_number": submission.name, "weight": "5.000", "shipping_method": int(shipping_id), "name": store_name, "company_name": store_name, "address": store_street, "house_number": store_house_number, "city": store_city, "postal_code": store_zip, "country": store_country, "telephone": store_phone_formatted, "from_name": partner.name, "from_address_1": post.get('street'), "from_house_number": post.get('street2'), "from_city": post.get('city'), "from_postal_code": post.get('postal_code'), "from_country": post.get('country'), "from_telephone": customer_phone_formatted, "from_email": partner.email}}
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

    def _get_sold_products(self):
        self = self.sudo()
        product_variant_ids = self.product_ids.product_variant_ids.ids
        if not product_variant_ids: return self.env['product.template']
        sold_lines = self.env['sale.order.line'].sudo().search([('product_id', 'in', product_variant_ids), ('order_id.state', 'in', ['sale', 'done']), ('qty_invoiced', '>', 0)])
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
        elif len(parts) == 1 and parts[0]: prefix_base = re.sub(r'[^A-Z0-9]', '', parts[0][:4].upper())
        if not prefix_base: prefix_base = "INV"
        supplier.write({'x_consignment_prefix': prefix_base})
        return prefix_base

    def _format_phone_be(self, phone_number):
        if not phone_number: return ""
        clean_phone = re.sub(r'\D', '', phone_number)
        if clean_phone.startswith('32'): return f"+{clean_phone}"
        if clean_phone.startswith('0'): return f"+32{clean_phone[1:]}"
        return f"+32{clean_phone}"

    def action_apply_discount(self):
        self.ensure_one()
        available_products = self.product_ids.filtered(lambda p: p.virtual_available > 0)
        for product in available_products:
            original_price = product.compare_list_price or product.list_price
            if self.discount_percentage > 0:
                if not product.compare_list_price: product.compare_list_price = original_price
                discount_factor = 1 - (self.discount_percentage / 100)
                new_price = original_price * discount_factor
                product.list_price = new_price
            else:
                if product.compare_list_price:
                    product.list_price = product.compare_list_price
                    product.compare_list_price = 0.0
        if self.discount_percentage > 0: self.message_post(body=f"Korting van {self.discount_percentage}% toegepast op {len(available_products)} beschikbare items. Reden: {self.discount_reason}")
        else: self.message_post(body=f"Korting verwijderd van {len(available_products)} beschikbare items.")

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
        if removed_template_ids: self.env['product.template'].browse(removed_template_ids).write({'active': False})
        return res