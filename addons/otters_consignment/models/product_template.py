# In models/product_template.py
from odoo import models, fields, api

class ProductTemplate(models.Model):
    _inherit = 'product.template'

    _sql_constraints = [
        ('default_code_unique',
         'UNIQUE(default_code)',
         'De interne referentie (code) van het product moet uniek zijn!')
    ]

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
                    count = self.env['product.template'].search_count([
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