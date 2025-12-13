# -*- coding: utf-8 -*-
from odoo import models, fields, api
import re
import logging

_logger = logging.getLogger(__name__)

class ConsignmentSubmission(models.Model):
    _name = 'otters.consignment.submission'
    _description = 'Beheert de inzendingen van kleding door leveranciers.'
    # HIER IS DE MAGIE: We erven van onze nieuwe mixin!
    _inherit = ['mail.thread', 'mail.activity.mixin', 'portal.mixin', 'otters.consignment.integrations']

    _sql_constraints = [
        ('name_unique', 'UNIQUE(name)', 'Het Inzending ID moet uniek zijn!'),
    ]

    # --- 1. BASIS VELDEN ---
    name = fields.Char(string="Inzending ID", required=True, readonly=True, default='Nieuw', copy=False)
    supplier_id = fields.Many2one('res.partner', string="Leverancier", required=True, tracking=True)
    submission_date = fields.Date(string="Inzendingsdatum", default=fields.Date.context_today, required=True, tracking=True)
    date_published = fields.Date(string="Datum Online", help="De datum waarop de producten online zijn geplaatst.", tracking=True)

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
    x_legacy_code = fields.Char(string="Oude Code (CSV)", copy=False, readonly=True, index=True)

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

    @api.model_create_multi
    def create(self, vals_list):
        expanded_vals_list, website_indices, total_bags = self._expand_multibag_requests(vals_list)

        for i, vals in enumerate(expanded_vals_list):
            if i in website_indices:
                self._handle_website_partner_data(vals)

            if vals.get('name', 'Nieuw') == 'Nieuw' and vals.get('supplier_id'):
                vals['name'] = self._generate_submission_name(vals)

        submissions = super(ConsignmentSubmission, self).create(expanded_vals_list)

        if website_indices and not self.env.context.get('skip_sendcloud'):
            # Deze functie komt nu uit de Mixin!
            self._send_confirmation_emails(submissions, total_bags)

        if len(vals_list) == 1 and len(submissions) > 1:
            return submissions[0]
        return submissions

    # Hulpfuncties voor create (houden we hier omdat ze business-specifiek zijn)
    def _expand_multibag_requests(self, vals_list):
        expanded = []
        website_indices = []
        total_bags_requested = 0
        for vals in vals_list:
            is_website = bool(vals.get('x_sender_email'))
            count = int(vals.get('label_count', 1))
            if is_website: total_bags_requested += count

            if is_website and count > 1:
                for _ in range(count):
                    new_vals = vals.copy()
                    new_vals['label_count'] = 1
                    expanded.append(new_vals)
                    website_indices.append(len(expanded) - 1)
            else:
                expanded.append(vals)
                if is_website: website_indices.append(len(expanded) - 1)
        return expanded, website_indices, total_bags_requested

    def _generate_submission_name(self, vals):
        partner = self.env['res.partner'].browse(vals['supplier_id'])
        prefix = self._get_or_create_supplier_prefix(partner)
        next_number = self.env['ir.sequence'].next_by_code('otters.consignment.submission') or '00000'
        return f'{prefix}_{next_number}'

    def _handle_website_partner_data(self, vals):
        raw_email = vals.pop('x_sender_email', '').strip()
        temp_payout_method = vals.pop('x_payout_method_temp', False)

        partner_vals = {
            'name': vals.pop('x_sender_name', False),
            'email': raw_email,
            'street': vals.pop('x_sender_street', False),
            'street2': vals.pop('x_sender_street2', ''),
            'city': vals.pop('x_sender_city', False),
            'zip': vals.pop('x_sender_postal_code', False),
            'country_id': False
        }

        country_code = vals.pop('x_sender_country_code', 'BE')
        if country_code:
            country = self.env['res.country'].search([('code', '=', country_code)], limit=1)
            if country: partner_vals['country_id'] = country.id

        Partner = self.env['res.partner'].sudo()
        partner = False
        current_user = self.env.user

        if not current_user._is_public() and not current_user.has_group('base.group_user'):
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

    # Hulpfuncties voor prefix en discount
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

    def _get_sold_lines(self):
        """ Geeft ALLE verkoopregels terug (Betaald én Onbetaald) """
        self = self.sudo()
        product_variant_ids = self.product_ids.product_variant_ids.ids

        if not product_variant_ids:
            return self.env['sale.order.line']

        # We zoeken nu alles wat in een order zit (ongeacht betaalstatus)
        return self.env['sale.order.line'].search([
            ('product_id', 'in', product_variant_ids),
            ('order_id.state', 'in', ['sale', 'done'])
        ])

    def _get_portal_sold_data(self):
        """ Bouwt de geaggregeerde lijst, inclusief betaalstatus """
        self = self.sudo()
        lines = self._get_sold_lines()

        grouped_data = {}

        for line in lines:
            # We voegen nu ook de betaalstatus toe aan de sleutel
            # Zo worden betaalde en onbetaalde regels niet op één hoop gegooid
            is_paid = line.x_is_paid_out
            date_val = line.x_payout_date or line.order_id.date_order.date()

            # Key = (Product, Datum, IsBetaald)
            key = (line.product_id, date_val, is_paid)

            if key not in grouped_data:
                grouped_data[key] = {
                    'product': line.product_id,
                    'name': line.product_id.name,
                    'qty': 0.0,
                    'price_sold': 0.0,
                    'payout': 0.0,
                    'date': date_val,
                    'is_paid': is_paid,       # <--- Belangrijk voor filtering straks
                    'currency': line.currency_id
                }

            grouped_data[key]['qty'] += line.product_uom_qty
            grouped_data[key]['price_sold'] += (line.price_unit * line.product_uom_qty)
            grouped_data[key]['payout'] += line.x_fixed_commission

        return list(grouped_data.values())

    def action_view_products(self):
        self.ensure_one()
        return {
            'name': 'Producten',
            'type': 'ir.actions.act_window',
            'res_model': 'product.template',
            'view_mode': 'list,form',
            # FILTER: Toon alleen producten van DEZE inzending
            'domain': [('submission_id', '=', self.id)],
            'context': {
                'default_submission_id': self.id,
                'default_is_published': True,
                # Zorg dat we terug kunnen keren
                'search_default_submission_id': self.id
            },
        }

    def action_set_online_and_notify(self):
        """ Zet de status op online, VUL DE DATUM IN en stuur een mail naar de klant. """
        self.ensure_one()

        # 1. Update status en DATUM
        vals = {'state': 'online'}

        # Als er nog geen online datum is, vul vandaag in
        if not self.date_published:
            vals['date_published'] = fields.Date.today()

        self.write(vals)

        # 2. Stuur E-mail (Bestaande code)
        if not self.supplier_id.email:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {'title': 'Let op', 'message': 'Klant heeft geen e-mailadres, status is wel gewijzigd.', 'type': 'warning'}
            }

        template = self.env.ref('otters_consignment.mail_template_consignment_is_online', raise_if_not_found=False)
        if template:
            template.sudo().send_mail(self.id, force_send=True)

        self.message_post(body="Klant is per mail verwittigd. Datum Online is ingesteld.")

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Online Gezet',
                'message': 'Status is Online, datum is ingesteld en mail is verstuurd.',
                'type': 'success',
                'sticky': False,
            }
        }