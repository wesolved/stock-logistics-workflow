# Copyright 2021 Camptocamp (https://www.camptocamp.com)
# Copyright 2025 Jacques-Etienne Baudoux (BCIM) <je@bcim.be>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from odoo.tests.common import TransactionCase

from .common import TestGroupByBase


class TestReport(TestGroupByBase, TransactionCase):
    def _set_qty_only_in_location(self, location, product, qty):
        for other_location in self.env["stock.location"].search(
            [("usage", "!=", "view"), ("id", "!=", location.id)]
        ):
            self._update_qty_in_location(other_location, product, 0)
        self._update_qty_in_location(location, product, qty)
        self.assertEqual(product.qty_available, qty)

    def make_downpayment(self, sale_order):
        so_context = {
            "active_model": "sale.order",
            "active_ids": [sale_order.id],
            "active_id": sale_order.id,
        }
        payment_params = {
            "advance_payment_method": "percentage",
            "amount": 50,
        }
        downpayment = (
            self.env["sale.advance.payment.inv"]
            .with_context(**so_context)
            .create(payment_params)
        )
        downpayment.create_invoices()

    def test_get_remaining_to_deliver_nondelivered_line(self):
        """One sale with two lines, one of them non delivered"""
        report = self.env["report.stock.report_deliveryslip"]

        stock_location = self.env.ref("stock.stock_location_stock")

        # SO1 has 5 units of product1, we have 3 in stock;
        # and has 7 units of product2, we have 0 in stock.
        so = self._get_new_sale_order(amount=5)
        self.make_downpayment(so)
        prod1 = so.order_line[0].product_id
        self.assertEqual(prod1, self.env.ref("product.product_delivery_01"))
        prod2 = self.env.ref("product.product_delivery_02")
        self.env["sale.order.line"].create(
            {
                "order_id": so.id,
                "name": prod2.name,
                "product_id": prod2.id,
                "product_uom_qty": 7,
                "product_uom_id": prod2.uom_id.id,
                "price_unit": prod2.list_price,
            }
        )
        self._set_qty_only_in_location(stock_location, prod1, 3)
        self._set_qty_only_in_location(stock_location, prod2, 0)
        self.assertEqual(len(so.order_line.filtered("product_id")), 2)
        so.action_confirm()

        self.assertEqual(len(so.picking_ids), 1)
        picking = so.picking_ids
        remaining_data = report.get_remaining_to_deliver(picking)
        self.assertEqual(len(remaining_data), 0)

        self._validate_transfer(picking)
        remaining_data = report.get_remaining_to_deliver(picking)
        self.assertEqual(len(remaining_data), 3)

        self.assertTrue(remaining_data[0]["is_header"])
        self.assertEqual(remaining_data[0]["concept"], so.name)
        self.assertFalse(remaining_data[1]["is_header"])
        self.assertEqual(remaining_data[1]["qty"], 2)
        self.assertFalse(remaining_data[2]["is_header"])
        self.assertEqual(remaining_data[2]["qty"], 7)

    def test_get_remaining_to_deliver_two_sales(self):
        """Two sales that combine into one picking"""
        report = self.env["report.stock.report_deliveryslip"]

        stock_location = self.env.ref("stock.stock_location_stock")

        # SO1 has 5 units of product_delivery_01, we have 3 in stock,
        # so 5-3=2 will be pending.
        so1 = self._get_new_sale_order(amount=5)
        prod_so1 = so1.order_line[0].product_id
        self.assertEqual(prod_so1, self.env.ref("product.product_delivery_01"))
        self._set_qty_only_in_location(stock_location, prod_so1, 3)

        # SO2 has 10 units of product_delivery_02, we have 4 in stock,
        # so 10-4=6 will be pending.
        so2 = self._get_new_sale_order(amount=10)
        prod_so2 = self.env.ref("product.product_delivery_02")
        so2.order_line[0].update(
            {
                "name": prod_so2.name,
                "product_id": prod_so2.id,
                "product_uom_id": prod_so2.uom_id.id,
                "price_unit": prod_so2.list_price,
            }
        )
        self._set_qty_only_in_location(stock_location, prod_so2, 4)

        so1.action_confirm()
        so2.action_confirm()

        self.assertEqual(set(so1.picking_ids.ids), set(so2.picking_ids.ids))
        self.assertEqual(len(so1.picking_ids), 1)
        picking = so1.picking_ids
        self.assertEqual(len(picking.move_line_ids), 2)

        remaining_data = report.get_remaining_to_deliver(picking)
        self.assertEqual(len(remaining_data), 0)

        self._validate_transfer(picking)
        remaining_data = report.get_remaining_to_deliver(picking)
        self.assertEqual(len(remaining_data), 4)

        self.assertTrue(remaining_data[0]["is_header"])
        self.assertEqual(remaining_data[0]["concept"], so1.name)
        self.assertFalse(remaining_data[1]["is_header"])
        self.assertEqual(remaining_data[1]["qty"], 2)
        self.assertTrue(remaining_data[2]["is_header"])
        self.assertEqual(remaining_data[2]["concept"], so2.name)
        self.assertFalse(remaining_data[3]["is_header"])
        self.assertEqual(remaining_data[3]["qty"], 6)

    def test_delivery_report_lines_two_sales_merged(self):
        """Check report lines for two sale orders merged in same picking."""
        so1 = self._get_new_sale_order()
        so2 = self._get_new_sale_order(amount=11)
        so1.action_confirm()
        so2.action_confirm()
        picking = so1.picking_ids
        # No qty reserved thus nothing to print
        res = picking.get_delivery_report_lines()
        self.assertEqual(len(res), 0)
        self.assertEqual(res._name, "stock.move")
        # Reserve goods and test again
        self._update_qty_in_location(
            picking.location_id,
            so1.order_line[0].product_id,
            so1.order_line[0].product_uom_qty,
        )
        self._update_qty_in_location(
            picking.location_id,
            so2.order_line[0].product_id,
            so2.order_line[0].product_uom_qty,
        )
        picking.action_assign()
        # Check that we have two display moves (sale name)
        # And two real moves.
        res = picking.get_delivery_report_lines()
        self.assertFalse(res[0].id)
        self.assertTrue(res[1].id)
        self.assertFalse(res[2].id)
        self.assertTrue(res[3].id)
        # Deliver and test again
        line = picking.move_ids[0]
        line.picked = True
        line = picking.move_ids[1]
        line.picked = True
        res = picking._action_done()
        self.assertEqual(picking.state, "done")
        res = picking.get_delivery_report_lines()
        self.assertEqual(len(res), 4)
        self.assertEqual(res._name, "stock.move.line")
        # Check that we have two display moves (sale name)
        # And two real moves.
        self.assertFalse(res[0].id)
        self.assertTrue(res[1].id)
        self.assertFalse(res[2].id)
        self.assertTrue(res[3].id)

    def _prepare_two_sales_picking(self):
        so1 = self._get_new_sale_order()
        so2 = self._get_new_sale_order(amount=11)
        so1.action_confirm()
        so2.action_confirm()
        picking = so1.picking_ids
        self.assertEqual(picking, so2.picking_ids)
        for so in (so1, so2):
            self._update_qty_in_location(
                picking.location_id,
                so.order_line[0].product_id,
                so.order_line[0].product_uom_qty,
            )
        picking.action_assign()
        return so1, so2, picking

    def _render_delivery_slip(self, picking):
        report = self.env.ref("stock.action_report_delivery")
        html, _report_type = report._render_qweb_html(report.report_name, picking.ids)
        return html.decode() if isinstance(html, bytes) else html

    def test_delivery_slip_render_two_sales(self):
        """The delivery slip of a picking shared by two sales has a separator
        row with the name of each sale, before and after the delivery."""
        so1, so2, picking = self._prepare_two_sales_picking()
        html = self._render_delivery_slip(picking)
        self.assertIn(so1.name, html)
        self.assertIn(so2.name, html)
        for move in picking.move_ids:
            move.picked = True
        picking._action_done()
        self.assertEqual(picking.state, "done")
        html = self._render_delivery_slip(picking)
        self.assertIn(so1.name, html)
        self.assertIn(so2.name, html)

    def test_delivery_report_aggregated_groups(self):
        """The aggregated lines of a done picking are grouped by sale order."""
        so1, so2, picking = self._prepare_two_sales_picking()
        for move in picking.move_ids:
            move.picked = True
        picking._action_done()
        groups = picking.get_delivery_report_aggregated_groups()
        self.assertEqual([group["title"] for group in groups], [so1.name, so2.name])
        for group, so in zip(groups, so1 | so2, strict=True):
            self.assertEqual(
                group["move_lines"].move_id.sale_line_id.order_id,
                so,
            )

    def test_delivery_report_aggregated_groups_one_sale(self):
        """A picking of a single sale has no title for its lines."""
        so = self._get_new_sale_order()
        so.action_confirm()
        picking = so.picking_ids
        groups = picking.get_delivery_report_aggregated_groups()
        self.assertEqual(len(groups), 1)
        self.assertFalse(groups[0]["title"])
