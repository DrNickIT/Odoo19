# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError
import base64
import csv
import io
import logging

_logger = logging.getLogger(__name__)

class ImportProductsWizard(models.TransientModel):
    _name = 'otters.consignment.import_products_wizard'
    _description = 'Wizard om producten te importeren in een inzending'

    file_data = fields.Binary(string="CSV-bestand", required=True)
    filename = fields.Char(string="Bestandsnaam")

    def import_products(self):
        """ Leest het CSV-bestand, creëert de producten en koppelt de kenmerken. """
        self.ensure_one()

        # 1. Haal de actieve inzending op
        submission_id = self.env.context.get('active_id')
        if not submission_id:
            raise UserError(_("Kan de actieve inzending niet vinden."))

        submission = self.env['otters.consignment.submission'].browse(submission_id)

        # 2. Controleer en Lees het CSV-bestand
        if not self.filename or not self.filename.lower().endswith('.csv'):
            raise UserError(_("Selecteer a.u.b. een .csv-bestand."))

        try:
            file_content = base64.b64decode(self.file_data).decode('utf-8')
            csv_data = csv.DictReader(io.StringIO(file_content))

            products_to_create = []

            for row in csv_data:
                # Kolomkoppen: 'name', 'price', 'category', 'attributes', 'condition_rating'
                name = row.get('name')
                price_str = row.get('price', '0.0')
                category_name = row.get('category')
                attributes_str = row.get('attributes')
                condition_rating_str = row.get('condition_rating', '0')

                if not name:
                    _logger.warning("Rij overgeslagen: geen 'name' gevonden.")
                    continue

                    # Conversie van Prijs
                try:
                    price = float(price_str)
                except ValueError:
                    raise UserError(_("Ongeldige prijs '%s' gevonden voor product '%s'.") % (price_str, name))

                    # --- Basis Product Waarden ---
                product_vals = {
                    'name': name,
                    'list_price': price,
                    'submission_id': submission.id,
                    'is_published': True,
                    # Correct voor voorraadtracking in een Storable Product
                    'type': 'consu',
                    'is_storable': True,
                    'qty_available': 1,
                    'condition_rating': condition_rating_str, # Veld voor de staat (1-5)
                }

                # --- Categorieën Verwerking ---
                if category_name:
                    category_name = category_name.strip()
                    category = self.env['product.public.category'].search([('name', '=ilike', category_name)], limit=1)
                    if not category:
                        category = self.env['product.public.category'].create({'name': category_name})

                    product_vals['public_categ_ids'] = [(6, 0, [category.id])]

                # --- Attributen (Kenmerken) Verwerking ---
                attribute_lines_commands = []
                if attributes_str:
                    attribute_pairs = [p.strip() for p in attributes_str.split(',') if p.strip()]

                    for pair in attribute_pairs:
                        if ':' not in pair:
                            _logger.warning(f"Ongeldige attribuutindeling voor product {name}: {pair}. Formaat moet zijn Naam:Waarde.")
                            continue

                        att_name, val_name = pair.split(':', 1)
                        att_name = att_name.strip()
                        val_name = val_name.strip()

                        # A. Zoek/Creëer het Attribuut (product.attribute)
                        attribute = self.env['product.attribute'].search([('name', '=ilike', att_name)], limit=1)
                        if not attribute:
                            # Kenmerk bestaat NIET: Maak een nieuwe aan en zet Variant Creation op NOOIT
                            attribute = self.env['product.attribute'].create({
                                'name': att_name,
                                'create_variant': 'no_variant'
                            })

                        # B. Zoek/Creëer de Attribuutwaarde (product.attribute.value)
                        value = self.env['product.attribute.value'].search([
                            ('attribute_id', '=', attribute.id),
                            ('name', '=ilike', val_name)
                        ], limit=1)
                        if not value:
                            # Waarde bestaat NIET: Maak een nieuwe waarde aan voor dit Kenmerk
                            value = self.env['product.attribute.value'].create({
                                'name': val_name,
                                'attribute_id': attribute.id,
                                'sequence': 10,
                            })

                        # C. Creëer de Commando voor de Attribuut Lijn
                        # Dit zorgt voor de gewenste "aparte lijnen" aanpak
                        attribute_lines_commands.append((0, 0, {
                            'attribute_id': attribute.id,
                            'value_ids': [(6, 0, [value.id])],
                        }))

                if attribute_lines_commands:
                    product_vals['attribute_line_ids'] = attribute_lines_commands

                products_to_create.append(product_vals)

            # 3. Creëer de producten in één batch
            if products_to_create:
                self.env['product.template'].create(products_to_create)

        except Exception as e:
            # Vang algemene fouten
            raise UserError(_("Fout bij het verwerken van het bestand: %s") % str(e))

        # 4. Sluit de wizard
        return {'type': 'ir.actions.act_window_close'}
