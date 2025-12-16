# In models/product_template.py
from odoo import models, fields, api

class ProductTemplate(models.Model):
    _inherit = 'product.template'

    _sql_constraints = [
        ('default_code_unique',
         'UNIQUE(default_code)',
         'De interne referentie (code) van het product moet uniek zijn!')
    ]

    x_unsold_reason = fields.Selection([
        ('charity', 'Geschonken aan goed doel'),
        ('returned', 'Teruggestuurd naar klant'),
        ('lost', 'Verloren / Beschadigd'),
        ('brand', 'Merk niet geaccepteerd'),
        ('unknown_migration', 'Ongekend tijdens migratie'),
        ('other', 'Andere')
    ], string="Reden uit collectie", copy=False, tracking=True, help="Vul dit in als het item niet verkocht is en uit de shop moet.")

    submission_id = fields.Many2one(
        'otters.consignment.submission',
        string="Originele Inzending",
        ondelete='set null'
    )

    # NIEUWE RELATED VELDEN TOEVOEGEN:

    consignment_supplier_id = fields.Many2one(
        'res.partner',
        string="Leverancier Inzending",
        related='submission_id.supplier_id',
        store=False,  # Niet opslaan in database, lees van de relatie
        readonly=True
    )

    consignment_submission_date = fields.Date(
        string="Inzendingsdatum",
        related='submission_id.submission_date',
        store=False,
        readonly=True
    )

    consignment_payout_method = fields.Selection(
        string="Uitbetalingsmethode",
        related='submission_id.payout_method',
        store=False,
        readonly=True
    )

    consignment_payout_percentage = fields.Float(
        string="Uitbetalingspercentage",
        related='submission_id.payout_percentage',
        store=False,
        readonly=True
    )

    consignment_state = fields.Selection(
        string='Status Inzending',
        related='submission_id.state',
        store=False,
        readonly=True
    )

    x_old_id = fields.Char(string="Oud Product ID", copy=False, readonly=True)

    brand_id = fields.Many2one(
        'otters.brand',
        string="Merk",
        index=True,
        ondelete='set null'
    )

    # Hulpveldje om te tonen wat de klant wou (Donate/Return)
    x_customer_preference = fields.Selection(
        related='submission_id.action_unsold',
        string="Voorkeur Klant",
        readonly=True
    )

    x_is_paid = fields.Boolean(
        string="Uitbetaald",
        compute='_compute_is_paid',
        store=False
    )

    x_payout_date = fields.Date(
        string="Datum Uitbetaald",
        compute='_compute_payout_date',
        store=False
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            # Check 1: Hoort dit product bij een inzending?
            # Check 2: Is er nog geen referentie ingevuld? (Zo wel, overschrijven we die niet)
            if vals.get('submission_id') and not vals.get('default_code'):

                # Haal de inzending op
                submission = self.env['otters.consignment.submission'].browse(vals['submission_id'])

                if submission:
                    # Tel hoeveel producten er al zijn en doe +1
                    # (We gebruiken search_count voor de snelheid en zekerheid)
                    count = self.env['product.template'].with_context(active_test=False).search_count([
                        ('submission_id', '=', submission.id)
                    ])
                    next_seq = count + 1

                    # Genereer de code: BV. "YAME001-1"
                    vals['default_code'] = f"{submission.name}-{next_seq}"

        # Voer de standaard aanmaak uit
        return super(ProductTemplate, self).create(vals_list)

    @api.onchange('brand_id')
    def _onchange_brand_id(self):
        """ Koppel het gekozen merk aan de attributen-tab. """
        if not self.brand_id:
            return

        brand_attribute = self.env['product.attribute'].search([('name', '=ilike', 'Merk')], limit=1)
        if not brand_attribute: return

        val_name = self.brand_id.name
        brand_value = self.env['product.attribute.value'].search([
            ('attribute_id', '=', brand_attribute.id),
            ('name', '=ilike', val_name)
        ], limit=1)

        if not brand_value: return

        # Zoek de regel
        existing_line = False
        for line in self.attribute_line_ids:
            if line.attribute_id.id == brand_attribute.id:
                existing_line = line
                break

        # EXTRA BEVEILIGING: Schrijf alleen als het nog niet juist is
        new_ids = [brand_value.id]
        if existing_line:
            # Als de waarde al 'Woody' is, doe dan niets!
            if existing_line.value_ids.ids != new_ids:
                existing_line.value_ids = [(6, 0, new_ids)]
        else:
            self.attribute_line_ids = [(0, 0, {
                'attribute_id': brand_attribute.id,
                'value_ids': [(6, 0, new_ids)]
            })]

    @api.onchange('attribute_line_ids')
    def _onchange_attribute_line_ids(self):
        """ Koppel het gekozen kenmerk aan het merk-veld. """
        if not self.attribute_line_ids:
            return

        brand_line = False
        for line in self.attribute_line_ids:
            if line.attribute_id.name.lower() == 'merk' and line.value_ids:
                brand_line = line
                break

        if brand_line:
            brand_name = brand_line.value_ids[0].name
            brand_record = self.env['otters.brand'].search([('name', '=ilike', brand_name)], limit=1)

            # === DE LOOP BREKER ===
            # Als het merk al juist staat, STOP DAN!
            if brand_record and self.brand_id != brand_record:
                self.brand_id = brand_record

    # NIEUWE LOGICA: Als Marleen een reden kiest -> Stock 0 & Offline
    @api.onchange('x_unsold_reason')
    def _onchange_unsold_reason(self):
        if self.x_unsold_reason:
            self.is_published = False

    def write(self, vals):
        # 1. Voer de wijziging uit
        res = super(ProductTemplate, self).write(vals)

        # 2. Check of er een reden is ingevuld/gewijzigd
        if 'x_unsold_reason' in vals:
            for product in self:
                if product.x_unsold_reason:
                    # A. Zet offline
                    if product.is_published:
                        product.is_published = False

                    # B. Zet voorraad op 0 (via stock.quant)
                    # We doen dit voor alle varianten (meestal is er maar 1)
                    for variant in product.product_variant_ids:
                        self._zero_out_stock(variant)
        return res

    def _zero_out_stock(self, product_variant):
        """ Hulpfunctie om stock op 0 te zetten """
        # Zoek de hoofdlocatie
        warehouse = self.env['stock.warehouse'].search([], limit=1)
        if not warehouse: return
        location = warehouse.lot_stock_id

        # Zoek huidige quant
        quant = self.env['stock.quant'].search([
            ('product_id', '=', product_variant.id),
            ('location_id', '=', location.id)
        ], limit=1)

        # Als er voorraad is, pas aan naar 0
        if quant and quant.quantity > 0:
            quant.with_context(inventory_mode=True).write({'inventory_quantity': 0})
            quant.action_apply_inventory()
        elif not quant:
            # Als er nog geen quant bestaat, maak er eentje met 0 (voor de zekerheid)
            self.env['stock.quant'].with_context(inventory_mode=True).create({
                'product_id': product_variant.id,
                'location_id': location.id,
                'inventory_quantity': 0
            }).action_apply_inventory()

    def _compute_is_paid(self):
        for product in self:
            is_paid = self.env['sale.order.line'].search_count([
                ('product_template_id', '=', product.id),
                ('x_is_paid_out', '=', True),
                ('order_id.state', 'in', ['sale', 'done'])
            ])
            product.x_is_paid = (is_paid > 0)

    def _compute_payout_date(self):
        for product in self:
            line = self.env['sale.order.line'].search([
                ('product_template_id', '=', product.id),
                ('order_id.state', 'in', ['sale', 'done']),
                ('x_is_paid_out', '=', True)
            ], limit=1)

            if line:
                product.x_payout_date = line.x_payout_date or line.order_id.date_order.date()
            else:
                product.x_payout_date = False

    @api.constrains('public_categ_ids')
    def _check_category_type_sync(self):
        """ Sync Categorie -> Type Kenmerk """
        for product in self:
            # 1. Welk type hoort bij de gekozen categorie?
            linked_types = product.public_categ_ids.mapped('x_linked_type_value_id')
            if not linked_types:
                continue

            target_type_value = linked_types[0] # Pak de eerste
            type_attribute = target_type_value.attribute_id

            # 2. Check of product al een regel voor 'Type' heeft
            existing_line = product.attribute_line_ids.filtered(lambda l: l.attribute_id == type_attribute)

            if existing_line:
                # Update bestaande regel
                if target_type_value.id not in existing_line.value_ids.ids:
                    existing_line.write({'value_ids': [(6, 0, [target_type_value.id])]})
            else:
                # Maak nieuwe regel
                product.write({
                    'attribute_line_ids': [(0, 0, {
                        'attribute_id': type_attribute.id,
                        'value_ids': [(6, 0, [target_type_value.id])]
                    })]
                })

    def action_fix_split_sizes(self):
        """
        Zoekt naar attributen (Maat) met een '/' (bv 92/98) en splitst deze
        in twee aparte lijnen op het product (92 en 98).
        """
        attr_name = "Maat"

        # 1. Attribuut zoeken
        attribute = self.env['product.attribute'].search([('name', '=ilike', attr_name)], limit=1)
        if not attribute:
            raise UserError(_(f"Attribuut '{attr_name}' niet gevonden!"))

        # 2. Zoek waarden met een slash
        bad_values = self.env['product.attribute.value'].search([
            ('attribute_id', '=', attribute.id),
            ('name', 'like', '/')
        ])

        products_fixed_count = 0

        for bad_val in bad_values:
            # "122/128" -> ["122", "128"]
            new_size_names = [x.strip() for x in bad_val.name.split('/') if x.strip()]
            if not new_size_names:
                continue

            # Zoek alle attribute lines die deze foute waarde hebben
            # (Dit zoekt globaal over alle producten!)
            lines_to_fix = self.env['product.template.attribute.line'].search([
                ('attribute_id', '=', attribute.id),
                ('value_ids', 'in', bad_val.id)
            ])

            for line in lines_to_fix:
                product = line.product_tmpl_id

                # STAP A: Verwijder de oude lijn met "122/128"
                line.unlink()

                # STAP B: Maak voor elk nieuw deel een NIEUWE lijn
                for size_name in new_size_names:
                    # Zoek/Maak de waarde (122 of 128)
                    val_obj = self.env['product.attribute.value'].search([
                        ('attribute_id', '=', attribute.id),
                        ('name', '=', size_name)
                    ], limit=1)

                    if not val_obj:
                        val_obj = self.env['product.attribute.value'].create({
                            'name': size_name,
                            'attribute_id': attribute.id,
                            'sequence': 10
                        })

                    # Maak de nieuwe lijn aan op het product.
                    # FORCEER een nieuwe lijn (create) in plaats van toevoegen aan bestaande.
                    self.env['product.template.attribute.line'].create({
                        'product_tmpl_id': product.id,
                        'attribute_id': attribute.id,
                        'value_ids': [(6, 0, [val_obj.id])]
                    })

                products_fixed_count += 1

        # Return de actie voor de notificatie
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Splitsing Voltooid',
                'message': f'{products_fixed_count} producten zijn opgesplitst naar aparte regels.',
                'type': 'success',
                'sticky': False,
            }
        }