# -*- coding: utf-8 -*-
from odoo import models, fields, api
import logging
import re

_logger = logging.getLogger(__name__)

class ConsignmentSubmission(models.Model):
    _name = 'otters.consignment.submission'
    _description = 'Beheert de inzendingen van kleding door leveranciers.'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string="Inzending ID", required=True, readonly=True, default='Nieuw', copy=False)
    supplier_id = fields.Many2one('res.partner', string="Leverancier", required=True, tracking=True)
    submission_date = fields.Date(string="Inzendingsdatum", default=fields.Date.context_today, required=True, tracking=True)
    state = fields.Selection([('draft', 'Concept'), ('received', 'Ontvangen'), ('processing', 'In Behandeling'), ('sold', 'Verkocht'), ('done', 'Afgehandeld')], string='Status', default='draft', required=True, tracking=True)
    product_ids = fields.One2many('product.template', 'submission_id', string="Ingezonden Producten")
    # --- ADD THESE TWO FIELDS ---
    payout_method = fields.Selection(
        string="Payout Method",
        related="supplier_id.x_payout_method",
        store=True,
        readonly=True,
        help="The payout method chosen for this submission."
    )
    payout_percentage = fields.Float(
        string="Payout Percentage",
        readonly=True,
        help="The payout percentage agreed upon at the time of this submission."
    )
    # --- END OF NEW FIELDS ---

    def _get_or_create_supplier_prefix(self, supplier):
        """
        Gets or creates a unique prefix for the given supplier.
        e.g., "Tom Hoornaert" -> "TOHO"
        e.g., "Tomas Hoogland" -> "TOHOO" (if "TOHO" is taken)
        """
        # If the supplier already has a prefix, use it.
        if supplier.x_consignment_prefix:
            return supplier.x_consignment_prefix

        # --- If not, generate a new, unique one ---
        if not supplier.name:
            return "PARTNER" # Fallback

        parts = supplier.name.strip().split()
        prefix_base = ""

        if len(parts) >= 2:
            # "Tom Hoornaert" -> "TO" + "HO"
            fn = re.sub(r'[^A-Z0-9]', '', parts[0][:2].upper())
            ln_base = re.sub(r'[^A-Z0-9]', '', parts[-1].upper())

            # Try FN[:2] + LN[:2], then FN[:2] + LN[:3], etc.
            for i in range(2, len(ln_base) + 1):
                prefix_try = fn + ln_base[:i]
                if not prefix_try: continue # Skip if name was weird (e.g., "!!")

                # Check if this prefix is already used by *another* supplier
                if not self.env['res.partner'].search_count([('x_consignment_prefix', '=', prefix_try)]):
                    prefix_base = prefix_try
                    break

            # Fallback if all variations are taken (e.g., TOHO, TOHOO, TOHOOR, ...)
            if not prefix_base:
                prefix_base = fn + ln_base + str(supplier.id)

        elif len(parts) == 1 and parts[0]:
            # "IKEA" -> "IKEA"
            prefix_base = re.sub(r'[^A-Z0-9]', '', parts[0][:4].upper())

        if not prefix_base:
            prefix_base = "INV" # Invalid

        # Save the new prefix to the supplier
        supplier.write({'x_consignment_prefix': prefix_base})
        _logger.info(f"### Generated and saved new prefix '{prefix_base}' for supplier '{supplier.name}'")
        return prefix_base

    @api.model_create_multi
    def create(self, vals_list):
        _logger.info(f"### CREATE METHOD CALLED. Vals list: {vals_list}")

        for vals in vals_list:
            if not vals.get('name') or vals.get('name') == 'Nieuw':
                _logger.info(f"### Name is 'Nieuw' or empty. Generating new ID.")

                supplier_id = vals.get('supplier_id')
                if not supplier_id:
                    _logger.warning("### No supplier_id found in vals. Skipping ID generation.")
                    continue

                supplier = self.env['res.partner'].browse(supplier_id)
                prefix = self._get_or_create_supplier_prefix(supplier)
                _logger.info(f"### Using prefix: {prefix}")

                # --- Find next number FOR THIS PREFIX ---
                search_pattern = f"{prefix}_"
                existing_records = self.search(
                    [('name', '=like', f"{search_pattern}%")],
                    order='name DESC',
                    limit=1
                )

                new_number = 1
                if existing_records:
                    last_name = existing_records.name
                    last_number_str = last_name.split('_')[-1]
                    try:
                        new_number = int(last_number_str) + 1
                    except ValueError:
                        new_number = 1 # Fallback

                number_str = str(new_number).zfill(5) # e.g., "001"

                vals['name'] = f"{prefix}_{number_str}"
                _logger.info(f"### Final new name set in vals: {vals['name']}")

            else:
                _logger.warning(f"### SKIPPING ID generation. 'name' was already set to: {vals.get('name')}")

        result = super(ConsignmentSubmission, self).create(vals_list)

        _logger.info(f"### Super create finished. Resulting names: {result.mapped('name')}")
        return result

    # In submission.py, binnen de ConsignmentSubmission class

    def write(self, vals):
        removed_template_ids = []

        if 'product_ids' in vals:
            new_commands = []

            for command in vals['product_ids']:
                if command[0] == 2 and command[1]:
                    # 1. Onderschep de 'Delete' actie (commando 2)
                    removed_template_ids.append(command[1])

                    # 2. Vervang 'Delete' (2, ID, False) door 'Unlink' (3, ID, False)
                    # Dit zorgt ervoor dat Odoo alleen de link verbreekt,
                    # maar de product.template NIET probeert te verwijderen.
                    new_commands.append((3, command[1], False))
                else:
                    new_commands.append(command)

            if removed_template_ids:
                vals['product_ids'] = new_commands

        # 3. Voer de standaard Odoo write/update uit
        res = super(ConsignmentSubmission, self).write(vals)

        # 4. Archiveer de Product Templates
        if removed_template_ids:
            templates_to_archive = self.env['product.template'].browse(removed_template_ids)

            # Archiveer: zet de 'active' status op False
            templates_to_archive.write({'active': False})

            _logger.info(f"### Product Templates gearchiveerd (active=False): {removed_template_ids}")

        return res

