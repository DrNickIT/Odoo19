# -*- coding: utf-8 -*-
from odoo import models, fields, api
import logging
import re

_logger = logging.getLogger(__name__)

class ConsignmentSubmission(models.Model):
    _name = 'otters.consignment.submission'
    _description = 'Beheert de inzendingen van kleding door leveranciers.'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'portal.mixin'] # Belangrijk voor Portal

    name = fields.Char(string="Inzending ID", required=True, readonly=True, default='Nieuw', copy=False)
    supplier_id = fields.Many2one('res.partner', string="Leverancier", required=True, tracking=True)
    submission_date = fields.Date(string="Inzendingsdatum", default=fields.Date.context_today, required=True, tracking=True)
    state = fields.Selection([('draft', 'Concept'), ('received', 'Ontvangen'), ('processing', 'In Behandeling'), ('sold', 'Verkocht'), ('done', 'Afgehandeld')], string='Status', default='draft', required=True, tracking=True)
    product_ids = fields.One2many('product.template', 'submission_id', string="Ingezonden Producten")

    # --- Gerelateerde velden voor uitbetaling ---
    payout_method = fields.Selection(
        string="Payout Method",
        related="supplier_id.x_payout_method",
        store=True,
        readonly=True,
        help="The payout method chosen for this submission."
    )
    payout_percentage = fields.Float(
        string="Payout Percentage",
        # Gebruik de velden van de partner, store=False omdat de waarde in create/write wordt vastgelegd
        related="supplier_id.x_cash_payout_percentage",
        store=False,
        readonly=True,
        help="The payout percentage agreed upon at the time of this submission."
    )

    # --- LOGICA VOOR VERKOCHTE PRODUCTEN (Strikte check voor financiële correctheid) ---
    def _get_sold_products(self):
        """ Bepaalt welke producten van deze inzending definitief als verkocht moeten worden beschouwd,
            wanneer de order is bevestigd EN de hoeveelheid is gefactureerd.
        """
        # Gebruik sudo() om ACL-fouten te voorkomen bij het zoeken naar Verkooporders door een Portal-gebruiker
        self = self.sudo()
        product_variant_ids = self.product_ids.product_variant_ids.ids

        if not product_variant_ids:
            return self.env['product.template']

        # Zoek alle orderlijnen die:
        sold_lines = self.env['sale.order.line'].sudo().search([
            ('product_id', 'in', product_variant_ids),
            # 1. Bevestigde orderstatus hebben (definitief verkocht)
            ('order_id.state', 'in', ['sale', 'done']),
            # 2. Een gefactureerde hoeveelheid hebben (FINANCIEEL VASTGELEGD)
            ('qty_invoiced', '>', 0),
        ])

        sold_product_templates = sold_lines.mapped('product_template_id')

        # Geef de set van verkochte templates terug die in deze inzending zitten
        return self.product_ids & sold_product_templates

    # --- Create/Write logica voor auto-nummering, percentages en archiveren ---

    @api.model
    def _get_or_create_supplier_prefix(self, partner):
        """
        Krijgt of creëert een unieke prefix voor een leverancier.
        """
        if not partner.x_consignment_prefix:
            name_parts = re.findall(r'\b\w', partner.name.upper())
            prefix = "".join(name_parts[:2]).ljust(2, 'X')

            last_partner_id = self.env['res.partner'].search([], order='id desc', limit=1)
            suffix_num = (last_partner_id.id or 0) + 1
            unique_prefix = f"{prefix}{suffix_num:03d}"

            while self.env['res.partner'].search_count([('x_consignment_prefix', '=', unique_prefix)]):
                suffix_num += 1
                unique_prefix = f"{prefix}{suffix_num:03d}"

            partner.x_consignment_prefix = unique_prefix

        return partner.x_consignment_prefix

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            # 1. Automatisch nummeren
            if vals.get('name', 'Nieuw') == 'Nieuw':
                # Gebruik de standaard Odoo sequens (mits deze is gedefinieerd in XML)
                vals['name'] = self.env['ir.sequence'].next_by_code('otters.consignment.submission') or 'Nieuw'

            # 2. Vul het juiste uitbetalingspercentage in
            if vals.get('supplier_id'):
                supplier = self.env['res.partner'].browse(vals['supplier_id'])
                ICP = self.env['ir.config_parameter'].sudo()

                if supplier.x_payout_method == 'cash':
                    default_perc = ICP.get_param('otters_consignment.cash_payout_percentage', '0.3')
                    vals['payout_percentage'] = supplier.x_cash_payout_percentage or float(default_perc)
                elif supplier.x_payout_method == 'coupon':
                    default_perc = ICP.get_param('otters_consignment.coupon_payout_percentage', '0.5')
                    vals['payout_percentage'] = supplier.x_coupon_payout_percentage or float(default_perc)

        result = super(ConsignmentSubmission, self).create(vals_list)
        return result

    def write(self, vals):
        removed_template_ids = []

        if 'product_ids' in vals:
            new_commands = []

            for command in vals['product_ids']:
                if command[0] == 2 and command[1]:
                    # Onderschep de 'Delete' actie (commando 2)
                    removed_template_ids.append(command[1])

                    # Vervang 'Delete' (2, ID, False) door 'Unlink' (3, ID, False)
                    # om te voorkomen dat Odoo de product.template probeert te verwijderen.
                    new_commands.append((3, command[1], False))
                else:
                    new_commands.append(command)

            if removed_template_ids:
                vals['product_ids'] = new_commands

        # Voer de standaard Odoo write/update uit
        res = super(ConsignmentSubmission, self).write(vals)

        # Archiveer de Product Templates
        if removed_template_ids:
            templates_to_archive = self.env['product.template'].browse(removed_template_ids)

            # Archiveer: zet de 'active' status op False
            templates_to_archive.write({'active': False})

        return res
