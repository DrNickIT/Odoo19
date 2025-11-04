{
    'name': 'Otters Webshop Consignment',
    'version': '19.0.1.0.0',  # Odoo 19 versie
    'category': 'Website',
    'summary': 'A portal for consignments. People who send clothes to your shop to sell.',
    'license': 'LGPL-3',
    'author': 'Tom Hoornaert',
    'depends': [
        'website_sale',
        'website',
        'stock',
        'sale_management',
        'otters_webshop_outofstock_filter',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/product_attribute_data.xml',
        'views/import_products_wizard_views.xml',
        'views/views.xml',
        'views/product_views_inherit.xml',
        'data/config_data.xml',
        'views/res_partner_views.xml',
        'views/templates.xml',
        'reports/consignment_report_views.xml',
    ],
    'installable': True,
    'auto_install': False,
}
