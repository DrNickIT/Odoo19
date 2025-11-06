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
        'portal',
    ],
    'data': [
        # 1. SECURITY & CONFIG (Moet EERST geladen worden)
        'security/ir_rule.xml',           # Access Rules (Record-niveau beveiliging)
        'security/ir.model.access.csv',   # ACL's (Model-niveau beveiliging)
        'data/config_data.xml',           # Systeemparameters (Payout percentages, Sendcloud)
        'data/product_attribute_data.xml',# Product Attributen

        # 2. BACKEND MODIFICATIES & WIZARDS (Modellen moeten nu geladen zijn)
        'views/res_partner_views.xml',    # Partner Formulier extensie
        'views/product_views_inherit.xml',# Product Formulier extensie (Maakt custom velden zichtbaar)
        'views/views.xml',                # Consignment Submission Model (Form/Tree/Menus)
        'reports/consignment_report_views.xml', # UI voor de SQL Rapportage
        'views/import_products_wizard_views.xml',
        'views/image_upload_wizard_views.xml',

        # 3. PRINT ACTIES & WEBLAYOUTS (Moet hier komen zodat alle modellen bestaan)
        'reports/product_labels.xml',

        # 4. PORTAAL & WEBSITE
        'views/templates.xml',            # Publieke Consignment formulier
        'views/portal_templates.xml',     # Portal Views (Mijn Inzendingen)
    ],
    'installable': True,
    'auto_install': False,
}
