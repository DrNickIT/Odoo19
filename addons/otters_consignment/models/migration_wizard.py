# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError
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

    # --- 1. Bestanden ---
    file_customers = fields.Binary(string="1. Klanten (otters_klanten.csv)", required=True)
    filename_customers = fields.Char()

    file_submissions = fields.Binary(string="2. Verzendzakken (otters_verzendzak.csv)", required=True)
    filename_submissions = fields.Char()

    file_brands = fields.Binary(string="3. Merken (otters_merken.csv)", required=False)
    filename_brands = fields.Char()

    file_products = fields.Binary(string="4. Producten (otters_producten.csv)", required=True)
    filename_products = fields.Char()

    file_giftcards = fields.Binary(string="5. Cadeaubonnen (otters_bonnen.csv)", required=False)
    filename_giftcards = fields.Char()

    file_actioncodes = fields.Binary(string="6. Actiecodes (otters_actiecodes.csv)", required=False)
    filename_actioncodes = fields.Char()

    file_orders = fields.Binary(string="7. Bestellingen (bestellingen.csv)", required=False)
    filename_orders = fields.Char()

    file_order_lines = fields.Binary(string="8. Bestelregels (bestellingen_producten.csv)", required=False)
    filename_order_lines = fields.Char()

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
        _logger.info("==========================================")
        _logger.info("=== 🚀 START MIGRATIE PROCES ===")
        _logger.info("==========================================")

        # 1. Klanten
        _logger.info(">>> Stap 1: Klanten verwerken...")
        customer_map = self._process_customers()
        self.env.cr.commit()
        _logger.info(f"✅ Stap 1 Klaar: {len(customer_map)} klanten in geheugen.")

        # 2. Zakken
        _logger.info(">>> Stap 2: Verzendzakken verwerken...")
        submission_map = self._process_submissions(customer_map)
        self.env.cr.commit()
        _logger.info(f"✅ Stap 2 Klaar: {len(submission_map)} zakken in geheugen.")

        # 3. Merken
        _logger.info(">>> Stap 3: Merken verwerken...")
        brand_map = self._process_brands()
        self.env.cr.commit()
        _logger.info(f"✅ Stap 3 Klaar: {len(brand_map)} merken in geheugen.")

        # NIEUW: STAP VOOR CADEAUBONNEN (Best voor producten, of erna, maakt niet veel uit)
        if self.file_giftcards:
            _logger.info(">>> Stap 3b: Cadeaubonnen verwerken...")
            self._process_giftcards()
            self.env.cr.commit()
            _logger.info("✅ Stap 3b Klaar: Cadeaubonnen geïmporteerd.")

        if self.file_actioncodes:
            _logger.info(">>> Stap 3c: Actiecodes verwerken...")
            self._process_actioncodes()
            self.env.cr.commit()
            _logger.info("✅ Stap 3c Klaar: Actiecodes geïmporteerd.")

        # 4. Producten
        _logger.info(">>> Stap 4: Producten verwerken (Dit kan even duren)...")
        count = self._process_products(submission_map, brand_map)

        # 5. Bestellingen (Header)
        order_map = {}
        if self.file_orders:
            _logger.info(">>> Stap 5: Bestellingen (Headers) verwerken...")
            order_map = self._process_orders()
            self.env.cr.commit()

        # 6. Bestelregels (Lines)
        if self.file_order_lines and order_map:
            _logger.info(">>> Stap 6: Bestelregels verwerken & Orders Bevestigen...")
            self._process_order_lines(order_map)
            self.env.cr.commit()

        _logger.info("==========================================")
        _logger.info(f"=== 🏁 MIGRATIE VOLTOOID: {count} PRODUCTEN ===")
        _logger.info("==========================================")

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {'title': 'Klaar!', 'message': f'{count} producten verwerkt. Check de logs voor details.', 'type': 'success', 'sticky': True}
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
                full_name = f"{row.get('voornaam','')} {row.get('achternaam','')}".strip() or email
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
                # === DATUM FIX ===
                raw_date = row.get('datum_ontvangen')
                date = fields.Date.today() # Standaard vandaag

                if raw_date and raw_date not in ['0000-00-00', 'nan', '']:
                    try:
                        # Check of het formaat geldig is
                        fields.Date.from_string(raw_date)
                        date = raw_date
                    except ValueError:
                        pass # Bij fout, hou 'vandaag' aan

                # ... (Partner IBAN ophalen) ...
                partner_iban = partner.bank_ids[:1].acc_number if partner.bank_ids else False

                submission = self.env['otters.consignment.submission'].with_context(skip_sendcloud=True).create({
                    'name': 'Nieuw',
                    'supplier_id': partner.id,
                    'submission_date': date,  # Gebruik de veilige datum
                    'state': 'online',
                    'payout_method': 'coupon',
                    'payout_percentage': 0.5,
                    'x_old_id': str(old_bag_id),
                    'action_unaccepted': action_val,
                    'action_unsold': action_val,
                    'agreed_to_terms': True,
                    'agreed_to_clothing_terms': True,
                    'agreed_to_shipping_fee': True,
                    'x_iban': partner_iban,
                    'x_is_locked': True
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
            brand_attribute = self.env['product.attribute'].create({'name': 'Merk', 'create_variant': 'no_variant', 'display_type': 'select'})

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

            # 2. BASIS DATA (Tekst updaten we altijd, dat is snel)
            brand_vals = {
                'name': name,
                'description': row.get('omschrijving_nl'),
                'is_published': True,
                'website_meta_title': row.get('seo_titel'),
                'website_meta_description': row.get('seo_description'),
                'website_meta_keywords': row.get('seo_keywords'),
            }

            # 3. FOTO LOGICA (SLIMMER!)
            # We downloaden alleen als het nodig is
            logo_url = row.get('foto')
            img_data = False

            should_download = False

            if not brand:
                # Nieuw merk? Altijd proberen te downloaden
                should_download = True
            elif not brand.logo:
                # Bestaand merk zonder logo? Downloaden!
                should_download = True
            else:
                # Bestaand merk MET logo? Overslaan.
                should_download = False
                skipped_images += 1

            if should_download and logo_url and str(logo_url) != 'nan':
                img_data = self._download_image(logo_url)
                if img_data:
                    brand_vals['logo'] = img_data

            # 4. MAAK AAN OF UPDATE
            if not brand:
                brand = self.env['otters.brand'].create(brand_vals)
            else:
                brand.write(brand_vals)

            # 5. ATTRIBUUT WAARDE
            brand_val = self.env['product.attribute.value'].search([('attribute_id', '=', brand_attribute.id), ('name', '=', name)], limit=1)
            if not brand_val:
                brand_val = self.env['product.attribute.value'].create({'name': name, 'attribute_id': brand_attribute.id})

            brand_map[old_merk_id] = {
                'brand_id': brand.id,
                'attr_val_id': brand_val.id,
                'attr_id': brand_attribute.id
            }
            count += 1

        _logger.info(f"--- MERKEN KLAAR: {count} verwerkt. {skipped_images} keer foto-download overgeslagen (bestond al). ---")
        return brand_map

    # -------------------------------------------------------------------------
    # STAP 4: PRODUCTEN (AANGEPAST VOOR x_unsold_reason)
    # -------------------------------------------------------------------------
    def _process_products(self, submission_map, brand_map):
        csv_data = self._read_csv(self.file_products)
        count = 0

        # --- 1. CACHE OPBOUWEN ---
        _logger.info("--- CACHE OPBOUWEN... ---")
        existing_recs = self.env['product.template'].search_read(
            ['|', ('x_old_id', '!=', False), ('default_code', '!=', False)],
            ['id', 'x_old_id', 'default_code']
        )
        existing_by_old_id = {str(r['x_old_id']): r['id'] for r in existing_recs if r['x_old_id']}
        existing_by_code = {r['default_code']: r['id'] for r in existing_recs if r['default_code']}

        _logger.info(f"--- CACHE KLAAR: {len(existing_recs)} producten in geheugen. ---")

        condition_mapping = {
            '5 hartjes': '❤️❤️❤️❤️❤️', '4 hartjes': '❤️❤️❤️❤️🤍',
            '3 hartjes': '❤️❤️❤️🤍🤍', '2 hartjes': '❤️❤️🤍🤍🤍', '1 hartje': '❤️🤍🤍🤍🤍'
        }
        accessoires_types = [
            'muts & sjaal', 'hoedjes & petjes', 'tutjes',
            'accessoires', 'speelgoed', 'riem', 'haarband', 'rugzakken en tassen',
            'slab', 'speenkoord', 'badcape', 'dekentje'
        ]

        _logger.info("--- START PRODUCTEN IMPORT ---")

        for row in csv_data:
            count += 1
            if count % 50 == 0:
                self.env.cr.commit()
                _logger.info(f"   [PRODUCTEN] {count} verwerkt... (Huidige: {row.get('naam')})")

            # --- A. VALIDATIE ---
            zak_id_product = self._clean_id(row.get('zak_id'))
            old_product_id = self._clean_id(row.get('product_id'))
            name = row.get('naam')

            if not zak_id_product: continue
            submission = submission_map.get(zak_id_product)
            if not submission: continue

            # --- B. BESTAAT HET AL? ---
            product_id = False
            default_code = row.get('code')

            if old_product_id and str(old_product_id) in existing_by_old_id:
                product_id = existing_by_old_id[str(old_product_id)]
            elif default_code and default_code in existing_by_code:
                product_id = existing_by_code[default_code]

            product = self.env['product.template'].browse(product_id) if product_id else False

            # --- C. COMMISSIE LOGICA ---
            commissie_raw = row.get('commissie')
            if commissie_raw:
                try:
                    comm_val = int(float(str(commissie_raw).replace(',', '.')))
                    method = False; percentage = 0.0
                    if comm_val == 30: method = 'cash'; percentage = 0.30
                    elif comm_val == 50: method = 'coupon'; percentage = 0.50

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
                except Exception: pass

            # --- D. STOCK, STATUS & UNSOLD REASON (AANGEPAST) ---
            verkocht = str(row.get('verkocht', '')).lower()
            online_verkocht = str(row.get('online_verkocht', '')).lower()
            niet_weergeven = str(row.get('product_niet_weergeven', '')).lower()
            waarom_weg = str(row.get('waarom_niet_weergeven', '')).lower()

            datum_verkocht = str(row.get('datum_verkocht', '')).strip()
            datum_uitbetaald = str(row.get('datum_uitbetaald', '')).strip()

            stock_csv = row.get('stock') or '0'
            try: stock_val = float(stock_csv.replace(',', '.'))
            except: stock_val = 0.0

            def is_empty_date(d): return not d or d == '0000-00-00'

            is_sold = False
            if verkocht == 'ja' or online_verkocht == 'ja' or not is_empty_date(datum_verkocht) or not is_empty_date(datum_uitbetaald):
                is_sold = True

            internal_description = False
            unsold_reason = False  # Nieuwe variabele

            if is_sold:
                final_qty = 1.0
                is_published = False
                internal_description = "MIGRATIE: Was verkocht in oud systeem."

            elif niet_weergeven == 'ja':
                # --- NIEUWE LOGICA: Probeer de reden te mappen ---
                final_qty = 0.0 # Als het weg is, is de stock 0
                is_published = False

                if 'terug' in waarom_weg or 'opgehaald' in waarom_weg:
                    unsold_reason = 'returned'
                elif 'goed doel' in waarom_weg or 'spullenhulp' in waarom_weg or 'doneer' in waarom_weg:
                    unsold_reason = 'charity'
                elif 'verloren' in waarom_weg or 'kapot' in waarom_weg or 'vlek' in waarom_weg:
                    unsold_reason = 'lost'
                else:
                    unsold_reason = 'other' # Fallback

                internal_description = f"Oorspronkelijk verborgen: {row.get('waarom_niet_weergeven')}."

            else:
                final_qty = stock_val
                is_published = (final_qty > 0)

            # --- E. DATA VOORBEREIDEN ---
            product_vals = {
                'name': name,
                'submission_id': submission.id,
                'is_published': is_published,
                'type': 'consu', # Consumable maar met voorraad tracking (is_storable)
                'is_storable': True,
                'default_code': default_code,
                'x_old_id': str(old_product_id),
                'description_ecommerce': row.get('lange_omschrijving'),
                'description_sale': row.get('korte_omschrijving_nl'),
                'website_meta_title': row.get('seo_titel'),
                'website_meta_description': row.get('seo_description'),
                'website_meta_keywords': row.get('seo_keywords'),
                'x_unsold_reason': unsold_reason, # <--- HIER VULLEN WE HET IN
            }

            if internal_description:
                product_vals['description'] = internal_description

            # --- F. CATEGORIE BEPALEN (Blijft hetzelfde) ---
            type_raw = str(row.get('type', '')).strip()
            type_lower = type_raw.lower()
            maat_raw = str(row.get('maat', '')).strip()

            target_cat_name = 'Kleding'
            target_sub_name = type_raw.capitalize()

            if type_lower in accessoires_types:
                target_cat_name = 'Accessoires'
            elif 'kousen' in type_lower or 'sokken' in type_lower:
                target_cat_name = 'Schoenen & Kousen'
                target_sub_name = 'Kousen'
            elif any(x in type_lower for x in ['schoen', 'laars', 'sneaker', 'sandaal']):
                target_cat_name = 'Schoenen & Kousen'
                target_sub_name = 'Schoenen'

            if maat_raw:
                try:
                    clean_maat = re.match(r"(\d+)", maat_raw)
                    if clean_maat:
                        size_num = int(clean_maat.group(1))
                        if size_num <= 45:
                            if target_cat_name != 'Accessoires' and target_sub_name != 'Kousen':
                                target_cat_name = 'Schoenen & Kousen'
                                target_sub_name = 'Schoenen'
                except Exception: pass

            main_cat = self.env['product.public.category'].search([('name', '=', target_cat_name), ('parent_id', '=', False)], limit=1)
            if not main_cat: main_cat = self.env['product.public.category'].create({'name': target_cat_name})
            final_categ_ids = [main_cat.id]

            if target_sub_name:
                sub_cat = self.env['product.public.category'].search([('name', '=', target_sub_name), ('parent_id', '=', main_cat.id)], limit=1)
                if not sub_cat: sub_cat = self.env['product.public.category'].create({'name': target_sub_name, 'parent_id': main_cat.id})
                final_categ_ids.append(sub_cat.id)

            product_vals['public_categ_ids'] = [(6, 0, final_categ_ids)]

            int_main = self.env['product.category'].search([('name', '=', target_cat_name), ('parent_id', '=', False)], limit=1)
            if not int_main: int_main = self.env['product.category'].create({'name': target_cat_name})
            final_int_id = int_main.id

            if target_sub_name:
                int_sub = self.env['product.category'].search([('name', '=', target_sub_name), ('parent_id', '=', int_main.id)], limit=1)
                if not int_sub: int_sub = self.env['product.category'].create({'name': target_sub_name, 'parent_id': int_main.id})
                final_int_id = int_sub.id

            product_vals['categ_id'] = final_int_id

            # --- G. MERK KOPPELING ---
            old_merk_id = self._clean_id(row.get('merk_id'))
            brand_data = None
            if old_merk_id and old_merk_id in brand_map:
                brand_data = brand_map[old_merk_id]
                product_vals['brand_id'] = brand_data['brand_id']

            # --- H. UPDATE OF CREATE ---
            if product:
                product.write(product_vals)
                self._update_stock(product, final_qty)
                if brand_data:
                    self._add_attribute_by_id(product, brand_data['attr_id'], brand_data['attr_val_id'])
                if not product.product_template_image_ids and not product.image_1920:
                    extra_fotos = row.get('extra_fotos')
                    if extra_fotos and str(extra_fotos) != 'nan':
                        urls = extra_fotos.split(',')
                        for idx, url in enumerate(urls):
                            if url:
                                extra_img = self._download_image(url.strip(), fix_old_id=old_product_id)
                                if extra_img:
                                    self.env['product.image'].create({
                                        'product_tmpl_id': product.id,
                                        'name': f"{name} - Extra {idx+1}",
                                        'image_1920': extra_img
                                    })
            else:
                image_url = row.get('foto')
                product_vals['image_1920'] = self._download_image(image_url, fix_old_id=old_product_id)
                prijs_raw = row.get('prijs') or '0'
                try: product_vals['list_price'] = float(str(prijs_raw).replace(',', '.'))
                except: product_vals['list_price'] = 0.0

                product = self.env['product.template'].create(product_vals)
                if old_product_id: existing_by_old_id[str(old_product_id)] = product.id

                self._update_stock(product, final_qty)

                if maat_raw:
                    attr_name = 'Schoenmaat' if target_cat_name == 'Schoenen & Kousen' else 'Maat'
                    self._add_attribute(product, attr_name, maat_raw)

                if row.get('merk'): self._add_attribute(product, 'Merk', row.get('merk'))
                if row.get('seizoen'): self._add_attribute(product, 'Seizoen', row.get('seizoen'))
                if row.get('categorie'): self._add_attribute(product, 'Geslacht', row.get('categorie'))
                if row.get('type'): self._add_attribute(product, 'Type', row.get('type'))

                staat = row.get('staat')
                if staat in condition_mapping:
                    self._add_attribute(product, 'Conditie', condition_mapping[staat])

                if brand_data:
                    self._add_attribute_by_id(product, brand_data['attr_id'], brand_data['attr_val_id'])

                extra_fotos = row.get('extra_fotos')
                if extra_fotos and str(extra_fotos) != 'nan':
                    urls = extra_fotos.split(',')
                    for idx, url in enumerate(urls):
                        if url:
                            extra_img = self._download_image(url.strip(), fix_old_id=old_product_id)
                            if extra_img:
                                self.env['product.image'].create({
                                    'product_tmpl_id': product.id,
                                    'name': f"{name} - Extra {idx+1}",
                                    'image_1920': extra_img
                                })

        return count

    def _download_image(self, url, fix_old_id=None):
        if not url or str(url) == 'nan': return False

        # --- OPTIE 1: LOKAAL ZOEKEN (VIA PRODUCT ID MAP) ---
        if self.image_base_path and fix_old_id:
            try:
                # 1. Haal bestandsnaam op
                # We splitsen op '?' om eventuele parameters na .jpg weg te halen (bv. ?v=1)
                clean_url_path = url.split('?')[0] if '?' in url else url
                # Als de filename IN de query params zit (zoals bij jou: foto.php?src=.../foto.jpg)
                # Dan pakt os.path.basename automatisch het laatste stukje na de laatste /
                filename = os.path.basename(url.strip())

                # Als de filename nog steeds rommel bevat (zoals ?src=), proberen we een tweede schoonmaak
                if '?' in filename:
                    filename = filename.split('?')[0]

                # 2. Bouw het pad
                # Let op: we gebruiken os.path.join voor veilige paden
                # Pad wordt: /mnt/images_source/fotos / 41215 / tra073.jpg
                folder_path = os.path.join(self.image_base_path, str(fix_old_id))
                local_path = os.path.join(folder_path, filename)

                # --- DEBUG LOGGING (TIJDELIJK AAN) ---
                _logger.info(f"🔎 ZOEKEN: {local_path}")

                # Check 1: Exacte match
                if os.path.exists(local_path):
                    _logger.info(f"✅ GEVONDEN: {local_path}")
                    with open(local_path, 'rb') as f:
                        return base64.b64encode(f.read())

                # Check 2: Case-Insensitive (tra073.JPG vs tra073.jpg)
                elif os.path.exists(folder_path):
                    # _logger.info(f"⚠️ Exact niet gevonden, ik zoek case-insensitive in: {folder_path}")
                    for f in os.listdir(folder_path):
                        if f.lower() == filename.lower():
                            full_path = os.path.join(folder_path, f)
                            _logger.info(f"✅ GEVONDEN (Case-Insensitive): {full_path}")
                            with open(full_path, 'rb') as f_obj:
                                return base64.b64encode(f_obj.read())

                    # Als we hier komen, zit het bestand niet in de map
                    _logger.warning(f"❌ NIET GEVONDEN IN MAP: {folder_path}. Gezocht naar: {filename}. Aanwezig: {os.listdir(folder_path)}")

                else:
                    _logger.warning(f"❌ MAP BESTAAT NIET: {folder_path}")

            except Exception as e:
                _logger.error(f"Fout bij lezen lokaal bestand {local_path}: {e}")

        # --- OPTIE 2: DOWNLOAD (FALLBACK) ---
        _logger.info(f"🌐 Downloading: {url}")

        # ... (Rest van je download logica blijft hetzelfde) ...
        clean_path = url.lstrip('.').strip().replace('//', '/')
        if fix_old_id and '/product//' in url:
            clean_path = clean_path.replace('/product//', f'/product/{fix_old_id}/')

        urls_to_try = [url] if url.startswith('http') else [f"{self.old_site_url}/{clean_path.lstrip('/')}"]
        headers = {'User-Agent': 'Mozilla/5.0'}
        for try_url in urls_to_try:
            try:
                r = requests.get(try_url, headers=headers, timeout=5)
                if r.status_code == 200 and 'image' in r.headers.get('Content-Type', ''):
                    return base64.b64encode(r.content)
            except: pass

        return False

    def _add_attribute(self, product, att_name, val_name):
        if not val_name or str(val_name) == 'nan': return
        vals = str(val_name).replace('&', '|').replace(' en ', '|').split('|')
        for v in vals:
            v = v.strip()
            if not v: continue
            attribute = self.env['product.attribute'].search([('name', '=ilike', att_name)], limit=1)
            if not attribute: attribute = self.env['product.attribute'].create({'name': att_name, 'create_variant': 'no_variant'})
            value = self.env['product.attribute.value'].search([('attribute_id', '=', attribute.id), ('name', '=ilike', v)], limit=1)
            if not value: value = self.env['product.attribute.value'].create({'name': v, 'attribute_id': attribute.id})
            exists = False
            for line in product.attribute_line_ids:
                if line.attribute_id.id == attribute.id and value.id in line.value_ids.ids: exists = True
            if not exists: self.env['product.template.attribute.line'].create({'product_tmpl_id': product.id, 'attribute_id': attribute.id, 'value_ids': [(6, 0, [value.id])]})

    def _add_attribute_by_id(self, product, attribute_id, value_id):
        exists = False
        for line in product.attribute_line_ids:
            if line.attribute_id.id == attribute_id and value_id in line.value_ids.ids: exists = True
        if not exists: self.env['product.template.attribute.line'].create({'product_tmpl_id': product.id, 'attribute_id': attribute_id, 'value_ids': [(6, 0, [value_id])]})

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
                    'taxes_id': False, # Geen BTW op bonnen
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
                _logger.warning(f"SKIP: Bon {code} heeft ongeldige bedragen (Totaal: {row.get('bedrag')}, Gebruikt: {row.get('bedrag_gebruikt')}).")
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
                    _logger.warning(f"LET OP: Datum '{raw_date}' onleesbaar voor bon {code}. Wordt geïmporteerd zonder vervaldatum.")

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
                discount_product = self.env['product.product'].create({'name': 'Korting', 'type': 'service', 'list_price': 0, 'taxes_id': False})

            fixed_program = self.env['loyalty.program'].create({
                'name': 'Oude Actiecodes (Vast)',
                'program_type': 'gift_card', # Gift card laat variabele bedragen toe
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
                except: pass

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
                    'points': value, # 25 euro = 25 punten
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
                            'program_type': 'coupons', # Coupons type!
                            'applies_on': 'current',   # Direct toepassen op huidige order
                            'trigger': 'with_code',
                            'portal_visible': False,
                        })

                        # Maak de beloning (bv. 10% korting)
                        self.env['loyalty.reward'].create({
                            'program_id': perc_prog.id,
                            'reward_type': 'discount',
                            'discount_mode': 'percent',
                            'discount': value, # Hier zetten we de 10 of 20
                            'discount_applicability': 'order', # Op hele order
                        })

                    # Opslaan in cache
                    percentage_programs_cache[value] = perc_prog.id

                # Maak de coupon aan in het juiste programma
                self.env['loyalty.card'].create({
                    'program_id': percentage_programs_cache[value],
                    'code': code,
                    'points': 0, # Coupons hebben geen punten nodig, gewoon bestaan is genoeg
                    'expiration_date': expiration_date,
                })
                count_percent += 1

        _logger.info("==========================================")
        _logger.info(f"EIND RAPPORT ACTIECODES:")
        _logger.info(f"✅ Vaste bedragen: {count_fixed}")
        _logger.info(f"✅ Percentage coupons: {count_percent}")
        _logger.info(f"❌ Verlopen: {skipped_expired}")
        _logger.info("==========================================")

    # -------------------------------------------------------------------------
    # STAP 5: BESTELLINGEN (HEADERS) - VOLLEDIGE VERSIE
    # -------------------------------------------------------------------------
    def _process_orders(self):
        csv_data = self._read_csv(self.file_orders)
        order_map = {} # Oude ID -> Nieuwe Odoo Order ID
        count = 0

        # --- 1. CACHE OPBOUWEN ---
        # We laden partners in het geheugen om zoekacties te versnellen
        _logger.info("--- PARTNER CACHE OPBOUWEN... ---")
        partner_obj = self.env['res.partner']

        # We zoeken alle partners die een e-mail hebben
        # Dit geeft een lijst van dicts terug: [{'id': 1, 'email': '...'}, ...]
        all_partners = partner_obj.search_read(
            [('email', '!=', False)],
            ['id', 'email', 'name']
        )

        # Maak een snelle opzoek-tabel op E-MAIL
        # We gebruiken .lower().strip() voor de zekerheid
        partner_by_email = {}
        for p in all_partners:
            if p['email']:
                clean_email = str(p['email']).strip().lower()
                partner_by_email[clean_email] = p['id']

        # Optioneel: Ook een cache op NAAM voor de fallback
        partner_by_name = {p['name'].strip().lower(): p['id'] for p in all_partners if p['name']}

        _logger.info(f"--- PARTNER CACHE KLAAR ({len(all_partners)} partners) ---")
        _logger.info("--- START ORDERS IMPORT ---")

        for row in csv_data:
            # === COMMIT ===
            count += 1
            if count % 100 == 0:
                self.env.cr.commit()
                _logger.info(f"   ... {count} orders verwerkt")

            old_id = row.get('bestel_id')
            if not old_id: continue

            # CHECK: Bestaat al?
            # We zoeken op client_order_ref (= het oude bestel ID)
            existing = self.env['sale.order'].search([('client_order_ref', '=', old_id)], limit=1)

            if existing:
                # Als hij al bestaat, slaan we hem op in de map (want de order lines hebben dit nodig)
                # Maar we doen verder niets (SKIP)
                order_map[old_id] = existing
                continue

            # Datum parsen (formaat: 2021-03-28 18:31:23)
            order_date = fields.Datetime.now()
            raw_date = row.get('datum')
            if raw_date and raw_date != '0000-00-00 00:00:00':
                try:
                    order_date = fields.Datetime.from_string(raw_date)
                except:
                    pass

            # Klant zoeken (Via onze snelle cache!)
            raw_email = row.get('factuur_email', '')
            email = str(raw_email).strip().lower()
            partner_id = False

            # 1. Zoek op Email in Cache
            if email and email in partner_by_email:
                partner_id = partner_by_email[email]

            # 2. Zoek via Database (Fallback, voor het geval de cache niet up to date is)
            if not partner_id and email:
                p = partner_obj.search([('email', '=ilike', email)], limit=1)
                if p: partner_id = p.id

            # 3. Zoek op Naam (Fallback)
            if not partner_id:
                naam_raw = row.get('factuur_naam', 'Onbekende Klant')
                naam_clean = str(naam_raw).strip().lower()

                if naam_clean in partner_by_name:
                    partner_id = partner_by_name[naam_clean]
                else:
                    # Nog steeds niet? Zoek in DB
                    p = partner_obj.search([('name', '=ilike', naam_raw)], limit=1)
                    if p: partner_id = p.id

            # 4. Nog steeds niet? Maak aan!
            if not partner_id:
                naam = row.get('factuur_naam') or 'Onbekende Klant'
                new_partner = partner_obj.create({
                    'name': naam,
                    'email': row.get('factuur_email'),
                    'street': row.get('factuur_straat'),
                    'city': row.get('factuur_gemeente'),
                    'comment': 'Geïmporteerd uit oude bestellingen'
                })
                partner_id = new_partner.id

                # Update de cache direct, zodat we hem de volgende keer snel vinden
                if new_partner.email:
                    partner_by_email[str(new_partner.email).strip().lower()] = new_partner.id
                partner_by_name[str(new_partner.name).strip().lower()] = new_partner.id

            # Order aanmaken
            order = self.env['sale.order'].create({
                'partner_id': partner_id,
                'date_order': order_date,
                'client_order_ref': old_id,   # Cruciaal voor duplicate check en lines koppeling
                'origin': f"Import: {row.get('ordernummer')}",
                'state': 'draft',             # We laten hem op draft staan, de volgende stap (6) vult hem
            })

            order_map[old_id] = order

        return order_map

    # -------------------------------------------------------------------------
    # STAP 6: BESTELREGELS (ZONDER BEVESTIGING)
    # -------------------------------------------------------------------------
    def _process_order_lines(self, order_map):
        csv_data = self._read_csv(self.file_order_lines)
        count = 0
        skipped = 0

        _logger.info("--- START ORDER REGELS ---")

        for row in csv_data:
            # 1. Unieke ID bepalen
            old_line_id = row.get('order_product_id')
            if not old_line_id: continue

            # 2. CHECK: Bestaat deze regel al? (Crash recovery)
            existing_line = self.env['sale.order.line'].search([
                ('x_old_id', '=', str(old_line_id))
            ], limit=1)

            if existing_line:
                skipped += 1
                continue

            # 3. Order zoeken
            old_order_id = row.get('order_id') or row.get('order_id_top')
            # Als order niet in de map zit (omdat we script herstarten), zoek in DB
            order = False
            if old_order_id in order_map:
                order = order_map[old_order_id]
            else:
                # Fallback: Zoek de order in de database
                order = self.env['sale.order'].search([('client_order_ref', '=', old_order_id)], limit=1)

            if not order: continue

            # 4. Product zoeken
            old_product_id = row.get('product_id')
            product = self.env['product.product'].search([
                ('product_tmpl_id.x_old_id', '=', str(old_product_id))
            ], limit=1)

            if not product:
                product = self.env['product.product'].search([('default_code', '=', 'MIGRATIE_ITEM')], limit=1)
                if not product:
                    product = self.env['product.product'].create({
                        'name': 'Onbekend/Verwijderd Item (Migratie)',
                        'default_code': 'MIGRATIE_ITEM',
                        'type': 'service',
                        'list_price': 0
                    })

            price_raw = row.get('prijs', '0').replace('€', '').replace(',', '.').strip()
            try: price = float(price_raw)
            except: price = 0.0

            # 5. Regel aanmaken (MET x_old_id)
            self.env['sale.order.line'].create({
                'order_id': order.id,
                'product_id': product.id,
                'price_unit': price,
                'product_uom_qty': 1,
                'x_is_paid_out': True,
                'x_old_id': str(old_line_id) # Opslaan voor de check hierboven
            })

            count += 1
            if count % 100 == 0:
                self.env.cr.commit()
                _logger.info(f"   ... {count} regels verwerkt")

        _logger.info(f"--- KLAAR: {count} nieuwe regels. {skipped} overgeslagen (bestonden al). ---")

    # -------------------------------------------------------------------------
    # STAP 7: ORDERS BEVESTIGEN (MET AUTO-STOCK FIX)
    # -------------------------------------------------------------------------
    def action_confirm_migrated_orders(self):
        _logger.info("--- START ORDER BEVESTIGING (MET STOCK FIX) ---")

        # Zoek orders die nog in concept staan en uit migratie komen
        orders_to_confirm = self.env['sale.order'].search([
            ('state', '=', 'draft'),
            ('client_order_ref', '!=', False),
            ('order_line', '!=', False)
        ])

        count = 0
        total = len(orders_to_confirm)
        warehouse = self.env['stock.warehouse'].search([], limit=1)
        location_id = warehouse.lot_stock_id.id

        for order in orders_to_confirm:
            # === COMMIT ===
            count += 1
            if count % 20 == 0:
                self.env.cr.commit()
                _logger.info(f"   ... {count}/{total} orders bevestigd")

            try:
                # STAP A: CHECK STOCK VOOR ELKE REGEL
                # Voordat we bevestigen, zorgen we dat er genoeg stock is.
                # Dit fixt het probleem dat producten al op 0 staan.
                for line in order.order_line:
                    product = line.product_id
                    if product.type == 'product' and product.qty_available < line.product_uom_qty:
                        # Tekort! We voegen snel stock toe (Just-in-Time)
                        self.env['stock.quant'].with_context(inventory_mode=True).create({
                            'product_id': product.id,
                            'location_id': location_id,
                            'inventory_quantity': line.product_uom_qty, # Zet op wat we nodig hebben
                        }).action_apply_inventory()

                # STAP B: BEVESTIGEN
                original_date = order.date_order

                # Dit boekt de voorraad nu direct weer af naar 0
                order.action_confirm()

                # 2. TRUCJE: Zet 'Gefactureerd Aantal' gelijk aan 'Besteld Aantal'
                # Hierdoor denkt Odoo dat de factuur al gemaakt is (buiten Odoo om)
                # en verdwijnt de order uit de lijst "Te Factureren".
                for line in order.order_line:
                    line.write({'qty_invoiced': line.product_uom_qty})

                # 3. Datum herstellen en Locken
                order.write({
                    'date_order': original_date,
                    'state': 'sale',
                    'effective_date': original_date,
                    # Forceer de invoice_status op 'invoiced' (voor de zekerheid)
                    'invoice_status': 'invoiced'
                })

                # STAP D: LEVERING AFHANDELEN
                if order.picking_ids:
                    for picking in order.picking_ids:
                        # Omdat we net stock hebben toegevoegd, zou dit moeten lukken
                        # We zetten de aantallen op 'Gedaan'
                        for move in picking.move_ids:
                            move.quantity = move.product_uom_qty

                        try:
                            picking.with_context(skip_backorder=True).button_validate()
                        except: pass

            except Exception as e:
                _logger.warning(f"Fout bij order {order.name}: {e}")

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {'title': 'Klaar', 'message': f'{count} orders bevestigd.', 'type': 'success'}
        }

    def action_cleanup_stock(self):
        """
        Draai dit NA de order-import.
        Zoekt producten die 'verkocht' moesten zijn (is_published=False en type=consu),
        maar die nog steeds op voorraad liggen (omdat de order-import faalde of ontbrak).
        Zet ze terug op 0.
        """
        _logger.info("--- START STOCK CLEANUP ---")

        # We zoeken producten die:
        # 1. Door migratie zijn aangemaakt (x_old_id bestaat)
        # 2. Niet gepubliceerd zijn (want verkochte items staan op published=False)
        # 3. Nog steeds voorraad hebben (> 0)

        products_to_fix = self.env['product.product'].search([
            ('product_tmpl_id.x_old_id', '!=', False),
            ('product_tmpl_id.is_published', '=', False),
            ('qty_available', '>', 0)
        ])

        count = 0
        for product in products_to_fix:
            # Check: Is dit echt een 'verkocht' item?
            # We kunnen kijken of er een description is die we net hebben gezet
            if "MIGRATIE: Was verkocht" in (product.description or ""):

                # Correctie uitvoeren: Zet stock naar 0
                self.env['stock.quant'].with_context(inventory_mode=True).create({
                    'product_id': product.id,
                    'location_id': self.env['stock.warehouse'].search([], limit=1).lot_stock_id.id,
                    'inventory_quantity': 0.0,
                }).action_apply_inventory()

                count += 1

        _logger.info(f"--- CLEANUP KLAAR: {count} wees-producten op 0 gezet ---")

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {'title': 'Cleanup Klaar', 'message': f'{count} producten gecorrigeerd.', 'type': 'success'}
        }