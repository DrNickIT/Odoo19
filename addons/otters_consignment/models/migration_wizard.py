# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError
from urllib.parse import urlparse, parse_qs
import base64
import csv
import io
import logging
import requests
import time
import re
import os

_logger = logging.getLogger(__name__)


class MigrationWizard(models.TransientModel):
    _name = 'otters.migration.wizard'
    _description = 'Master Migratie Tool'
    migration_partner_id = fields.Many2one('res.partner', string="Fictieve Migratie Klant")
    migration_submission_id = fields.Many2one('otters.consignment.submission', string="Fictieve Migratie Inzending")

    # --- 1. Bestanden ---
    file_customers = fields.Binary(string="1. Klanten (otters_klanten.csv)", required=False)
    filename_customers = fields.Char()

    file_submissions = fields.Binary(string="2. Verzendzakken (otters_verzendzak.csv)", required=False)
    filename_submissions = fields.Char()

    file_brands = fields.Binary(string="3. Merken (otters_merken.csv)", required=False)
    filename_brands = fields.Char()

    file_products = fields.Binary(string="4. Producten (otters_producten.csv)", required=False)
    filename_products = fields.Char()

    file_giftcards = fields.Binary(string="5. Cadeaubonnen (otters_bonnen.csv)", required=False)
    filename_giftcards = fields.Char()

    file_actioncodes = fields.Binary(string="6. Actiecodes (otters_actiecodes.csv)", required=False)
    filename_actioncodes = fields.Char()

    # NIEUW VELD: Lokaal pad
    image_base_path = fields.Char(
        string="Lokaal Pad naar Foto's (Server)",
        help="Bv. /mnt/images_source. Als dit is ingevuld, zoekt het script de foto's hier in plaats van te downloaden."
    )

    old_site_url = fields.Char(string="Oude Website URL", default="https://www.ottersenflamingos.be")

    def _clean_id(self, value):
        if not value: return False
        try:
            cleaned = str(int(float(str(value).replace(',', '.'))))
            return cleaned
        except:
            return str(value).strip()

    def _update_stock(self, product_tmpl, qty):
        try:
            product_variant = product_tmpl.product_variant_id
            if not product_variant: return
            warehouse = self.env['stock.warehouse'].search([], limit=1)
            location = warehouse.lot_stock_id
            if not location: return
            self.env['stock.quant'].with_context(inventory_mode=True).create({
                'product_id': product_variant.id,
                'location_id': location.id,
                'inventory_quantity': float(qty),
            }).action_apply_inventory()
        except Exception as e:
            pass

    def start_migration(self):
        """
        MASTER FUNCTIE: Draait de volledige import ÉN alle fixes erachteraan.
        """
        # 1. Veiligheidscheck
        if not self.file_customers and not self.file_products:
            raise UserError("Upload minstens de basisbestanden (klanten/producten) om te starten!")

        _logger.info("==========================================")
        _logger.info("🚀 START TOTALE PRODUCTIE MIGRATIE")
        _logger.info("==========================================")

        # --- FASE 1: DE IMPORT (Bestaande logica) ---

        # 1. Klanten
        partner_map = {}
        if self.file_customers:
            partner_map = self._process_customers()
            self.env.cr.commit()  # Tussentijds opslaan

        # 2. Verzendzakken
        submission_map = {}
        if self.file_submissions:
            submission_map = self._process_submissions(partner_map)
            self.env.cr.commit()

        # 3. Merken
        brand_map = {}
        if self.file_brands:
            brand_map = self._process_brands()
            self.env.cr.commit()

        # NIEUWE STAP: Aanmaken van de Fictieve Migratie Records
        _logger.info(">>> Stap 3d: Fictieve Migratie Records aanmaken...")
        self._create_migration_records()
        self.env.cr.commit()
        _logger.info("✅ Stap 3d Klaar: Fictieve klant en zakken aangemaakt.")

        # 4. Producten (Hier zit nu de nieuwe geïntegreerde logica)
        if self.file_products:
            _logger.info(">>> Stap 4: Producten en Fictieve Orders verwerken...")
            count = self._process_products_new_logic(submission_map, brand_map)
            self.env.cr.commit()

        if self.file_giftcards:
            self._process_giftcards()

        if self.file_actioncodes:
            self._process_actioncodes()
            self.env.cr.commit()

        # --- FASE 2: DE AUTOMATISCHE FIXES (Jouw nieuwe functies) ---

        _logger.info("==========================================")
        _logger.info("🏁 MIGRATIE SUCCESVOL AFGEROND!")
        _logger.info("==========================================")

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Migratie Voltooid',
                'message': 'Alles is geïmporteerd, bevestigd, opgeruimd en financieel bijgewerkt.',
                'type': 'success',
                'sticky': True
            }
        }

    def _read_csv(self, binary_data):
        if not binary_data: return []
        try:
            file_content = base64.b64decode(binary_data).decode('utf-8')
        except UnicodeDecodeError:
            file_content = base64.b64decode(binary_data).decode('latin-1')
        first_line = file_content.split('\n')[0]
        delimiter = ';' if ';' in first_line else ','
        return csv.DictReader(io.StringIO(file_content), delimiter=delimiter)

    def _process_customers(self):
        csv_data = self._read_csv(self.file_customers)
        mapping = {}
        count = 0
        for row in csv_data:
            # Logging heartbeat elke 100 klanten
            count += 1
            if count % 100 == 0:
                _logger.info(f"   ... {count} klanten verwerkt")

            old_id = self._clean_id(row.get('klant_id'))
            email = row.get('username')
            if not old_id or not email: continue

            domain = ['|', ('email', '=ilike', email.strip()), ('x_old_id', '=', str(old_id))]
            partner = self.env['res.partner'].search(domain, limit=1)

            straat = f"{row.get('straat', '')} {row.get('huisnr', '')}".strip()
            bus = row.get('bus')
            if bus and str(bus) != 'nan':
                straat2 = f"Bus {bus}"
            else:
                straat2 = False

            if not partner:
                full_name = f"{row.get('voornaam', '')} {row.get('achternaam', '')}".strip() or email
                partner = self.env['res.partner'].create({
                    'name': full_name, 'email': email,
                    'street': straat,
                    'street2': straat2,
                    'zip': row.get('postcode', ''), 'city': row.get('gemeente', ''),
                    'x_old_id': str(old_id)
                })
            else:
                vals = {}
                if not partner.x_old_id: vals['x_old_id'] = str(old_id)
                if partner.x_consignment_prefix and partner.x_consignment_prefix.startswith('IMP'):
                    vals['x_consignment_prefix'] = False
                if vals: partner.write(vals)

            iban = row.get('rekeningnummer')
            if not iban or str(iban) == 'nan' or not str(iban).strip():
                iban = row.get('rekeningnummer2')

            if iban and str(iban) != 'nan' and str(iban).strip() != '':
                clean_iban = str(iban).replace(' ', '').strip()
                existing_bank = self.env['res.partner.bank'].search([
                    ('acc_number', '=', clean_iban),
                    ('partner_id', '=', partner.id)
                ], limit=1)
                if not existing_bank:
                    try:
                        self.env['res.partner.bank'].create({
                            'acc_number': clean_iban,
                            'partner_id': partner.id
                        })
                    except Exception as e:
                        pass

            mapping[old_id] = partner
        return mapping

    def _process_submissions(self, customer_map):
        csv_data = self._read_csv(self.file_submissions)
        mapping = {}

        def parse_legacy_date(d_str):
            if not d_str: return False
            s = str(d_str).strip()
            if s in ['0000-00-00', 'nan', '', 'False', 'None']:
                return False
            try:
                # Test of het een geldige datum is voor Odoo
                fields.Date.from_string(s)
                return s
            except ValueError:
                return False

        for row in csv_data:
            # ... (bestaande checks voor id en customer) ...
            old_bag_id = self._clean_id(row.get('zak_id'))
            old_customer_id = self._clean_id(row.get('KlantId'))
            if not old_bag_id or not old_customer_id: continue

            partner = customer_map.get(old_customer_id)
            if not partner: continue

            submission = self.env['otters.consignment.submission'].search([('x_old_id', '=', str(old_bag_id))], limit=1)

            schenking_raw = str(row.get('schenking', '')).lower()
            if 'goed doel' in schenking_raw:
                action_val = 'donate'
            elif 'terug' in schenking_raw:
                action_val = 'return'
            else:
                action_val = 'donate'

            if not submission:
                # === DATUM LOGICA (JOUW REGELS) ===

                # 1. Haal ruwe datums op
                raw_sent = parse_legacy_date(row.get('datum_verzonden'))
                raw_received = parse_legacy_date(row.get('datum_ontvangen'))

                final_date_received = False   # Voor veld submission_date (Inzending Datum)
                final_date_published = False  # Voor veld date_published (Online Datum)

                # SCENARIO 1: Beide datums zijn bekend
                if raw_sent and raw_received:
                    final_date_received = raw_sent      # "datum_verzonden -> submission_date"
                    final_date_published = raw_received # "datum_ontvangen -> date_published"

                # SCENARIO 2: Alleen datum_verzonden is bekend
                elif raw_sent and not raw_received:
                    final_date_received = raw_sent
                    final_date_published = raw_sent     # "zet dan in beide velden datum_verzonden"

                # SCENARIO 3: Alleen datum_ontvangen is bekend
                elif not raw_sent and raw_received:
                    final_date_received = raw_received  # "zet dan in beide velden datum_ontvangen"
                    final_date_published = raw_received

                # SCENARIO 4: Geen van beide is bekend (FALLBACK OP JAAR CODE)
                else:
                    code_str = str(row.get('code', '')).strip()
                    fallback_year = fields.Date.today().year # Safety net

                    # Probeer jaar uit code te halen (bv. 20210337 -> 2021)
                    # We zoeken naar de eerste 4 cijfers
                    if len(code_str) >= 4 and code_str[:4].isdigit():
                        fallback_year = int(code_str[:4])

                    # Zet beide op 1 juli van dat jaar
                    fallback_date = f"{fallback_year}-07-01"

                    final_date_received = fallback_date
                    final_date_published = fallback_date

                    _logger.info(f"   [DATUM FIX] Zak {old_bag_id}: Geen datums gevonden. Teruggevallen op {fallback_date} (Code: {code_str})")

                # ... (Partner IBAN ophalen) ...
                partner_iban = partner.bank_ids[:1].acc_number if partner.bank_ids else False

                submission = self.env['otters.consignment.submission'].with_context(skip_sendcloud=True).create({
                    'name': 'Nieuw',
                    'supplier_id': partner.id,
                    'submission_date': final_date_received,  # De berekende ontvangstdatum
                    'date_published': final_date_published,  # De berekende online datum
                    'state': 'online',
                    'payout_method': 'coupon',
                    'payout_percentage': 0.5,
                    'x_old_id': str(old_bag_id),
                    'x_legacy_code': row.get('code'),
                    'action_unaccepted': action_val,
                    'action_unsold': action_val,
                    'agreed_to_terms': True,
                    'agreed_to_clothing_terms': True,
                    'agreed_to_shipping_fee': True,
                    'x_iban': partner_iban,
                })

                notities = row.get('notities')
                if notities and str(notities) != 'nan' and str(notities).strip() != '':
                    self.env['otters.consignment.rejected.line'].create({
                        'submission_id': submission.id,
                        'product_name': 'Notitie uit migratie',
                        'reason': 'other',
                        'note': notities
                    })

                oude_code = row.get('code')
                if oude_code:
                    submission.message_post(body=f"<b>Oude Code:</b> {oude_code}")

            mapping[old_bag_id] = submission
        return mapping

    def _process_brands(self):
        if not self.file_brands: return {}
        csv_data = self._read_csv(self.file_brands)
        brand_map = {}

        # Attribuut zoeken/maken
        brand_attribute = self.env['product.attribute'].search([('name', '=', 'Merk')], limit=1)
        if not brand_attribute:
            brand_attribute = self.env['product.attribute'].create(
                {'name': 'Merk', 'create_variant': 'no_variant', 'display_type': 'pills'})

        count = 0
        skipped_images = 0

        _logger.info("--- START MERKEN IMPORT ---")

        for row in csv_data:
            if count > 0 and count % 50 == 0:
                self.env.cr.commit()

            old_merk_id = self._clean_id(row.get('merk_id'))
            name = row.get('naam')
            if not old_merk_id or not name: continue

            # 1. ZOEK HET MERK
            brand = self.env['otters.brand'].search([('name', '=', name)], limit=1)

            # 2. BASIS DATA
            brand_vals = {
                'name': name,
                'description': row.get('omschrijving_nl'),
                'is_published': True,
                'website_meta_title': row.get('seo_titel'),
                'website_meta_description': row.get('seo_description'),
                'website_meta_keywords': row.get('seo_keywords'),
            }

            # 3. FOTO LOGICA (MET CACHING)
            logo_url = row.get('foto')
            img_data = False
            should_download = False

            if not brand:
                should_download = True
            elif not brand.logo:
                should_download = True
            else:
                should_download = False
                skipped_images += 1

            if should_download and logo_url and str(logo_url) != 'nan':
                img_data = self._download_image(logo_url, fix_old_id=f"MERK_{old_merk_id}")

                if img_data:
                    brand_vals['logo'] = img_data

            # 4. MAAK AAN OF UPDATE
            if not brand:
                brand = self.env['otters.brand'].create(brand_vals)
            else:
                brand.write(brand_vals)

            # 5. ATTRIBUUT WAARDE
            brand_val = self.env['product.attribute.value'].search(
                [('attribute_id', '=', brand_attribute.id), ('name', '=', name)], limit=1)
            if not brand_val:
                brand_val = self.env['product.attribute.value'].create(
                    {'name': name, 'attribute_id': brand_attribute.id})

            brand_map[old_merk_id] = {
                'brand_id': brand.id,
                'attr_val_id': brand_val.id,
                'attr_id': brand_attribute.id
            }
            count += 1

        _logger.info(
            f"--- MERKEN KLAAR: {count} verwerkt. {skipped_images} keer foto-download overgeslagen (bestond al). ---")
        return brand_map

    def _process_products_new_logic(self, submission_map, brand_map):
        csv_data = self._read_csv(self.file_products)
        count = 0

        # --- CACHE OPBOUWEN ---
        _logger.info("--- CACHE OPBOUWEN... ---")
        existing_recs = self.env['product.template'].search_read(
            ['|', ('x_old_id', '!=', False), ('default_code', '!=', False)],
            ['id', 'x_old_id', 'default_code']
        )
        existing_by_old_id = {str(r['x_old_id']): r['id'] for r in existing_recs if r['x_old_id']}
        existing_by_code = {r['default_code']: r['id'] for r in existing_recs if r['default_code']}
        _logger.info(f"--- CACHE KLAAR: {len(existing_recs)} producten. ---")

        # Mappings
        condition_mapping = {
            '5 hartjes': '❤️❤️❤️❤️❤️', '4 hartjes': '❤️❤️❤️❤️🤍',
            '3 hartjes': '❤️❤️❤️🤍🤍'
        }
        # Accessoires types
        accessoires_types = ['muts & sjaal', 'hoedjes & petjes', 'tutjes', 'accessoires', 'speelgoed', 'riem',
                             'haarband', 'rugzakken en tassen', 'slab', 'speenkoord', 'badcape', 'dekentje']

        partner_id = self.migration_partner_id
        q4_cutoff_date = self._parse_date('2025-09-30')
        FALLBACK_DATE_PAID = self._parse_date('2022-08-31')

        _logger.info("--- START PRODUCTEN/ORDER MIGRATIE ---")

        for row in csv_data:
            count += 1
            if count % 100 == 0:
                self.env.cr.commit()
                _logger.info(f"   [PRODUCTEN] {count} verwerkt... (Huidige: {row.get('naam')})")

            # --- A. DATA EN STATUS PARSEN ---
            old_product_id = self._clean_id(row.get('product_id'))
            zak_id_product = self._clean_id(row.get('zak_id'))
            name = row.get('naam')

            if 'kadobon' in name.lower() or 'cadeaubon' in name.lower() or 'giftcard' in name.lower():
                _logger.info(f"   [SKIP] Product {old_product_id} overgeslagen (Gedefinieerd als Kadobon).")
                continue

            default_code = row.get('code')

            if not zak_id_product: continue
            submission = submission_map.get(zak_id_product)
            if not submission: continue

            # Vlaggen & Waarden
            uitbetaald_raw = str(row.get('uitbetaald', '')).lower()
            verkocht_raw = str(row.get('verkocht', '')).lower()
            niet_weergeven_raw = str(row.get('product_niet_weergeven', '')).lower()
            status_image_raw = str(row.get('status_image', '')).lower()  # Of 'status_afbeelding', check je CSV header!
            waarom_weg = row.get('waarom_niet_weergeven', '')  # HERSTELD: Tekstreden

            is_paid_raw = (uitbetaald_raw == 'ja')
            is_sold_raw = (verkocht_raw == 'ja')
            is_hidden_raw = (niet_weergeven_raw == 'ja')
            is_definitief_niet_actief = ('nietactief.png' in status_image_raw)

            # Datums
            datum_uitbetaald_str = str(row.get('datum_uitbetaald', '')).strip()
            datum_verkocht_str = str(row.get('datum_verkocht', '')).strip()
            has_payout_date = not self._is_empty_date(datum_uitbetaald_str)
            has_sale_date = not self._is_empty_date(datum_verkocht_str)

            # Stock
            try:
                stock_val = float(str(row.get('stock') or '0').replace(',', '.'))
            except:
                stock_val = 0.0

            # --- B. PRODUCT ZOEKEN ---
            product_id = False
            if old_product_id and str(old_product_id) in existing_by_old_id:
                product_id = existing_by_old_id[str(old_product_id)]
            elif default_code and default_code in existing_by_code:
                product_id = existing_by_code[default_code]

            product = self.env['product.template'].browse(product_id) if product_id else False

            # --- C. COMMISSIE LOGICA (HERSTELD) ---
            # Dit stukje zorgt dat de inzending geüpdatet wordt als er 'cash' of 'coupon' staat
            commissie_raw = row.get('commissie')
            if commissie_raw:
                try:
                    comm_val = int(float(str(commissie_raw).replace(',', '.')))
                    method = False;
                    percentage = 0.0
                    if comm_val == 30:
                        method = 'cash'; percentage = 0.30
                    elif comm_val == 50:
                        method = 'coupon'; percentage = 0.50

                    if method:
                        if submission.payout_method != method:
                            submission.write({'payout_method': method, 'payout_percentage': percentage})
                        partner = submission.supplier_id
                        if partner.x_payout_method != method:
                            partner.write({
                                'x_payout_method': method,
                                'x_cash_payout_percentage': 0.3 if method == 'cash' else 0.0,
                                'x_coupon_payout_percentage': 0.5 if method == 'coupon' else 0.0
                            })
                except Exception:
                    pass

            # --- D. CATEGORIE & MERK & DATA (HERSTELD) ---
            # 1. Categorie
            type_raw = str(row.get('type', '')).strip()
            type_lower = type_raw.lower()
            maat_raw = str(row.get('maat', '')).strip()
            target_cat_name = 'Kleding';
            target_sub_name = type_raw.capitalize()

            if type_lower in accessoires_types:
                target_cat_name = 'Accessoires'
            elif 'kousen' in type_lower or 'sokken' in type_lower:
                target_cat_name = 'Schoenen & Kousen'; target_sub_name = 'Kousen'
            elif any(x in type_lower for x in ['schoen', 'laars', 'sneaker', 'sandaal']):
                target_cat_name = 'Schoenen & Kousen'; target_sub_name = 'Schoenen'  # Pantoffel fix zit hierin

            # Maat fix
            if maat_raw:
                try:
                    clean_maat = re.match(r"(\d+)", maat_raw)
                    if clean_maat and int(clean_maat.group(1)) < 44 and target_cat_name not in ['Accessoires',
                                                                                                 'Schoenen & Kousen']:
                        target_cat_name = 'Schoenen & Kousen';
                        target_sub_name = 'Schoenen'
                except:
                    pass

            # Categorieën aanmaken
            main_cat = self.env['product.public.category'].search(
                [('name', '=', target_cat_name), ('parent_id', '=', False)], limit=1)
            if not main_cat: main_cat = self.env['product.public.category'].create({'name': target_cat_name})
            final_categ_ids = [main_cat.id]
            if target_sub_name:
                sub_cat = self.env['product.public.category'].search(
                    [('name', '=', target_sub_name), ('parent_id', '=', main_cat.id)], limit=1)
                if not sub_cat: sub_cat = self.env['product.public.category'].create(
                    {'name': target_sub_name, 'parent_id': main_cat.id})
                final_categ_ids.append(sub_cat.id)

            int_main = self.env['product.category'].search([('name', '=', target_cat_name), ('parent_id', '=', False)],
                                                           limit=1)
            if not int_main: int_main = self.env['product.category'].create({'name': target_cat_name})
            final_int_id = int_main.id
            if target_sub_name:
                int_sub = self.env['product.category'].search(
                    [('name', '=', target_sub_name), ('parent_id', '=', int_main.id)], limit=1)
                if not int_sub: int_sub = self.env['product.category'].create(
                    {'name': target_sub_name, 'parent_id': int_main.id})
                final_int_id = int_sub.id

            # Merk
            old_merk_id = self._clean_id(row.get('merk_id'))
            brand_data = None
            if old_merk_id and old_merk_id in brand_map: brand_data = brand_map[old_merk_id]

            # Product Values
            product_vals = {
                'name': name, 'submission_id': submission.id, 'type': 'consu', 'is_storable': True,
                'default_code': default_code, 'x_old_id': str(old_product_id),
                'description_ecommerce': row.get('lange_omschrijving'),
                'description_sale': row.get('korte_omschrijving_nl'),
                'website_meta_title': row.get('seo_titel'), 'website_meta_description': row.get('seo_description'),
                'website_meta_keywords': row.get('seo_keywords'),
                'public_categ_ids': [(6, 0, final_categ_ids)], 'categ_id': final_int_id,
                'brand_id': brand_data['brand_id'] if brand_data else False
            }

            # --- E. PRODUCT AANMAAK / UPDATE ---
            if product:
                product.write(product_vals)
                # Attributen & Foto's bijwerken
                if brand_data: self._add_attribute_by_id(product, brand_data['attr_id'], brand_data['attr_val_id'])
                if not product.product_template_image_ids and not product.image_1920:
                    extra_fotos = row.get('extra_fotos')
                    if extra_fotos and str(extra_fotos) != 'nan':
                        for idx, url in enumerate(extra_fotos.split(',')):
                            if url:
                                extra_img = self._download_image(url.strip(), fix_old_id=old_product_id)
                                if extra_img: self.env['product.image'].create(
                                    {'product_tmpl_id': product.id, 'name': f"{name} - Extra {idx + 1}",
                                     'image_1920': extra_img})
            else:
                image_url = row.get('foto')
                product_vals['image_1920'] = self._download_image(image_url, fix_old_id=old_product_id)
                try:
                    product_vals['list_price'] = float(str(row.get('prijs') or '0').replace(',', '.'))
                except:
                    product_vals['list_price'] = 0.0

                product = self.env['product.template'].create(product_vals)
                if old_product_id: existing_by_old_id[str(old_product_id)] = product.id

                # Attributen
                if maat_raw: self._add_attribute(product,
                                                 'Schoenmaat' if target_cat_name == 'Schoenen & Kousen' else 'Maat',
                                                 maat_raw)
                if row.get('merk'): self._add_attribute(product, 'Merk', row.get('merk'))
                if row.get('seizoen'): self._add_attribute(product, 'Seizoen', row.get('seizoen'))
                if row.get('categorie'): self._add_attribute(product, 'Geslacht', row.get('categorie'))
                if row.get('type'): self._add_attribute(product, 'Type', row.get('type'))
                if row.get('staat') in condition_mapping: self._add_attribute(product, 'Conditie',
                                                                              condition_mapping[row.get('staat')])
                if brand_data: self._add_attribute_by_id(product, brand_data['attr_id'], brand_data['attr_val_id'])
                extra_fotos = row.get('extra_fotos')
                if extra_fotos and str(extra_fotos) != 'nan':
                    for idx, url in enumerate(extra_fotos.split(',')):
                        if url:
                            extra_img = self._download_image(url.strip(), fix_old_id=old_product_id)
                            if extra_img: self.env['product.image'].create(
                                {'product_tmpl_id': product.id, 'name': f"{name} - Extra {idx + 1}",
                                 'image_1920': extra_img})

            # --- F. STATUS & ORDER REGELS (DE 12 SCENARIO'S) ---

            # --------------------------------------------------------------------------------
            # REGEL 0: Absolute vlag 'Niet Actief'
            # --------------------------------------------------------------------------------
            if is_definitief_niet_actief:
                _logger.info(f"   [DEF. NIET ACTIEF] Product {old_product_id}. Markeren als Unsold.")
                self._set_unsold_migration(product, stock_val, reason_text="Afbeelding 'nietactief.png'")
                continue

            # --------------------------------------------------------------------------------
            # BLOK 1: UITBETAALD = JA (VERRUIMDE CHECK)
            # --------------------------------------------------------------------------------
            elif is_paid_raw:
                payout_date = self._parse_date(datum_uitbetaald_str)
                sale_date = self._parse_date(datum_verkocht_str)

                # --- BEPALEN DATUMS VOOR ACTIE ---
                if has_payout_date:
                    # Regels 1-6 (Datum Uitbetaald is leidend of Verkoopdatum indien aanwezig)
                    order_date = sale_date if has_sale_date else payout_date
                    payout_date_final = payout_date
                else:
                    # Hier valt jouw eerdere voorbeeld in: Betaald=Ja, maar Datum Uitbetaald mist.
                    if has_sale_date:
                        # De verkoopdatum wordt zowel de orderdatum als de (fictieve) uitbetaaldatum.
                        order_date = sale_date
                        payout_date_final = sale_date
                        _logger.info(f"   [FIX DATUM] Product {old_product_id}: Uitbetaald=Ja zonder datum. Gebruikt Verkoopdatum {order_date} als Payout Datum.")
                    else:
                        # NIEUWE FALLBACK REGEL: Beide datums ontbreken, gebruik 31/08/2022
                        order_date = FALLBACK_DATE_PAID
                        payout_date_final = FALLBACK_DATE_PAID
                        _logger.warning(f"   [FALLBACK DATE] Product {old_product_id}: Betaald=Ja, maar GEEN verkoop- of uitbetaaldatum. Gebruikt fallback datum {FALLBACK_DATE_PAID}.")

                    if not order_date: # Safety check voor het geval FALLBACK_DATE_PAID False is (bv niet geparset)
                        self._set_unsold_migration(product, stock_val, reason_text="MIGRATIE FOUT: Betaald=Ja maar geen geldige datum.")
                        continue
                        # ---------------------------------

                # Veiligheidscheck (Kwartaal 4)
                if order_date and order_date > q4_cutoff_date:
                    _logger.warning(f"   [CHECK] Product {old_product_id} is Betaald MAAR datum {order_date} > cutoff. Dit is inconsistent. Verwerkt als UITBETAALD.")

                # Regels 1 & 2: Verkocht = Ja
                if is_sold_raw:
                    _logger.info(f"   [R 1/2] Betaald=Ja, Verkocht=Ja. Order maken.")
                    self._create_fictive_order(product, order_date, partner_id, is_paid=True, payout_date=payout_date_final)

                # Regels 3 & 4: Verkocht=Nee & (Niet Verbergen=Nee & Stock>0)
                elif not is_sold_raw and not is_hidden_raw and stock_val > 0:
                    _logger.info(f"   [R 3/4] Betaald=Ja, Kopie nodig. Order maken op origineel.")
                    self._create_fictive_order(product, order_date, partner_id, is_paid=True, payout_date=payout_date_final)
                    self._create_product_copy(product, stock_val)

                # Regels 5 & 6: Verkocht=Nee & (Verbergen=Ja of Stock<=0)
                elif not is_sold_raw and (is_hidden_raw or stock_val <= 0):
                    _logger.info(f"   [R 5/6] Betaald=Ja, Verbergen/Stock=0. Order maken.")
                    self._create_fictive_order(product, order_date, partner_id, is_paid=True, payout_date=payout_date_final)

            # --------------------------------------------------------------------------------
            # BLOK 2: UITBETAALD = NEE
            # --------------------------------------------------------------------------------
            elif not is_paid_raw:

                # REGEL 7: Verkocht=Ja & Datum>Cutoff
                if is_sold_raw and has_sale_date:
                    sale_date = self._parse_date(datum_verkocht_str)
                    if sale_date and sale_date > q4_cutoff_date:
                        _logger.info(f"   [R 7] Betaald=Nee, Verkocht=Ja, Datum={sale_date} > Cutoff. Order maken (Niet Betaald).")
                        self._create_fictive_order(product, sale_date, partner_id, is_paid=False, payout_date=False)

                    # REGEL 8: Verkocht=Ja & Datum<=Cutoff & Zak=20250012 (Speciale zak)
                    elif sale_date and sale_date <= q4_cutoff_date and submission.x_legacy_code == '20250012':
                        _logger.info(f"   [R 8] Betaald=Nee, Verkocht=Ja, Zak=20250012. Order maken (Niet Betaald).")
                        self._create_fictive_order(product, sale_date, partner_id, is_paid=False, payout_date=False)

                    # REGEL 9: Verkocht=Ja & Datum<=Cutoff & Zak != 20250012 (Onverkocht -> Unsold)
                    elif sale_date and sale_date <= q4_cutoff_date and submission.x_legacy_code != '20250012':
                        _logger.info(f"   [R 9] Betaald=Nee, Verkocht=Ja, Datum<=Cutoff, Zak!=20250012. Wordt Unsold (Inconsistentie).")
                        self._set_unsold_migration(product, stock_val, reason_text=waarom_weg or "MIGRATIE: Verkocht maar niet betaald vóór cutoff (inconsistentie).")

                    else:
                        # Fallback voor onleesbare data: Unsold
                        self._set_unsold_migration(product, stock_val, reason_text=waarom_weg)


                # REGEL 10: Verkocht=Ja & Datum NIET ingevuld
                elif is_sold_raw and not has_sale_date:
                    _logger.info(f"   [R 10] Betaald=Nee, Verkocht=Ja, Geen datum. Wordt Unsold (Geen Order Datum).")
                    self._set_unsold_migration(product, stock_val, reason_text=waarom_weg or "MIGRATIE: Geen verkoopdatum bekend.")

                # REGEL 11: Verkocht=Nee & Verbergen=Nee
                elif not is_sold_raw and not is_hidden_raw:
                    _logger.info(f"   [R 11] Betaald=Nee, Te koop. Published=True.")
                    self._set_published_stock(product, stock_val)

                # REGEL 12: Verkocht=Nee & Verbergen=Ja
                elif is_hidden_raw:
                    _logger.info(f"   [R 12] Betaald=Nee, Verborgen. Wordt Unsold.")
                    self._set_unsold_migration(product, stock_val, reason_text=waarom_weg)

            # Fallback (Als er iets raars is zoals 'uitbetaald' leeg en 'datum_uitbetaald' gevuld)
            else:
                _logger.warning(f"   [FALLBACK] Onbekende statuscombinatie voor {old_product_id}. Wordt Unsold.")
                self._set_unsold_migration(product, stock_val, reason_text="MIGRATIE FOUT: Onbekende Statuscombinatie.")

        return count

    def _download_image(self, url, fix_old_id=None):
        if not url or str(url) == 'nan': return False

        local_save_path = False
        filename = False

        # --- STAP 1: BEPAAL DE ECHTE BESTANDSNAAM ---
        try:
            # Parse de URL om parameters te scheiden
            parsed = urlparse(str(url).strip())
            params = parse_qs(parsed.query)

            # SCENARIO A: Het is een dynamische URL (foto.php?src=...)
            if 'src' in params:
                # Haal het pad uit 'src': /files/product/foto/sde003.jpg
                src_path = params['src'][0]
                filename = os.path.basename(src_path)  # sde003.jpg

            # SCENARIO B: Het is een gewone URL (.../afbeelding.jpg)
            else:
                filename = os.path.basename(parsed.path)

            # Veiligheid: als bestandsnaam leeg is (bv. url eindigt op /)
            if not filename or len(filename) < 3:
                filename = "image.jpg"

        except Exception as e:
            _logger.warning(f"Kon bestandsnaam niet bepalen uit {url}: {e}")
            filename = "unknown.jpg"

        # --- STAP 2: BOUW HET LOKALE PAD ---
        if self.image_base_path and fix_old_id and filename:
            try:
                # Bouw pad: /mnt/images_source/41215/sde003.jpg
                folder_path = os.path.join(self.image_base_path, str(fix_old_id))
                local_save_path = os.path.join(folder_path, filename)

                # --- OPTIE A: HET BESTAAT AL LOKAAL (CACHE HIT) ---
                if os.path.exists(local_save_path):
                    _logger.info(f"✅ GEVONDEN (CACHE): {local_save_path}")
                    with open(local_save_path, 'rb') as f:
                        return base64.b64encode(f.read())

                # Case-insensitive fallback check
                if os.path.exists(folder_path):
                    for f in os.listdir(folder_path):
                        if f.lower() == filename.lower():
                            full_path = os.path.join(folder_path, f)
                            with open(full_path, 'rb') as f_obj:
                                return base64.b64encode(f_obj.read())
                    _logger.warning(
                        f"❌ NIET GEVONDEN IN MAP: {folder_path}. Gezocht naar: {filename}. Aanwezig: {os.listdir(folder_path)}")
                else:
                    _logger.warning(f"❌ MAP BESTAAT NIET: {folder_path}")

            except Exception as e:
                _logger.error(f"Fout bij padbepaling lokaal bestand: {e}")

        # --- OPTIE B: DOWNLOADEN (CACHE MISS) ---
        # _logger.info(f"🌐 Downloaden: {url}")

        clean_path = url.lstrip('.').strip().replace('//', '/')
        if fix_old_id and '/product//' in url:
            clean_path = clean_path.replace('/product//', f'/product/{fix_old_id}/')

        urls_to_try = [url] if url.startswith('http') else [f"{self.old_site_url}/{clean_path.lstrip('/')}"]
        headers = {'User-Agent': 'Mozilla/5.0'}

        for try_url in urls_to_try:
            try:
                r = requests.get(try_url, headers=headers, timeout=10)
                if r.status_code == 200 and 'image' in r.headers.get('Content-Type', ''):
                    content = r.content

                    # --- STAP 3: OPSLAAN VOOR DE VOLGENDE KEER (CACHE FILL) ---
                    if local_save_path:
                        try:
                            # Zorg dat de map bestaat
                            os.makedirs(os.path.dirname(local_save_path), exist_ok=True)

                            # Schrijf het bestand weg MET DE JUISTE NAAM
                            with open(local_save_path, 'wb') as f_save:
                                f_save.write(content)

                            _logger.info(f"💾 CACHE OPGESLAGEN: {local_save_path}")
                        except Exception as save_err:
                            _logger.warning(f"Kon bestand niet lokaal cachen: {save_err}")

                    return base64.b64encode(content)
            except Exception as e:
                pass

        return False

    def _add_attribute(self, product, att_name, val_name):
        if not val_name or str(val_name) == 'nan': return

        clean_val_string = str(val_name).replace('/', '|').replace('&', '|').replace(' en ', '|')
        vals = clean_val_string.split('|')

        for v in vals:
            v = v.strip()
            if not v: continue

            attribute = self.env['product.attribute'].search([('name', '=ilike', att_name)], limit=1)
            if not attribute:
                attribute = self.env['product.attribute'].create({
                    'name': att_name,
                    'create_variant': 'no_variant'
                })

            value = self.env['product.attribute.value'].search([
                ('attribute_id', '=', attribute.id),
                ('name', '=ilike', v)
            ], limit=1)

            if not value:
                value = self.env['product.attribute.value'].create({
                    'name': v,
                    'attribute_id': attribute.id
                })

            try:
                self.env['product.template.attribute.line'].create({
                    'product_tmpl_id': product.id,
                    'attribute_id': attribute.id,
                    'value_ids': [(6, 0, [value.id])]
                })
            except Exception as e:
                # Vangnet: Als Odoo klaagt over duplicaten, loggen we het en gaan we door
                _logger.warning(f"Kon aparte attribuutlijn niet maken voor {v} op {product.name}: {e}")

    def _add_attribute_by_id(self, product, attribute_id, value_id):
        exists = False
        for line in product.attribute_line_ids:
            if line.attribute_id.id == attribute_id and value_id in line.value_ids.ids: exists = True
        if not exists: self.env['product.template.attribute.line'].create(
            {'product_tmpl_id': product.id, 'attribute_id': attribute_id, 'value_ids': [(6, 0, [value_id])]})

    def _process_giftcards(self):
        if not self.file_giftcards:
            return

        csv_data = self._read_csv(self.file_giftcards)

        # 1. Programma zoeken/maken
        program = self.env['loyalty.program'].search([('program_type', '=', 'gift_card')], limit=1)

        if not program:
            # HAAL EURO OP
            currency_eur = self.env.ref('base.EUR', raise_if_not_found=False)
            currency_id = currency_eur.id if currency_eur else False

            # Zoek een geschikt "Gift Card" product
            gift_card_product = self.env['product.product'].search([
                ('name', 'ilike', 'Gift Card'),
                ('type', '=', 'service')
            ], limit=1)

            # Bestaat het niet? Maak het aan!
            if not gift_card_product:
                gift_card_product = self.env['product.product'].create({
                    'name': 'Gift Card',
                    'type': 'service',
                    'taxes_id': False,  # Geen BTW op bonnen
                    'list_price': 0,
                })

            program = self.env['loyalty.program'].create({
                'name': 'Cadeaubonnen',
                'program_type': 'gift_card',
                'applies_on': 'future',
                'trigger': 'auto',
                'portal_visible': True,
                'portal_point_name': 'Euro',
                'currency_id': currency_id,
            })

            self.env['loyalty.reward'].create({
                'program_id': program.id,
                'reward_type': 'discount',
                'discount_mode': 'per_point',
                'discount': 1.0,
                # GEBRUIK ONS GEVONDEN PRODUCT
                'discount_line_product_id': gift_card_product.id,
            })

        count = 0
        skipped_expired = 0
        skipped_empty = 0
        skipped_exist = 0

        today = fields.Date.context_today(self)

        _logger.info("--- START IMPORT CADEAUBONNEN ---")

        for row in csv_data:
            code = row.get('code')

            # LOG: Geen code
            if not code:
                _logger.warning("SKIP: Rij overgeslagen, geen code gevonden in CSV.")
                continue

            # LOG: Bestaat al
            existing = self.env['loyalty.card'].search([('code', '=', code)], limit=1)
            if existing:
                _logger.info(f"SKIP: Bon {code} bestaat al in Odoo.")
                skipped_exist += 1
                continue

            # Bereken restbedrag
            try:
                totaal = float(str(row.get('bedrag') or '0').replace(',', '.'))
                gebruikt = float(str(row.get('bedrag_gebruikt') or '0').replace(',', '.'))
                rest = totaal - gebruikt
            except ValueError:
                _logger.warning(
                    f"SKIP: Bon {code} heeft ongeldige bedragen (Totaal: {row.get('bedrag')}, Gebruikt: {row.get('bedrag_gebruikt')}).")
                continue

            # LOG: Leeg / Opgebruikt
            if rest <= 0.01:
                _logger.info(f"SKIP: Bon {code} is volledig opgebruikt (Restbedrag: {rest}).")
                skipped_empty += 1
                continue

            # Datum Check
            expiration_date = False
            raw_date = row.get('tot')

            if raw_date and raw_date != '0000-00-00':
                try:
                    exp_date_obj = fields.Date.from_string(raw_date)

                    # LOG: Vervallen
                    if exp_date_obj < today:
                        _logger.info(f"SKIP: Bon {code} is vervallen op {raw_date} (Restbedrag: {rest}).")
                        skipped_expired += 1
                        continue

                    expiration_date = raw_date
                except Exception:
                    _logger.warning(
                        f"LET OP: Datum '{raw_date}' onleesbaar voor bon {code}. Wordt geïmporteerd zonder vervaldatum.")

            # Maak de bon aan
            self.env['loyalty.card'].create({
                'program_id': program.id,
                'code': code,
                'points': rest,
                'expiration_date': expiration_date,
            })
            count += 1

            if count % 50 == 0:
                _logger.info(f"   ... {count} bonnen aangemaakt ...")

        _logger.info("==========================================")
        _logger.info(f"EIND RAPPORT CADEAUBONNEN:")
        _logger.info(f"✅ Aangemaakt: {count}")
        _logger.info(f"❌ Reeds bestaand: {skipped_exist}")
        _logger.info(f"❌ Opgebruikt (0 euro): {skipped_empty}")
        _logger.info(f"❌ Vervallen datum: {skipped_expired}")
        _logger.info("==========================================")

    def _process_actioncodes(self):
        if not self.file_actioncodes:
            return

        csv_data = self._read_csv(self.file_actioncodes)

        # Cache voor de percentage-programma's om database calls te sparen
        # Key = percentage (bv. 10.0), Value = program_id
        percentage_programs_cache = {}

        # 1. Zoek/Maak het VASTE BEDRAG programma (Gift Card)
        fixed_program = self.env['loyalty.program'].search([('name', '=', 'Oude Actiecodes (Vast)')], limit=1)

        if not fixed_program:
            currency_eur = self.env.ref('base.EUR', raise_if_not_found=False)
            currency_id = currency_eur.id if currency_eur else False

            # Product zoeken/maken
            discount_product = self.env['product.product'].search([('name', '=', 'Korting')], limit=1)
            if not discount_product:
                discount_product = self.env['product.product'].create(
                    {'name': 'Korting', 'type': 'service', 'list_price': 0, 'taxes_id': False})

            fixed_program = self.env['loyalty.program'].create({
                'name': 'Oude Actiecodes (Vast)',
                'program_type': 'gift_card',  # Gift card laat variabele bedragen toe
                'applies_on': 'future',
                'trigger': 'auto',
                'portal_visible': False,
                'portal_point_name': 'Euro',
                'currency_id': currency_id,
            })

            self.env['loyalty.reward'].create({
                'program_id': fixed_program.id,
                'reward_type': 'discount',
                'discount_mode': 'per_point',
                'discount': 1.0,
                'discount_line_product_id': discount_product.id,
            })

        count_fixed = 0
        count_percent = 0
        skipped_expired = 0

        today = fields.Date.context_today(self)
        _logger.info("--- START IMPORT ACTIECODES (SPLIT) ---")

        for row in csv_data:
            code = row.get('code')
            if not code: continue

            # Check duplicaten (in alle programma's)
            existing = self.env['loyalty.card'].search([('code', '=', code)], limit=1)
            if existing: continue

            # Datum check
            expiration_date = False
            raw_date = row.get('tot')
            if raw_date and raw_date != '0000-00-00':
                try:
                    exp_date_obj = fields.Date.from_string(raw_date)
                    if exp_date_obj < today:
                        skipped_expired += 1
                        continue
                    expiration_date = raw_date
                except:
                    pass

            # Type bepalen
            soort = str(row.get('soort', '')).lower()
            try:
                # In jouw CSV heet de waarde 'aantal'
                value = float(str(row.get('aantal') or '0').replace(',', '.'))
            except ValueError:
                continue

            if value <= 0: continue

            # === SCENARIO A: VAST BEDRAG ===
            if 'vast' in soort:
                self.env['loyalty.card'].create({
                    'program_id': fixed_program.id,
                    'code': code,
                    'points': value,  # 25 euro = 25 punten
                    'expiration_date': expiration_date,
                })
                count_fixed += 1

            # === SCENARIO B: PERCENTAGE ===
            elif 'percentage' in soort:
                # Check of we voor dit percentage (bv. 10.0) al een programma hebben
                if value not in percentage_programs_cache:
                    prog_name = f"Oude Actiecodes ({int(value)}%)"

                    # Zoek in DB
                    perc_prog = self.env['loyalty.program'].search([('name', '=', prog_name)], limit=1)

                    if not perc_prog:
                        # Maak nieuw programma voor dit specifieke percentage
                        perc_prog = self.env['loyalty.program'].create({
                            'name': prog_name,
                            'program_type': 'coupons',  # Coupons type!
                            'applies_on': 'current',  # Direct toepassen op huidige order
                            'trigger': 'with_code',
                            'portal_visible': False,
                        })

                        # Maak de beloning (bv. 10% korting)
                        self.env['loyalty.reward'].create({
                            'program_id': perc_prog.id,
                            'reward_type': 'discount',
                            'discount_mode': 'percent',
                            'discount': value,  # Hier zetten we de 10 of 20
                            'discount_applicability': 'order',  # Op hele order
                        })

                    # Opslaan in cache
                    percentage_programs_cache[value] = perc_prog.id

                # Maak de coupon aan in het juiste programma
                self.env['loyalty.card'].create({
                    'program_id': percentage_programs_cache[value],
                    'code': code,
                    'points': 0,  # Coupons hebben geen punten nodig, gewoon bestaan is genoeg
                    'expiration_date': expiration_date,
                })
                count_percent += 1

        _logger.info("==========================================")
        _logger.info(f"EIND RAPPORT ACTIECODES:")
        _logger.info(f"✅ Vaste bedragen: {count_fixed}")
        _logger.info(f"✅ Percentage coupons: {count_percent}")
        _logger.info(f"❌ Verlopen: {skipped_expired}")
        _logger.info("==========================================")

    def _create_migration_records(self):
        """ Maakt een generieke klant en inzending aan voor migratie doeleinden. """

        # 1. Klant (Partner)
        partner = self.env['res.partner'].search([('name', '=', 'Fictieve Migratie Klant')], limit=1)
        if not partner:
            partner = self.env['res.partner'].create({
                'name': 'Fictieve Migratie Klant',
                'is_company': False,
                'email': 'migratie@ottersenflamingos.be',
                'comment': 'Gebruikt voor het simuleren van historische verkoop uit de oude webshop.'
            })
        self.migration_partner_id = partner

        # 2. Inzending (Submission)
        submission = self.env['otters.consignment.submission'].search([('name', '=', 'MIGRATIE - Stock Kopieën')],
                                                                      limit=1)
        if not submission:
            # We gebruiken skip_sendcloud=True om te voorkomen dat er labels worden aangemaakt
            submission = self.env['otters.consignment.submission'].with_context(skip_sendcloud=True).create({
                'name': 'MIGRATIE - Stock Kopieën',
                'supplier_id': partner.id,
                'state': 'online',  # Dit bestaat in je model, dus is veilig!
                'payout_method': 'coupon',
                'payout_percentage': 0.5,

                # Verplichte velden (Required=True) invullen:
                'agreed_to_terms': True,
                'agreed_to_clothing_terms': True,
                'agreed_to_shipping_fee': True,
            })

        self.migration_submission_id = submission

    def _is_empty_date(self, date_str):
        """ Utility om te controleren op lege/ongeldige datums """
        return not date_str or date_str in ('0000-00-00', '0000-11-30', 'nan', '')

    def _parse_date(self, date_str):
        # CORRECT: Als het leeg is, geef False terug.
        if self._is_empty_date(date_str):
            return False

        try:
            return fields.Date.from_string(date_str)
        except ValueError:
            _logger.warning(f"Datum {date_str} onleesbaar")
            return False

    def _create_fictive_order(self, product, date, partner_id, is_paid, payout_date):
        """
        Maakt een fictieve SO aan.
        FIX: Gebruikt state='sale' en zet qty_invoiced=besteld zodat hij niet bij 'Te Factureren' komt.
        """

        product_variant = product.product_variant_id
        if not product_variant:
            _logger.warning(f"❌ SKIP: Product {product.name} heeft geen variant.")
            return

        # 1. Datum Check & Conversie
        if not date:
            _logger.warning(f"⛔ SKIP ORDER: Product {product.x_old_id} (Naam: {product.name}) - Geen datum.")
            self._set_unsold_migration(product, 0, reason_text="MIGRATIE FOUT: Order overgeslagen wegens ontbrekende datum")
            return

        date_order_dt = fields.Datetime.to_datetime(date)

        # 2. Order Maken (Draft)
        try:
            order = self.env['sale.order'].create({
                'partner_id': partner_id.id if isinstance(partner_id, type(self.env['res.partner'])) else partner_id,
                'date_order': date_order_dt,
                'client_order_ref': f"MIGR_{product.x_old_id}_{fields.Date.to_string(date)}",
                'origin': f"Migratie: {product.name}",
                'state': 'draft',
            })
        except Exception as e:
            _logger.error(f"❌ CRASH bij maken order voor {product.x_old_id}: {e}")
            return

        # 3. Lijn Maken
        line = self.env['sale.order.line'].create({
            'order_id': order.id,
            'product_id': product_variant.id,
            'price_unit': product.list_price,
            'product_uom_qty': 1,
            'x_is_paid_out': is_paid,
            'x_payout_date': payout_date,
            'x_old_id': f"MIGR_{product.x_old_id}"
        })

        # 4. Bevestigen (Zet status op 'sale')
        order.action_confirm()

        # --- DE CRUCIALE FIX ---
        # Odoo kijkt naar het verschil tussen 'Besteld' en 'Gefactureerd'.
        # Wij zeggen nu hard: "Alles is al geleverd en gefactureerd".
        for l in order.order_line:
            l.write({
                'qty_delivered': l.product_uom_qty,
                'qty_invoiced': l.product_uom_qty
            })
        # -----------------------

        # 5. Finaliseren
        # We hoeven invoice_status niet meer te forceren, Odoo berekent die nu zelf als 'invoiced'
        # omdat qty_invoiced == product_uom_qty.
        order.write({
            'state': 'sale',             # Gewoon 'Sale' gebruiken
            'effective_date': date_order_dt,
        })

        # 6. Opruimen
        self._update_stock(product, 0)
        product.write({'is_published': False})

        _logger.info(f"✅ ORDER AANGEMAAKT: {order.name} voor {product.name}")

    def _create_product_copy(self, original_product, stock_qty):
        """ Kopieert het product en zet het nieuwe exemplaar op voorraad en gepubliceerd. """

        # 1. Haal de migratie inzending op (dit is al een recordset)
        mig_submission = self.migration_submission_id

        if not mig_submission:
            # Vangnet: als de wizard opnieuw gestart is, kan dit veld leeg zijn.
            # Zoek hem dan opnieuw.
            mig_submission = self.env['otters.consignment.submission'].search([('name', '=', 'MIGRATIE - Stock Kopieën')], limit=1)

        # 2. Kopie maken
        # We gebruiken strikt .id (int) voor de submission_id
        new_product = original_product.copy({
            'name': original_product.name + ' (Kopie Migratie)',
            'submission_id': mig_submission.id, # <--- DIT MOET EEN INTEGER ZIJN
            'x_old_id': False,
            'default_code': (original_product.default_code or '') + '-C',
        })

        # 3. Stock en Publicatie op de kopie
        self._update_stock(new_product, stock_qty)
        new_product.write({'is_published': True})

        _logger.info(f"   [COPY] Product gekopieerd: {new_product.name}")

    def _set_unsold_migration(self, product, stock_qty, reason_text=''):
        """
        Product is niet uitbetaald en niet verkocht.
        We bepalen de reden op basis van de tekst uit de CSV (waarom_niet_weergeven).
        """
        self._update_stock(product, stock_qty)  # Behoud de stock (vaak 0)

        # OUDE LOGICA HERSTELD: Bepaal de categorie van de reden
        t = str(reason_text).lower()
        reason_code = 'other'  # Default

        if 'terug' in t or 'opgehaald' in t:
            reason_code = 'returned'
        elif 'goed doel' in t or 'spullenhulp' in t or 'doneer' in t:
            reason_code = 'charity'
        elif 'verloren' in t or 'kapot' in t or 'vlek' in t:
            reason_code = 'lost'
        elif 'merk' in t:
            reason_code = 'brand'
        elif not t and stock_qty <= 0:
            reason_code = 'unknown_migration'  # Alleen unknown als er echt geen tekst is

        # Interne notitie toevoegen als er tekst is
        if reason_text:
            old_desc = product.description or ''
            product.write({'description': f"{old_desc}\n[MIGRATIE] Reden onverkocht: {reason_text}".strip()})

        product.write({
            'is_published': False,
            'x_unsold_reason': reason_code
        })

    def _set_published_stock(self, product, stock_qty):
        """ Product is beschikbaar en moet online staan. """
        self._update_stock(product, stock_qty)
        product.write({
            'is_published': True,
            'x_unsold_reason': False
        })
