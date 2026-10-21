# Copyright 2020 Camptocamp (https://www.camptocamp.com)
# Copyright 2020 Jacques-Etienne Baudoux (BCIM) <je@bcim.be>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from odoo.tests import Form, TransactionCase

from .common import TestGroupByBase


class TestGroupByPullRules(TestGroupByBase, TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # 18+ by default sets up the delivery routes as push rules.
        # We need to change the existing routes to pull as they were prior to 18 for
        # these tests.
        # We depend on stock_warehouse_out_pull for this.
        cls.env.ref("stock.warehouse0").delivery_pull = True

    def test_sale_stock_merge_same_partner_no_carrier(self):
        """2 sale orders for the same partner, without carrier

        -> the pickings are merged"""
        so1 = self._get_new_sale_order()
        so2 = self._get_new_sale_order(amount=11)
        so3 = self._get_new_sale_order(amount=12)
        so1.action_confirm()
        so2.action_confirm()
        so3.action_confirm()
        self.assertTrue(so1.picking_ids)
        self.assertEqual(so1.picking_ids, so2.picking_ids, so3.picking_ids)
        # the picking lists the stock references of the three sale orders
        self.assertEqual(
            so1.picking_ids.move_ids.reference_ids,
            so1.stock_reference_ids | so2.stock_reference_ids | so3.stock_reference_ids,
        )

    def test_sale_stock_merge_same_carrier(self):
        """2 sale orders for the same partner, with same carrier

        -> the pickings are merged"""
        so1 = self._get_new_sale_order(carrier=self.carrier1)
        so2 = self._get_new_sale_order(amount=11, carrier=self.carrier1)
        so1.action_confirm()
        so2.action_confirm()
        # there is a picking for the sales, and it is shared
        self.assertTrue(so1.picking_ids)
        self.assertEqual(so1.picking_ids, so2.picking_ids)
        # the origin of the picking mentions both sales names
        self.assertTrue(so1.name in so1.picking_ids[0].origin)
        self.assertTrue(so2.name in so1.picking_ids[0].origin)

    def test_sale_stock_no_merge_different_carrier(self):
        """2 sale orders for the same partner, with different carriers

        -> the pickings are not merged"""
        so1 = self._get_new_sale_order(carrier=self.carrier1)
        so2 = self._get_new_sale_order(amount=11, carrier=self.carrier2)
        so1.action_confirm()
        so2.action_confirm()
        self.assertEqual(so1.picking_ids.carrier_id, self.carrier1)
        self.assertEqual(so2.picking_ids.carrier_id, self.carrier2)
        self.assertNotEqual(so1.picking_ids, so2.picking_ids)
        self.assertTrue(so1.name in so1.picking_ids[0].origin)
        self.assertTrue(so2.name in so2.picking_ids[0].origin)

    def test_sale_stock_no_merge_carrier_set_only_on_one(self):
        """2 sale orders for the same partner, one with the other without

        -> the pickings are not merged"""
        so1 = self._get_new_sale_order(carrier=self.carrier1)
        so2 = self._get_new_sale_order(amount=11, carrier=None)
        so1.action_confirm()
        so2.action_confirm()
        self.assertEqual(so1.picking_ids.carrier_id, self.carrier1)
        self.assertFalse(so2.picking_ids.carrier_id)
        self.assertNotEqual(so1.picking_ids, so2.picking_ids)

    def test_sale_stock_no_merge_same_carrier_picking_policy_one_disabled(self):
        """2 sale orders for the same partner, with same carrier, deliver at
        once picking policy

        -> the pickings are not merged

        """
        so1 = self._get_new_sale_order(carrier=self.carrier1)
        so1.picking_policy = "one"
        so2 = self._get_new_sale_order(amount=11, carrier=self.carrier1)
        so2.picking_policy = "one"
        so1.action_confirm()
        so2.action_confirm()
        # there is a picking for each the sales, different
        self.assertTrue(so1.picking_ids)
        self.assertTrue(so2.picking_ids)
        self.assertNotEqual(so1.picking_ids, so2.picking_ids)
        # the origin of the picking mentions both sales names
        self.assertTrue(so1.name in so1.picking_ids[0].origin)
        self.assertTrue(so2.name in so2.picking_ids[0].origin)

    def test_sale_stock_no_merge_same_carrier_picking_policy_one_enabled(self):
        """2 sale orders for the same partner, with same carrier, deliver at
        once picking policy

        -> the pickings are merged

        """
        self.env.ref("stock.warehouse0").group_shippings_one = True
        so1 = self._get_new_sale_order(carrier=self.carrier1)
        so1.picking_policy = "one"
        so2 = self._get_new_sale_order(amount=11, carrier=self.carrier1)
        so2.picking_policy = "one"
        so1.action_confirm()
        so2.action_confirm()
        # there is a picking for each the sales, different
        self.assertTrue(so1.picking_ids)
        self.assertTrue(so2.picking_ids)
        self.assertEqual(so1.picking_ids, so2.picking_ids)
        # the origin of the picking mentions both sales names
        self.assertTrue(so1.name in so1.picking_ids[0].origin)
        self.assertTrue(so2.name in so2.picking_ids[0].origin)

    def test_sale_stock_no_merge_same_carrier_mixed_picking_policy(self):
        """2 sale orders for the same partner, with same carrier, deliver at once
        picking policy for the 1st sale order.

        -> the pickings are not merged

        """
        self.env.ref("stock.warehouse0").group_shippings_one = True
        so1 = self._get_new_sale_order(carrier=self.carrier1)
        so1.picking_policy = "one"
        so2 = self._get_new_sale_order(amount=11, carrier=self.carrier1)
        so1.action_confirm()
        so2.action_confirm()
        # there is a picking for each the sales, different
        self.assertTrue(so1.picking_ids)
        self.assertTrue(so2.picking_ids)
        self.assertNotEqual(so1.picking_ids, so2.picking_ids)
        # the origin of the picking mentions both sales names
        self.assertTrue(so1.name in so1.picking_ids[0].origin)
        self.assertTrue(so2.name in so2.picking_ids[0].origin)

    def test_printed_pick_no_merge(self):
        """1st sale order ship is printed, 2nd sale order not merged"""
        so1 = self._get_new_sale_order(carrier=self.carrier1)
        so1.action_confirm()
        so1.picking_ids.do_print_picking()
        so2 = self._get_new_sale_order(amount=11, carrier=self.carrier1)
        self.assertNotEqual(so1.picking_ids, so2.picking_ids)

    def test_backorder_picking_merge(self):
        """1st sale order ship is printed, 2nd sale order not merged.
        Partial delivery of so1

        -> backorder is merged with so2 picking

        """
        so1 = self._get_new_sale_order(carrier=self.carrier1)
        so1.action_confirm()
        so1.picking_ids.do_print_picking()
        so2 = self._get_new_sale_order(amount=11, carrier=self.carrier1)
        so2.action_confirm()
        pick = so1.picking_ids
        move = pick.move_ids[:1]
        move.quantity = 5
        move.picked = True
        pick.with_context(cancel_backorder=False)._action_done()
        so2.invalidate_recordset()
        self.assertTrue(so2.picking_ids & so1.picking_ids)
        self.assertEqual(so2.picking_ids.sale_ids, so1 + so2)

    def test_cancelling_sale_order1(self):
        """1st sale order is cancelled

        -> picking is still todo with only 1 stock move todo"""
        so1 = self._get_new_sale_order(carrier=self.carrier1)
        so1.action_confirm()
        so2 = self._get_new_sale_order(amount=11, carrier=self.carrier1)
        so2.action_confirm()
        self.assertTrue(so1.picking_ids)
        self.assertTrue(so2.picking_ids)
        self.assertEqual(so1.picking_ids, so2.picking_ids)
        so1._action_cancel()
        self.assertNotEqual(so1.picking_ids.state, "cancel")
        moves = so1.picking_ids.move_ids
        so1_moves = moves.filtered(lambda m: m.sale_line_id.order_id == so1)
        so2_moves = moves.filtered(lambda m: m.sale_line_id.order_id == so2)
        self.assertEqual(so1_moves.mapped("state"), ["cancel"])
        self.assertEqual(so2_moves.mapped("state"), ["confirmed"])
        self.assertEqual(so1.state, "cancel")
        self.assertEqual(so2.state, "sale")

    def test_cancelling_sale_order1_before_create_order2(self):
        """1st sale order is cancelled

        -> picking is still todo with only 1 stock move todo"""
        so1 = self._get_new_sale_order(carrier=self.carrier1)
        so1.action_confirm()
        so1._action_cancel()
        so2 = self._get_new_sale_order(amount=11, carrier=self.carrier1)
        so2.action_confirm()
        self.assertTrue(so1.picking_ids)
        self.assertTrue(so2.picking_ids)
        self.assertFalse(so1.picking_ids & so2.picking_ids)

    def test_cancelling_sale_order2(self):
        """2nd sale order is cancelled

        -> picking is still todo with only 1 stock move todo"""
        so1 = self._get_new_sale_order(carrier=self.carrier1)
        so1.action_confirm()
        so2 = self._get_new_sale_order(amount=11, carrier=self.carrier1)
        so2.action_confirm()
        self.assertTrue(so1.picking_ids)
        self.assertTrue(so2.picking_ids)
        self.assertEqual(so1.picking_ids, so2.picking_ids)
        so2._action_cancel()
        self.assertNotEqual(so1.picking_ids.state, "cancel")
        moves = so1.picking_ids.move_ids
        so1_moves = moves.filtered(lambda m: m.sale_line_id.order_id == so1)
        so2_moves = moves.filtered(lambda m: m.sale_line_id.order_id == so2)
        self.assertEqual(so1_moves.mapped("state"), ["confirmed"])
        self.assertEqual(so2_moves.mapped("state"), ["cancel"])
        self.assertEqual(so1.state, "sale")
        self.assertEqual(so2.state, "cancel")

    def test_delivery_multi_step(self):
        """the warehouse uses pick + ship

        -> shippings are grouped, pickings are not"""
        self.warehouse.delivery_steps = "pick_ship"
        so1 = self._get_new_sale_order(carrier=self.carrier1)
        so1.action_confirm()
        so2 = self._get_new_sale_order(amount=11, carrier=self.carrier1)
        so2.action_confirm()
        self.assertEqual(len(so1.picking_ids), 2)
        self.assertEqual(len(so2.picking_ids), 2)
        # ship should be shared between so1 and so2
        ships = so1.picking_ids & so2.picking_ids
        self.assertEqual(len(ships), 1)
        self.assertEqual(ships.picking_type_id, self.warehouse.out_type_id)
        # but not picks
        # Note: When grouping the ships, all pulled internal moves should also
        # be regrouped but this is currently not supported by this module. You
        # need the stock_available_to_promise_release module to have this
        # feature
        picks = so1.picking_ids - ships | so2.picking_ids - ships
        self.assertEqual(len(picks), 2)
        self.assertEqual(picks.picking_type_id, self.warehouse.pick_type_id)

        # the ships have the references of both sales, the picks the one of
        # their own sale
        self.assertEqual(
            ships.move_ids.reference_ids,
            so1.stock_reference_ids | so2.stock_reference_ids,
        )
        for pick in picks:
            self.assertEqual(
                pick.move_ids.reference_ids, pick.sale_ids.stock_reference_ids
            )

        # Add a line to so1
        self.assertEqual(len(ships.move_ids), 2)
        sale_form = Form(so1)
        self._set_line(sale_form, 4)
        sale_form.save()
        self.assertEqual(len(ships.move_ids), 3)
        # the ships have the references of both sales, the picks the one of
        # their own sale
        ships = so1.picking_ids & so2.picking_ids
        self.assertEqual(len(ships), 1)
        picks = so1.picking_ids - ships | so2.picking_ids - ships
        self.assertEqual(len(picks), 2)
        self.assertEqual(
            ships.move_ids.reference_ids,
            so1.stock_reference_ids | so2.stock_reference_ids,
        )
        for pick in picks:
            self.assertEqual(
                pick.move_ids.reference_ids, pick.sale_ids.stock_reference_ids
            )

        # Add a line to so2
        self.assertEqual(len(ships.move_ids), 3)
        self._set_line(sale_form, 4)
        sale_form.save()
        self.assertEqual(len(ships.move_ids), 4)
        # the ships have the references of both sales, the picks the one of
        # their own sale
        ships = so1.picking_ids & so2.picking_ids
        self.assertEqual(len(ships), 1)
        picks = so1.picking_ids - ships | so2.picking_ids - ships
        self.assertEqual(len(picks), 2)
        self.assertEqual(
            ships.move_ids.reference_ids,
            so1.stock_reference_ids | so2.stock_reference_ids,
        )
        for pick in picks:
            self.assertEqual(
                pick.move_ids.reference_ids, pick.sale_ids.stock_reference_ids
            )

    def test_delivery_multi_step_group_pick(self):
        """the warehouse uses pick + ship (with grouping enabled on pick)

        -> shippings are grouped, as well as pickings

        Note that the grouping of pickings cannot be enabled, the grouping
        option is only visible on the outgoing picking types. Grouping
        conditions are based on some data that are only available on the
        shipping."""
        self.warehouse.delivery_steps = "pick_ship"
        rule = self.env["stock.rule"]._get_rule(
            self.product,
            self.warehouse.pick_type_id.default_location_dest_id,
            {"warehouse_id": self.warehouse},
        )
        rule.propagate_carrier = False
        self.warehouse.pick_type_id.group_pickings = True
        so1 = self._get_new_sale_order(carrier=self.carrier1)
        so1.action_confirm()
        so2 = self._get_new_sale_order(amount=11, carrier=self.carrier1)
        so2.action_confirm()
        self.assertEqual(len(so1.picking_ids), 2)
        self.assertEqual(len(so2.picking_ids), 2)
        # ship & pick should be shared between so1 and so2
        self.assertEqual(so1.picking_ids, so2.picking_ids)
        transfers = so1.picking_ids
        self.assertEqual(len(transfers), 2)
        ships = transfers.filtered(
            lambda o: o.picking_type_id == self.warehouse.out_type_id
        )
        picks = transfers.filtered(
            lambda o: o.picking_type_id == self.warehouse.pick_type_id
        )
        self.assertEqual(len(ships), 1)
        self.assertEqual(len(picks), 1)
        self.assertFalse(so1.picking_ids - so2.picking_ids)

    def test_delivery_multi_step_cancel_so1(self):
        """the warehouse uses pick + ship. Cancel SO1

        -> shippings are grouped, pickings are not"""
        self.warehouse.delivery_steps = "pick_ship"
        rule = self.env["stock.rule"]._get_rule(
            self.product,
            self.warehouse.pick_type_id.default_location_dest_id,
            {"warehouse_id": self.warehouse},
        )
        rule.propagate_carrier = False
        so1 = self._get_new_sale_order(carrier=self.carrier1)
        so1.action_confirm()
        so2 = self._get_new_sale_order(amount=11, carrier=self.carrier1)
        so2.action_confirm()
        ships = (so1.picking_ids | so2.picking_ids).filtered(
            lambda p: p.picking_type_code == "outgoing"
        )
        pick1 = so1.order_line.move_ids.move_orig_ids.picking_id
        pick2 = so2.order_line.move_ids.move_orig_ids.picking_id
        so1._action_cancel()
        self.assertEqual(ships.state, "waiting")
        self.assertEqual(pick1.state, "cancel")
        self.assertEqual(pick2.state, "confirmed")

    def test_delivery_multi_step_cancel_so2(self):
        """the warehouse uses pick + ship. Cancel SO2

        -> shippings are grouped, pickings are not"""
        self.warehouse.delivery_steps = "pick_ship"
        rule = self.env["stock.rule"]._get_rule(
            self.product,
            self.warehouse.pick_type_id.default_location_dest_id,
            {"warehouse_id": self.warehouse},
        )
        rule.propagate_carrier = False
        so1 = self._get_new_sale_order(carrier=self.carrier1)
        so1.action_confirm()
        so2 = self._get_new_sale_order(amount=11, carrier=self.carrier1)
        so2.action_confirm()
        ships = (so1.picking_ids | so2.picking_ids).filtered(
            lambda p: p.picking_type_code == "outgoing"
        )
        pick1 = so1.order_line.move_ids.move_orig_ids.picking_id
        pick2 = so2.order_line.move_ids.move_orig_ids.picking_id
        so2._action_cancel()
        self.assertEqual(ships.state, "waiting")
        self.assertEqual(pick1.state, "confirmed")
        self.assertEqual(pick2.state, "cancel")

    def test_delivery_multi_step_group_pick_cancel_so1(self):
        """the warehouse uses pick + ship (with grouping enabled on pick)

        -> shippings are grouped, as well as pickings"""
        self.warehouse.delivery_steps = "pick_ship"
        self.warehouse.pick_type_id.group_pickings = True
        rule = self.env["stock.rule"]._get_rule(
            self.product,
            self.warehouse.pick_type_id.default_location_dest_id,
            {"warehouse_id": self.warehouse},
        )
        rule.propagate_carrier = False
        so1 = self._get_new_sale_order(carrier=self.carrier1)
        so1.action_confirm()
        so2 = self._get_new_sale_order(amount=11, carrier=self.carrier1)
        so2.action_confirm()
        so1._action_cancel()
        # ship & pick should be shared between so1 and so2
        transfers = so1.picking_ids
        ship = transfers.filtered(
            lambda o: o.picking_type_id == self.warehouse.out_type_id
        )
        pick = transfers.filtered(
            lambda o: o.picking_type_id == self.warehouse.pick_type_id
        )
        self.assertEqual(len(ship), 1)
        self.assertEqual(len(pick), 1)
        self.assertEqual(ship.state, "waiting")
        self.assertEqual(pick.state, "confirmed")

    def test_delivery_multi_step_group_pick_cancel_so2(self):
        """the warehouse uses pick + ship (with grouping enabled on pick)

        -> shippings are grouped, as well as pickings"""
        self.warehouse.delivery_steps = "pick_ship"
        self.warehouse.pick_type_id.group_pickings = True
        rule = self.env["stock.rule"]._get_rule(
            self.product,
            self.warehouse.pick_type_id.default_location_dest_id,
            {"warehouse_id": self.warehouse},
        )
        rule.propagate_carrier = False
        so1 = self._get_new_sale_order(carrier=self.carrier1)
        so1.action_confirm()
        so2 = self._get_new_sale_order(amount=11, carrier=self.carrier1)
        so2.action_confirm()
        so2._action_cancel()
        # ship & pick should be shared between so1 and so2
        transfers = so1.picking_ids
        ship = transfers.filtered(
            lambda o: o.picking_type_id == self.warehouse.out_type_id
        )
        pick = transfers.filtered(
            lambda o: o.picking_type_id == self.warehouse.pick_type_id
        )
        self.assertEqual(len(ship), 1)
        self.assertEqual(len(pick), 1)
        self.assertEqual(ship.state, "waiting")
        self.assertEqual(pick.state, "confirmed")

    def test_delivery_multi_step_cancel_so1_create_so3(self):
        """the warehouse uses pick + ship. Cancel SO1, create SO3

        -> shippings are grouped, pickings are not"""
        self.warehouse.delivery_steps = "pick_ship"
        rule = self.env["stock.rule"]._get_rule(
            self.product,
            self.warehouse.pick_type_id.default_location_dest_id,
            {"warehouse_id": self.warehouse},
        )
        rule.propagate_carrier = False
        so1 = self._get_new_sale_order(carrier=self.carrier1)
        so1.action_confirm()
        so2 = self._get_new_sale_order(amount=11, carrier=self.carrier1)
        so2.action_confirm()
        ships = (so1.picking_ids | so2.picking_ids).filtered(
            lambda p: p.picking_type_code == "outgoing"
        )
        so1._action_cancel()
        so3 = self._get_new_sale_order(amount=12, carrier=self.carrier1)
        so3.action_confirm()
        self.assertTrue(ships in so3.picking_ids)
        pick3 = so3.order_line.move_ids.move_orig_ids.picking_id
        self.assertEqual(len(pick3), 1)
        self.assertEqual(pick3.state, "confirmed")

    def test_delivery_mult_step_cancelling_sale_order1_before_create_order2(self):
        """1st sale order is cancelled

        -> picking is still todo with only 1 stock move todo"""
        so1 = self._get_new_sale_order(carrier=self.carrier1)
        so1.action_confirm()
        so1._action_cancel()
        so2 = self._get_new_sale_order(amount=11, carrier=self.carrier1)
        so2.action_confirm()
        self.assertTrue(so1.picking_ids)
        self.assertTrue(so2.picking_ids)
        self.assertFalse(so1.picking_ids & so2.picking_ids)

    def test_sale_stock_merge_references(self):
        """sales orders moves are merged, the picking has both references

        Ensure that the picking is linked with both SO
        and we find the stock.picking records from the SO.
        """
        so1 = self._get_new_sale_order(carrier=self.carrier1)
        so1.name = "SO1"
        so2 = self._get_new_sale_order(amount=11, carrier=self.carrier1)
        so2.name = "SO2"
        so1.action_confirm()
        so2.action_confirm()
        self.assertEqual(so1.picking_ids, so2.picking_ids)
        picking = so1.picking_ids
        # the picking holds the references of both sales orders
        self.assertEqual(
            picking.move_ids.reference_ids,
            so1.stock_reference_ids | so2.stock_reference_ids,
        )
        self.assertEqual(picking.sale_ids, so1 | so2)

        line = so1.order_line.filtered(lambda line: not line.is_delivery)

        self._update_qty_in_location(
            picking.location_id,
            line.product_id,
            line.product_uom_qty,
        )
        picking.action_assign()

        # process move of so1, we'll expect new backorders and new
        # transfers merged in the backorder to "forget" about so1
        move1 = picking.move_ids.filtered(
            lambda line: line.sale_line_id.order_id == so1
        )
        move1.quantity = move1.product_uom_qty
        move1.picked = True
        picking._action_done()

        backorder = picking.backorder_ids

        so3 = self._get_new_sale_order(carrier=self.carrier1)
        so3.name = "SO3"
        so3.action_confirm()

        # so3 moves are merged in the backorder used for so2,
        # the backorder holds the references of so2 and so3
        self.assertEqual(backorder.sale_ids, so2 | so3)
        self.assertEqual(
            backorder.move_ids.reference_ids,
            so2.stock_reference_ids | so3.stock_reference_ids,
        )

        # the orders are linked to the transfers that hold their moves
        self.assertEqual(so1.picking_ids, picking)
        self.assertEqual(so2.picking_ids, backorder)
        self.assertEqual(so3.picking_ids, backorder)

    def test_create_backorder(self):
        """Ensure there is no regression when group pickings is disabled when
        we confirm a partial qty on a picking to create a backorder.
        """
        so = self._get_new_sale_order(amount=10, carrier=self.carrier1)
        so.name = "SO TEST"
        so.action_confirm()
        picking = so.picking_ids
        picking.picking_type_id.group_pickings = False

        line = so.order_line.filtered(lambda line: not line.is_delivery)
        self._update_qty_in_location(
            picking.location_id,
            line.product_id,
            line.product_uom_qty,
        )
        picking.action_assign()
        line = picking.move_ids[:1]
        line.quantity = line.product_uom_qty / 2
        line.picked = True
        picking._action_done()
        self.assertEqual(picking.state, "done")
        self.assertTrue(picking.backorder_ids)
        self.assertNotEqual(picking, picking.backorder_ids)

    def test_create_backorder_partial_qty_keeps_move_lines(self):
        """A partially delivered move, with reserved lines, is backordered.

        The reserved move lines of the remaining quantity follow the move to
        the backorder.
        """
        so = self._get_new_sale_order(amount=10, carrier=self.carrier1)
        so.action_confirm()
        picking = so.picking_ids
        self.assertTrue(picking.picking_type_id.group_pickings)
        line = so.order_line.filtered(lambda line: not line.is_delivery)
        self._update_qty_in_location(
            picking.location_id, line.product_id, line.product_uom_qty
        )
        picking.action_assign()
        move = picking.move_ids.filtered(lambda m: m.sale_line_id == line)
        half = move.product_uom_qty / 2
        move.quantity = half
        move.picked = True
        picking._action_done()
        self.assertEqual(picking.state, "done")
        backorder = picking.backorder_ids
        self.assertEqual(len(backorder), 1)
        self.assertEqual(backorder.sale_ids, so)
        self.assertEqual(backorder.move_ids.product_uom_qty, half)
        self.assertEqual(backorder.move_line_ids.picking_id, backorder)

    def test_create_backorder_references(self):
        """Ensure the backorder references only the remaining moves.

        The sale orders delivered in the original picking stay linked to it
        and are not linked to the backorder.
        """
        so1 = self._get_new_sale_order()
        so2 = self._get_new_sale_order(amount=11)
        so3 = self._get_new_sale_order(amount=12)
        so1.action_confirm()
        so2.action_confirm()
        so3.action_confirm()

        picking = so1.picking_ids | so2.picking_ids | so3.picking_ids
        line = so1.order_line.filtered(lambda line: not line.is_delivery)

        self._update_qty_in_location(
            picking.location_id,
            line.product_id,
            line.product_uom_qty,
        )

        self.assertEqual(len(picking), 1)
        picking.action_assign()

        # partially process the picking for line from so1
        move = picking.move_ids.filtered(lambda m: m.sale_line_id.order_id == so1)
        move.move_line_ids.picked = True
        picking._action_done()
        backorder = picking.backorder_ids
        self.assertTrue(backorder)
        self.assertEqual(len(backorder), 1)
        self.assertEqual(picking.move_ids.reference_ids, so1.stock_reference_ids)
        self.assertEqual(
            backorder.move_ids.reference_ids,
            so2.stock_reference_ids | so3.stock_reference_ids,
        )
        self.assertEqual(backorder.sale_ids, so2 | so3)
