{
    'name': 'Otters Webshop Sold Out Stock Filter',
    'version': '19.0.1.0.0',  # Odoo 19 versie
    'category': 'Website',
    'license': 'LGPL-3',
    'summary': 'Hides products that are not in stock anymore (qty > 0 EN virtual > 0).',
    'author': 'Tom Hoornaert',
    'depends': [
        'website_sale',
        'website_sale_stock',
        'stock',
    ],
    'data': [
        'security/ir.model.access.csv',
        'security/ir_rule.xml',
    ],
    'installable': True,
    'auto_install': False,
}
