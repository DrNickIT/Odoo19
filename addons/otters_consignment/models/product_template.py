# In models/product_template.py
from odoo import models, fields

class ProductTemplate(models.Model):
    _inherit = 'product.template'

    _sql_constraints_default_code_unique = models.SQLConstraint(
        'default_code_unique',
        'UNIQUE(default_code)',
        'De interne referentie (code) van het product moet uniek zijn!'
    )

    submission_id = fields.Many2one(
        'otters.consignment.submission',
        string="Originele Inzending",
        ondelete='set null'
    )

    consignment_attribute_values_ids = fields.Many2many(
        'product.attribute.value',
        string="Kenmerken Waarden",
        compute='_compute_consignment_attribute_values_ids',
        store=False, # Niet opslaan, wordt dynamisch berekend
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
