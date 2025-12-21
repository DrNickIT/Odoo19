import json
import logging
from odoo import http, _
from odoo.http import request

_logger = logging.getLogger(__name__)

class SendcloudController(http.Controller):

    @http.route(['/sendcloud/webhook'], type='http', auth='public', methods=['POST'], csrf=False)
    def sendcloud_webhook(self, **post):
        try:
            data = json.loads(request.httprequest.data)
            action = data.get('action')
            parcel = data.get('parcel')

            if action == 'parcel_status_changed' and parcel:
                tracking_number = parcel.get('tracking_number')
                new_status = parcel.get('status', {}).get('message')

                picking = request.env['stock.picking'].sudo().search([
                    ('carrier_tracking_ref', '=', tracking_number)
                ], limit=1)

                if picking:
                    picking.message_post(
                        body=f"Sendcloud Status Update: {new_status}",
                        message_type="notification"
                    )
            return "OK"

        except Exception as e:
            _logger.error(f"Fout bij verwerken Sendcloud webhook: {str(e)}")
            return "Error", 500

    @http.route('/shop/sendcloud/save_service_point', type='jsonrpc', auth="public", website=True)
    def save_service_point(self, service_point_id, service_point_name, **kw):
        sale_order_id = request.session.get('sale_order_id')
        if sale_order_id:
            order = request.env['sale.order'].sudo().browse(sale_order_id)
            if order.exists():
                order.write({
                    'sendcloud_service_point_id': service_point_id,
                    'sendcloud_service_point_name': service_point_name
                })
                return {'success': True}
        return {'success': False}