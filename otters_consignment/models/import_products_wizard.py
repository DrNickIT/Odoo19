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

    # Lijst met kolommen die GEEN attribuut mogen worden (omdat het basisvelden zijn)
    # Alles wat hier NIET in staat, wordt een Kenmerk (Attribuut)
    BASE_FIELDS = [
        'name', 'naam', 'titel',
        'price', 'prijs', 'verkoopprijs',
        'category', 'categorie', 'cat',
        'code', 'default_code', 'interne referentie', 'ref',
        'image_url', 'foto', 'afbeelding',
        'seo_title', 'meta title',
        'seo_description', 'meta description',
        'website_description', 'omschrijving', 'lange omschrijving',
        'merk', 'brand', # Merk behandelen we apart (want is Brand ID + Attribuut)
        'condition_number', 'conditie', 'staat' # Conditie behandelen we apart (mapping)
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
            # STAP 1: DECODING & INLEZEN (FOCUS HIEROP)
            # ---------------------------------------------------------------

            # A. Decodeer de binaire data
            raw_data = base64.b64decode(self.file_data)

            # B. Probeer UTF-8, val terug op Windows CP1252 (standaard Excel export)
            # Dit voorkomt crashes op speciale tekens zoals é, €, ë
            try:
                file_content = raw_data.decode('utf-8')
            except UnicodeDecodeError:
                file_content = raw_data.decode('cp1252')

            # C. Bepaal delimiter (puntkomma of komma)
            first_line = file_content.split('\n')[0]
            delimiter = ';' if first_line.count(';') > first_line.count(',') else ','

            # D. De CSV Reader instellen (DIT LOST HET ENTER PROBLEEM OP)
            # quotechar='"' -> Zorgt dat: "Tekst met \n enter" -> als 1 veld wordt gelezen
            f = io.StringIO(file_content)
            csv_data = csv.DictReader(f, delimiter=delimiter, quotechar='"')

            # E. Headers opschonen (BOM characters wegpoetsen)
            csv_data.fieldnames = [x.strip().replace('\ufeff', '') for x in (csv_data.fieldnames or [])]

            _logger.info(f"Import start. Delimiter: '{delimiter}'. Headers: {csv_data.fieldnames}")

            # ---------------------------------------------------------------
            # STAP 2: DE BESTAANDE LOGICA (ONGWIJZIGD)
            # ---------------------------------------------------------------

            products_to_create = []

            for row in csv_data:

                # A. Basis Velden
                name = self._get_csv_value(row, ['name', 'naam', 'titel'])
                if not name: continue # Sla lege regels over

                price_str = self._get_csv_value(row, ['price', 'prijs', 'verkoopprijs']).replace(',', '.') or '0.0'
                try: price = float(price_str)
                except ValueError: price = 0.0

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

                # C. Categorie Logica (Hierarchie)
                # Bv: "Kleding / Pull" -> Maakt Kleding (indien nodig) en Pull eronder
                cat_raw = self._get_csv_value(row, ['category', 'categorie'])
                if cat_raw:
                    category_id = self._find_or_create_category_hierarchy(cat_raw)
                    product_vals['public_categ_ids'] = [(6, 0, [category_id])]


                # D. Attributen Verzamelen
                attribute_lines = []

                # 1. Merk (Speciaal: moet ook Otters Brand zijn)
                merk_raw = self._get_csv_value(row, ['merk', 'brand'])
                if merk_raw:
                    brand = self._find_or_create_brand(merk_raw)
                    # OUDE FOUTE CODE:
                    # if not brand.active: brand.write({'active': True})

                    # NIEUWE CORRECTE CODE:
                    if not brand.is_published:
                        brand.write({'is_published': True})

                    product_vals['brand_id'] = brand.id
                    self._add_attribute_line(attribute_lines, 'Merk', merk_raw)

                # 2. Conditie (Speciaal: mapping van cijfer naar hartjes)
                conditie_raw = self._get_csv_value(row, ['condition_number', 'conditie', 'staat'])
                if conditie_raw:
                    # Kijk of het 3, 4, 5 is, anders neem de tekst letterlijk
                    val = self.CONDITION_MAPPING.get(conditie_raw, conditie_raw)
                    self._add_attribute_line(attribute_lines, 'Conditie', val)

                # 3. Dynamische Kolommen (Alles wat overblijft)
                # We lopen door de CSV headers heen.
                # Als een header NIET in de basislijst staat, maken we er een attribuut van.
                for header in row.keys():
                    if not header: continue
                    clean_header = header.strip()
                    val = row[header].strip()

                    if not val: continue # Lege waarde overslaan

                    # Als deze kolom al verwerkt is of basis is, skip hem
                    if clean_header.lower() in [x.lower() for x in self.BASE_FIELDS]:
                        continue

                    # Speciale check: Maat vs Schoenmaat
                    # Als de categorie 'Schoen' bevat, noemen we de attribuut 'Schoenmaat' ipv 'Maat'
                    attr_name = clean_header.capitalize() # Bv. "Geslacht", "Seizoen"

                    if attr_name.lower() in ['maat', 'size']:
                        if cat_raw and 'schoen' in cat_raw.lower():
                            attr_name = 'Schoenmaat'
                        else:
                            attr_name = 'Maat'

                    self._add_attribute_line(attribute_lines, attr_name, val)

                if attribute_lines:
                    product_vals['attribute_line_ids'] = attribute_lines

                products_to_create.append(product_vals)

            # E. Alles aanmaken
            if products_to_create:
                self.env['product.template'].create(products_to_create)

            # F. Nasorteren
            try:
                self.env['product.attribute'].search([]).action_sort_values()
                _logger.info("Import: Attributen gesorteerd.")
            except Exception as e:
                _logger.warning(f"Sorteerfout: {e}")

        except Exception as e:
            raise UserError(_("Fout bij importeren: %s") % str(e))

        return {'type': 'ir.actions.act_window_close'}


    # --- HULPFUNCTIES ---

    def _get_csv_value(self, row, key_variants):
        """ Zoekt een waarde in de rij, checkt verschillende schrijfwijzen van de header """
        for k in key_variants:
            # Check exacte match
            if k in row and row[k]: return row[k].strip()
            # Check case-insensitive match
            for header in row.keys():
                if header.lower() == k.lower() and row[header]:
                    return row[header].strip()
        return ''

    def _find_or_create_category_hierarchy(self, path_str):
        path_str = str(path_str).strip()
        if not path_str: return False

        # --- SCENARIO 1: ENKEL WOORD (bv. "kleedje") ---
        if '/' not in path_str:
            existing_cat = self.env['product.public.category'].search([
                ('name', '=ilike', path_str)
            ], limit=1)

            if existing_cat:
                return existing_cat.id

        # --- SCENARIO 2: PAD of NIEUWE CATEGORIE ---
        parts = [p.strip() for p in path_str.split('/') if p.strip()]
        parent_id = False
        last_cat = False

        for part in parts:
            # Zoek case-insensitive met de juiste parent
            cat = self.env['product.public.category'].search([
                ('name', '=ilike', part),
                ('parent_id', '=', parent_id)
            ], limit=1)

            if not cat:
                # NIET GEVONDEN -> AANMAKEN
                # We gebruiken .capitalize() zodat "broek" netjes "Broek" wordt
                cat = self.env['product.public.category'].create({
                    'name': part.capitalize(),
                    'parent_id': parent_id
                })
                # Koppel meteen het Type attribuut
                self._ensure_category_type_link(cat)

            parent_id = cat.id
            last_cat = cat

        return last_cat.id if last_cat else False

    def _ensure_category_type_link(self, category):
        """
        Zorgt dat voor categorie 'Broek' er ook een Attribuut Waarde 'Broek' bestaat
        in het attribuut 'Type', en koppelt deze.
        """
        type_attr = self.env['product.attribute'].search([('name', '=', 'Type')], limit=1)
        if not type_attr:
            type_attr = self.env['product.attribute'].create({'name': 'Type', 'display_type': 'pills'})

        # Zoek of waarde bestaat
        type_val = self.env['product.attribute.value'].search([
            ('attribute_id', '=', type_attr.id),
            ('name', '=', category.name)
        ], limit=1)

        if not type_val:
            type_val = self.env['product.attribute.value'].create({
                'attribute_id': type_attr.id,
                'name': category.name
            })

        # Koppel aan de categorie (voor de automatische sync later)
        if category.x_linked_type_value_id != type_val:
            category.write({'x_linked_type_value_id': type_val.id})

    def _find_or_create_brand(self, name):
        """ Zoekt of maakt Otters Brand """
        # We zoeken gewoon op naam (active_test is niet nodig als er geen active veld is)
        brand = self.env['otters.brand'].search([
            ('name', '=ilike', name)
        ], limit=1)

        if brand:
            # Als hij bestaat maar 'uit' staat (ongepubliceerd), zet hem aan!
            if not brand.is_published:
                brand.write({'is_published': True})
        else:
            # Bestaat niet? Maak aan en zet meteen gepubliceerd
            brand = self.env['otters.brand'].create({
                'name': name,
                'is_published': True
            })
        return brand

    def _add_attribute_line(self, lines_list, attr_name, val_string):
        if not val_string:
            return

        # 1. Split op | of , en schoonmaken
        values = [v.strip() for v in val_string.replace('|', ',').split(',') if v.strip()]

        # 2. Attribuut zoeken of aanmaken
        attribute = self.env['product.attribute'].search([('name', '=ilike', attr_name)], limit=1)
        if not attribute:
            attribute = self.env['product.attribute'].create({
                'name': attr_name,
                'create_variant': 'no_variant', # Belangrijk: geen varianten genereren
                'display_type': 'radio'
            })

        # 3. Alle waardes (Jongen, Meisje) zoeken of aanmaken
        val_ids = []
        for v in values:
            val_obj = self.env['product.attribute.value'].with_context(active_test=False).search([
                ('attribute_id', '=', attribute.id),
                ('name', '=ilike', v)
            ], limit=1)

            if not val_obj:
                val_obj = self.env['product.attribute.value'].create({
                    'attribute_id': attribute.id,
                    'name': v
                })
            elif not val_obj.active:
                val_obj.write({'active': True})

            val_ids.append(val_obj.id)

        # 4. CRUCIAAL: Voor elk gevonden ID een NIEUWE, APARTE lijn toevoegen
        # We checken NIET of de lijn al bestaat, want we willen juist dubbele lijnen (Jongen apart, Meisje apart).
        for val_id in val_ids:
            lines_list.append((0, 0, {
                'attribute_id': attribute.id,
                'value_ids': [(6, 0, [val_id])], # Let op de haakjes: [val_id]
            }))