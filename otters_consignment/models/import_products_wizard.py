# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError
import base64
import csv
import io
import logging
import re

_logger = logging.getLogger(__name__)

class ImportProductsWizard(models.TransientModel):
    _name = 'otters.consignment.import_products_wizard'
    _description = 'Wizard om producten te importeren (CSV van Marleen)'

    file_data = fields.Binary(string="CSV-bestand", required=True)
    filename = fields.Char(string="Bestandsnaam")

    # Mapping voor de conditie cijfers naar hartjes
    CONDITION_MAPPING = {
        '5': '❤️❤️❤️❤️❤️',
        '4': '❤️❤️❤️❤️🤍',
        '3': '❤️❤️❤️🤍🤍',
    }

    # Lijst met kolommen die GEEN attribuut mogen worden
    BASE_FIELDS = [
        'name', 'naam', 'titel',
        'price', 'prijs', 'verkoopprijs',
        'category', 'categorie', 'cat', 'type',
        'code', 'default_code', 'interne referentie', 'ref',
        'image_url', 'foto', 'afbeelding',
        'seo_title', 'meta title',
        'seo_description', 'meta description',
        'website_description', 'omschrijving', 'lange omschrijving',
        'merk', 'brand',
        'condition_number', 'conditie', 'staat'
    ]

    def import_products(self):
        self.ensure_one()
        submission_id = self.env.context.get('active_id')
        if not submission_id:
            raise UserError(_("Kan de actieve inzending niet vinden."))

        submission = self.env['otters.consignment.submission'].browse(submission_id)

        if not self.filename or not self.filename.lower().endswith('.csv'):
            raise UserError(_("Selecteer a.u.b. een .csv-bestand."))

        try:
            # ---------------------------------------------------------------
            # STAP 1: DECODING & INLEZEN
            # ---------------------------------------------------------------
            raw_data = base64.b64decode(self.file_data)
            try:
                file_content = raw_data.decode('utf-8')
            except UnicodeDecodeError:
                file_content = raw_data.decode('cp1252')

            first_line = file_content.split('\n')[0]
            delimiter = ';' if first_line.count(';') > first_line.count(',') else ','

            f = io.StringIO(file_content)
            csv_data = csv.DictReader(f, delimiter=delimiter, quotechar='"')
            # Headers opschonen (BOM verwijderen etc)
            csv_data.fieldnames = [x.strip().replace('\ufeff', '') for x in (csv_data.fieldnames or [])]

            _logger.info(f"Import start. Delimiter: '{delimiter}'. Headers: {csv_data.fieldnames}")

            # ---------------------------------------------------------------
            # STAP 2: DE LOGICA
            # ---------------------------------------------------------------

            products_to_create = []
            skipped_rows = []
            success_count = 0

            # We gebruiken enumerate om het rijnummer te weten (start op 2 want 1 is header)
            for i, row in enumerate(csv_data, start=2):

                # A. Basis Velden Check
                name = self._get_csv_value(row, ['name', 'naam', 'titel'])

                # UPDATE: Als naam ontbreekt, loggen we dit expliciet
                if not name:
                    skipped_rows.append(f"Rij {i}: Naam ontbreekt")
                    continue

                price_str = self._get_csv_value(row, ['price', 'prijs', 'verkoopprijs']).replace(',', '.') or '0.0'
                try:
                    price = float(price_str)
                except ValueError:
                    price = 0.0

                # UPDATE: Optioneel - als je ook wilt dat producten zonder prijs worden gemeld:
                # if price == 0.0:
                #    skipped_rows.append(f"Rij {i}: Prijs is 0 of ongeldig")
                #    continue

                default_code = self._get_csv_value(row, ['code', 'default_code', 'ref', 'DRO code'])

                # SEO & Omschrijvingen
                seo_title = self._get_csv_value(row, ['seo_title', 'meta title'])
                seo_desc = self._get_csv_value(row, ['seo_description', 'meta description'])
                web_desc_raw = self._get_csv_value(row, ['website_description', 'omschrijving'])
                web_desc = web_desc_raw.replace('\n', '<br/>') if web_desc_raw else ''

                # B. Maak de Product Dictionary
                product_vals = {
                    'name': name,
                    'list_price': price,
                    'submission_id': submission.id,
                    'is_published': True,
                    'type': 'consu',
                    'is_storable': True,
                    'qty_available': 1,
                    'default_code': default_code,
                    'website_meta_title': seo_title,
                    'website_meta_description': seo_desc,
                    'description_sale': web_desc,
                    'description_ecommerce': web_desc,
                }

                # C. Categorie Logica
                cat_raw = self._get_csv_value(row, ['category', 'categorie', 'type'])

                if cat_raw:
                    public_cat_ids = []
                    first_internal_cat_id = False

                    # Splits op | om meerdere categorieën te ondersteunen
                    for cat_part in cat_raw.split('|'):
                        cat_part = cat_part.strip()
                        if not cat_part: continue

                        category_id = self._find_or_create_category_hierarchy(cat_part)
                        if category_id:
                            public_cat_ids.append(category_id)

                            # Interne categorie (slechts eentje nodig voor de backend)
                            if not first_internal_cat_id:
                                public_cat = self.env['product.public.category'].browse(category_id)
                                internal_cat = self.env['product.category'].search([('name', '=', public_cat.name)], limit=1)
                                if not internal_cat:
                                    internal_cat = self.env['product.category'].create({'name': public_cat.name})
                                first_internal_cat_id = internal_cat.id

                    if public_cat_ids:
                        product_vals['public_categ_ids'] = [(6, 0, public_cat_ids)]
                    if first_internal_cat_id:
                        product_vals['categ_id'] = first_internal_cat_id

                # D. Attributen Verzamelen
                attribute_lines = []

                # 1. Merk
                merk_raw = self._get_csv_value(row, ['merk', 'brand'])
                if merk_raw:
                    brand = self._find_or_create_brand(merk_raw)
                    if not brand.is_published:
                        brand.write({'is_published': True})
                    product_vals['brand_id'] = brand.id
                    self._add_attribute_line(attribute_lines, 'Merk', merk_raw)

                # 2. Conditie
                conditie_raw = self._get_csv_value(row, ['condition_number', 'conditie', 'staat'])
                if conditie_raw:
                    val = self.CONDITION_MAPPING.get(conditie_raw, conditie_raw)
                    self._add_attribute_line(attribute_lines, 'Conditie', val)

                # 3. Dynamische Kolommen
                for header in row.keys():
                    if not header: continue
                    clean_header = header.strip()
                    val = row[header].strip()

                    if not val: continue
                    if clean_header.lower() in [x.lower() for x in self.BASE_FIELDS]:
                        continue

                    attr_name = clean_header.capitalize()

                    if attr_name.lower() in ['maat', 'size']:
                        if cat_raw and 'schoen' in cat_raw.lower():
                            attr_name = 'Schoenmaat'
                        else:
                            attr_name = 'Maat'

                    self._add_attribute_line(attribute_lines, attr_name, val)

                if attribute_lines:
                    product_vals['attribute_line_ids'] = attribute_lines

                products_to_create.append(product_vals)
                success_count += 1

            # E. Alles aanmaken
            if products_to_create:
                # 1. Maak de producten aan
                created_products = self.env['product.template'].create(products_to_create)

                # 2. Haal de standaard stock locatie op
                warehouse = self.env['stock.warehouse'].search([('company_id', '=', self.env.company.id)], limit=1)
                stock_location = warehouse.lot_stock_id

                if stock_location:
                    for product in created_products:
                        # Haal de variant op (nodig voor stock.quant)
                        variant = product.product_variant_id

                        if variant:
                            # 3. Maak de ECHTE voorraad aan (stock.quant)
                            self.env['stock.quant'].with_context(inventory_mode=True).create({
                                'product_id': variant.id,
                                'location_id': stock_location.id,
                                'inventory_quantity': 1.0,
                            }).action_apply_inventory()

                            # 4. CRUCIAAL: Roep handmatig de update functie aan
                            # Dit zet x_shop_available direct op True
                            product._update_shop_availability()

            # F. Nasorteren
            try:
                self.env['product.attribute'].search([]).action_sort_values()
            except Exception as e:
                _logger.warning(f"Sorteerfout: {e}")

        except Exception as e:
            raise UserError(_("Fout bij importeren: %s") % str(e))

        # --- NIEUW: Rapportage teruggeven ---
        msg = f"Succesvol geïmporteerd: {success_count} producten."
        msg_type = 'success'

        if skipped_rows:
            msg += f"\n\n⚠️ {len(skipped_rows)} regels overgeslagen:\n" + "\n".join(skipped_rows[:10])
            if len(skipped_rows) > 10:
                msg += "\n... (en meer)"
            msg_type = 'warning'

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Import Voltooid',
                'message': msg,
                'type': msg_type,
                'sticky': True if skipped_rows else False,
                'next': {'type': 'ir.actions.act_window_close'}
            }
        }

    # --- HULPFUNCTIES (Ongewijzigd) ---

    def _get_csv_value(self, row, key_variants):
        for k in key_variants:
            if k in row and row[k]: return row[k].strip()
            for header in row.keys():
                if header.lower() == k.lower() and row[header]:
                    return row[header].strip()
        return ''

    def _find_or_create_category_hierarchy(self, path_str):
        path_str = str(path_str).strip()
        if not path_str: return False

        if '/' not in path_str:
            existing_cat = self.env['product.public.category'].search([
                ('name', '=ilike', path_str)
            ], limit=1)
            if existing_cat: return existing_cat.id

        parts = [p.strip() for p in path_str.split('/') if p.strip()]
        parent_id = False
        last_cat = False

        for part in parts:
            cat = self.env['product.public.category'].search([
                ('name', '=ilike', part),
                ('parent_id', '=', parent_id)
            ], limit=1)

            if not cat:
                cat = self.env['product.public.category'].create({
                    'name': part.capitalize(),
                    'parent_id': parent_id
                })
                # Zorg dat de koppeling met Type ook gelegd wordt!
                self._ensure_category_type_link(cat)

            parent_id = cat.id
            last_cat = cat

        return last_cat.id if last_cat else False

    def _ensure_category_type_link(self, category):
        """ Zorgt dat de categorie gekoppeld is aan een Type waarde """
        type_attr = self.env['product.attribute'].search([('name', '=', 'Type')], limit=1)
        if not type_attr:
            type_attr = self.env['product.attribute'].create({'name': 'Type', 'display_type': 'radio'})

        type_val = self.env['product.attribute.value'].search([
            ('attribute_id', '=', type_attr.id),
            ('name', '=ilike', category.name)
        ], limit=1)

        if not type_val:
            type_val = self.env['product.attribute.value'].create({
                'attribute_id': type_attr.id,
                'name': category.name
            })

        if category.x_linked_type_value_id != type_val:
            category.write({'x_linked_type_value_id': type_val.id})

    def _find_or_create_brand(self, name):
        brand = self.env['otters.brand'].search([('name', '=ilike', name)], limit=1)
        if brand:
            if not brand.is_published:
                brand.write({'is_published': True})
        else:
            brand = self.env['otters.brand'].create({'name': name, 'is_published': True})
        return brand

    def _add_attribute_line(self, lines_list, attr_name, val_string):
        if not val_string: return
        values = [v.strip() for v in val_string.replace('|', ',').split(',') if v.strip()]
        attribute = self.env['product.attribute'].search([('name', '=ilike', attr_name)], limit=1)
        if not attribute:
            attribute = self.env['product.attribute'].create({
                'name': attr_name.capitalize(), # Forceer hoofdletter bij nieuw kenmerk
                'create_variant': 'no_variant',
                'display_type': 'radio'
            })

        val_ids = []
        for v in values:
            val_obj = self.env['product.attribute.value'].with_context(active_test=False).search([
                ('attribute_id', '=', attribute.id),
                ('name', '=ilike', v)
            ], limit=1)

            if not val_obj:
                val_obj = self.env['product.attribute.value'].create({
                    'attribute_id': attribute.id,
                    'name': v.capitalize()  # <--- HIER: Forceer hoofdletter bij nieuwe waarde!
                })
            elif not val_obj.active:
                val_obj.write({'active': True})

            val_ids.append(val_obj.id)

        for val_id in val_ids:
            lines_list.append((0, 0, {
                'attribute_id': attribute.id,
                'value_ids': [(6, 0, [val_id])],
            }))