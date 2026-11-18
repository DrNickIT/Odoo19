import json
import re

from odoo import http
from odoo.http import request


_STORAGE_CODE_RE = re.compile(r'^[A-Za-z0-9_-]+$')


class StorageScanController(http.Controller):
    @staticmethod
    def _is_internal_user():
        user = request.env.user
        return user.has_group('base.group_user') and not user.has_group('base.group_portal')

    @http.route(
        '/otters/storage/scan',
        type='http',
        auth='user',
        methods=['GET'],
        website=True,
        sitemap=False,
    )
    def storage_scan_page(self, **kwargs):
        if not self._is_internal_user():
            return request.not_found()
        return request.render('otters_consignment.storage_scan_page')

    @http.route(
        '/otters/storage/assign',
        type='http',
        auth='user',
        methods=['POST'],
        website=True,
        sitemap=False,
    )
    def storage_scan_assign(self, product_code=None, bag_code=None, confirm_move=None, **kwargs):
        if not self._is_internal_user():
            return self._json_response({'ok': False, 'message': 'Geen toegang.'}, status=403)

        product_code = (product_code or '').strip().upper()
        bag_code = (bag_code or '').strip().upper()
        if not _STORAGE_CODE_RE.fullmatch(product_code):
            return self._json_response({
                'ok': False,
                'message': 'Vul een geldige productcode of barcode in.',
            })
        if not _STORAGE_CODE_RE.fullmatch(bag_code):
            return self._json_response({
                'ok': False,
                'message': 'Vul een geldige zakcode in.',
            })

        product, error = self._find_product(product_code)
        if error:
            return self._json_response({'ok': False, 'message': error})

        current_bag = product.storage_bag_id
        if current_bag and current_bag.code != bag_code and confirm_move not in ('1', 'true', 'True'):
            return self._json_response({
                'ok': False,
                'needs_confirmation': True,
                'message': (
                    f'{product.default_code} zit momenteel in zak {current_bag.code}. '
                    f'Wil je het product verplaatsen naar zak {bag_code}?'
                ),
            })

        Bag = request.env['otters.storage.bag'].sudo()
        bag = Bag.search([('code', '=', bag_code)], limit=1)
        if not bag:
            bag = Bag.create({'code': bag_code})

        product.sudo().write({'storage_bag_id': bag.id})
        return self._json_response({
            'ok': True,
            'message': f'{product.default_code or product.name} is gekoppeld aan zak {bag.code}.',
            'product_code': product.default_code or product_code,
            'bag_code': bag.code,
        })

    @staticmethod
    def _find_product(code):
        Product = request.env['product.product'].sudo().with_context(active_test=False)
        variants = Product.search([('barcode', '=ilike', code)])
        templates = variants.mapped('product_tmpl_id')
        if len(templates) > 1:
            return False, f'Meer dan één product heeft barcode {code}.'
        if templates:
            return templates[0], False

        Template = request.env['product.template'].sudo().with_context(active_test=False)
        templates = Template.search([('default_code', '=ilike', code)], limit=2)
        if not templates:
            variants = Product.search([('default_code', '=ilike', code)], limit=2)
            templates = variants.mapped('product_tmpl_id')

        if not templates:
            return False, f'Geen product gevonden met barcode of productcode {code}.'
        if len(templates) > 1:
            return False, f'Meer dan één product heeft productcode {code}.'
        return templates[0], False

    @staticmethod
    def _json_response(data, status=200):
        return request.make_response(
            json.dumps(data),
            headers=[('Content-Type', 'application/json')],
            status=status,
        )
