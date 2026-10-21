# Copyright 2020 Camptocamp (https://www.camptocamp.com)
# Copyright 2020 Jacques-Etienne Baudoux (BCIM) <je@bcim.be>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from itertools import groupby

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class StockPicking(models.Model):
    _inherit = "stock.picking"

    sale_ids = fields.Many2many(
        comodel_name="sale.order",
        relation="sale_order_stock_picking_rel",
        column1="picking_id",
        column2="order_id",
        compute="_compute_sale_ids",
        store=True,
    )
    canceled_by_merge = fields.Boolean(
        default=False,
        help="Technical field. Indicates the transfer is"
        " canceled because it was left empty after a manual merge.",
    )

    @api.model
    def _get_index_for_grouping_fields(self):
        """
        This tuple is intended to be overriden in order to add fields
        used in groupings
        """
        res = super()._get_index_for_grouping_fields()
        if "carrier_id" not in res:
            res.append("carrier_id")
        return res

    def init(self):
        """
        This has to be called in every overriding module
        """
        self._create_index_for_grouping()

    @api.depends("canceled_by_merge")
    def _compute_state(self):
        super()._compute_state()
        for picking in self:
            if picking.canceled_by_merge:
                picking.state = "cancel"
        return

    def _check_emptyness_after_merge(self):
        """Handle pickings emptied during a manual merge."""
        for picking in self:
            if not picking.move_ids:
                picking.canceled_by_merge = True

    @api.depends("move_ids.sale_line_id.order_id")
    def _compute_sale_ids(self):
        for rec in self:
            rec.sale_ids = rec.move_ids.sale_line_id.order_id

    @api.depends("move_ids.sale_line_id.order_id")
    def _compute_sale_id(self):
        # A transfer shared by several orders is linked to all of them through
        # sale_ids. The single sale order of the standard is the first one.
        for picking in self:
            picking.sale_id = picking.move_ids.sale_line_id.order_id[:1]

    def write(self, values):
        if self.env.context.get("picking_no_overwrite_partner_origin"):
            written_fields = set(values.keys())
            if written_fields == {"partner_id", "origin"}:
                values = {}
        return super().write(values)

    def action_cancel(self):
        # When a SO is canceled, cancel only moves related to this SO and not
        # all moves of the picking
        cancel_reference_ids = self.env.context.get("cancel_sale_reference_ids")
        if cancel_reference_ids:
            moves = self.move_ids.filtered(
                lambda m: set(m.reference_ids.ids) & set(cancel_reference_ids)
                and m.state not in ("done", "cancel")
            )
            moves.with_context(cancel_sale_reference_ids=False)._action_cancel()
            return True
        else:
            return super().action_cancel()

    def _create_backorder(self, backorder_moves=None):
        backorders = self.browse()
        bo_to_assign = self.browse()
        if picking_no_grouping := self.filtered(lambda p: p._is_grouping_disabled()):
            backorders += super(StockPicking, picking_no_grouping)._create_backorder(
                backorder_moves=backorder_moves
            )
        if picking_grouping := self - picking_no_grouping:
            moves = picking_grouping.move_ids
            for old_picking in moves.picking_id:
                if backorder_moves:
                    moves_to_backorder = backorder_moves.filtered(
                        lambda m, old_picking=old_picking: m.picking_id == old_picking
                    )
                else:
                    moves_to_backorder = old_picking._get_moves_to_backorder()
                if not moves_to_backorder:
                    continue
                moves_to_backorder._recompute_state()
                moves_to_backorder.filtered("picked").picked = False
                moves_to_backorder.with_context(
                    _assign_picking_excluded=old_picking
                )._assign_picking()
                for new_picking, moves in moves_to_backorder.grouped(
                    "picking_id"
                ).items():
                    if old_picking == new_picking:
                        raise UserError(
                            self.env._(
                                "Backorder moves cannot be assigned to the same picking"
                            )
                        )
                    backorders |= new_picking

                    move_lines = moves.move_line_ids.filtered(
                        lambda ml, new_picking=new_picking: ml.picking_id != new_picking
                    )
                    if move_lines:
                        # The package levels of Odoo 18 do not exist anymore
                        move_lines.picking_id = new_picking

                    if not new_picking.backorder_id:
                        new_picking.backorder_id = old_picking
                    old_picking.message_post(
                        body=_(
                            "The backorder %s has been created.",
                            new_picking._get_html_link(),
                        )
                    )

                    if new_picking.picking_type_id.reservation_method == "at_confirm":
                        bo_to_assign |= new_picking
        if bo_to_assign:
            bo_to_assign.action_assign()
        return backorders

    def _prepare_merged_origin(self):
        """Concatenate all origin together.
        Note that in standard, only max 5 are displayed"""
        moves = self.move_ids.filtered(lambda m: m.state != "cancel")
        origins = moves.filtered(lambda m: m.origin).mapped("origin")
        origins = sorted(list(set(origins)))
        return " ".join(origins)

    def _update_merged_origin(self):
        self.origin = self._prepare_merged_origin()

    def _is_merged_by_assignation(self, new_moves):
        """Tell if moves of another stock reference were added to the transfer.

        :param new_moves: the moves that were just assigned to the transfer
        """
        self.ensure_one()
        if self._is_grouping_disabled():
            return False
        previous_moves = self.move_ids - new_moves
        return not previous_moves or bool(
            new_moves.reference_ids - previous_moves.reference_ids
        )

    def _is_grouping_disabled(self):
        self.ensure_one()
        return (
            not self.picking_type_id.group_pickings
            or self.partner_id.disable_picking_grouping
            or (not self.picking_type_id.group_pickings_one and self.move_type == "one")
        )

    def _group_moves_by_order(self, moves):
        # Meant to be overridden
        return groupby(moves, lambda m: m.sale_line_id.order_id)

    def _get_sorted_moves(self):
        # Meant to be overriden
        self.ensure_one()
        moves = self.move_ids.filtered(lambda m: m.state != "cancel")
        return moves.sorted(lambda m: m.sale_line_id.order_id.id)

    def _get_sorted_move_lines(self):
        # Meant to be overriden
        self.ensure_one()
        return self.move_line_ids

    def _delivery_report_state_is_done(self):
        return self.state == "done"

    def get_delivery_report_lines(self):
        """Return the lines that will be on the report.

        If the picking concerns multiple sale order some fake records are
        inserted to have the sale information as line separators.
        Otherwise standard records are returned.
        """
        self.ensure_one()
        moves = self._get_sorted_moves()
        if not self._delivery_report_state_is_done():
            moves = moves.filtered("quantity")

        if len(moves.mapped("sale_line_id.order_id")) > 1:
            grouped_moves = self._group_moves_by_order(moves)
            fake_record = {
                "product_id": 1,
                "product_uom_qty": 0,
                "product_uom": self.env.ref("uom.product_uom_unit").id,
                "company_id": self.env.user.company_id.id,
                "location_id": self.env.ref("stock.stock_location_output").id,
                "location_dest_id": self.env.ref("stock.stock_location_output").id,
            }
            if not self._delivery_report_state_is_done():
                sales_and_moves = self.env["stock.move"]
                for sale, sale_moves in grouped_moves:
                    line_desc = sale.get_name_for_delivery_line()
                    fake_record.update(
                        {"description_picking": line_desc, "origin": sale.name}
                    )
                    sales_and_moves |= sales_and_moves.new(fake_record.copy())
                    for move in sale_moves:
                        sales_and_moves |= move
                return sales_and_moves
            else:
                sales_and_moves = self.env["stock.move.line"]
                fake_record["quantity"] = fake_record.pop("product_uom_qty")
                fake_record["product_uom_id"] = fake_record.pop("product_uom")
                for sale, sale_moves in grouped_moves:
                    if sale:
                        line_desc = sale.get_name_for_delivery_line()
                        fake_record.update(
                            {"description_picking": line_desc, "origin": sale.name}
                        )
                        sales_and_moves |= sales_and_moves.new(fake_record.copy())
                    for move in sale_moves:
                        for move_line in move.move_line_ids:
                            sales_and_moves |= move_line
                return sales_and_moves
        elif not self._delivery_report_state_is_done():
            return moves
        else:
            return self._get_sorted_move_lines()

    def get_delivery_report_aggregated_groups(self):
        """Return the move lines to print for a done transfer, by sale order.

        The quantities of a done transfer are aggregated by product. When the
        transfer concerns several sale orders, they are aggregated for each
        order, which is shown by the title of the group.
        """
        self.ensure_one()
        move_lines = self.move_line_ids
        orders = move_lines.move_id.sale_line_id.order_id
        if len(orders) <= 1:
            return [{"title": False, "move_lines": move_lines}]
        groups = []
        for order in orders.sorted("id"):
            groups.append(
                {
                    "title": order.get_name_for_delivery_line(),
                    "move_lines": move_lines.filtered(
                        lambda ml, order=order: ml.move_id.sale_line_id.order_id
                        == order
                    ),
                }
            )
        other_lines = move_lines.filtered(
            lambda ml: not ml.move_id.sale_line_id.order_id
        )
        if other_lines:
            groups.append({"title": False, "move_lines": other_lines})
        return groups

    def get_customer_refs(self):
        """Returns all unique sales order customer references."""
        if self._delivery_report_state_is_done():
            move_ids = self.move_ids
        else:
            move_ids = self.move_ids.filtered("product_uom_qty")
        references = move_ids.mapped("sale_line_id.order_id.client_order_ref")
        return set(filter(None, references))
