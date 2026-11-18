from odoo import api, fields, models


class StorageBag(models.Model):
    _name = 'otters.storage.bag'
    _description = 'Opbergzak'
    _rec_name = 'code'
    _order = 'code'

    _sql_constraints = [
        ('code_unique', 'UNIQUE(code)', 'Deze zakcode bestaat al.'),
    ]

    code = fields.Char(string='Zakcode', required=True, index=True)
    product_ids = fields.One2many(
        'product.template',
        'storage_bag_id',
        string='Producten',
    )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('code'):
                vals['code'] = vals['code'].strip().upper()
        return super().create(vals_list)

    def write(self, vals):
        vals = vals.copy()
        if vals.get('code'):
            vals['code'] = vals['code'].strip().upper()
        return super().write(vals)
