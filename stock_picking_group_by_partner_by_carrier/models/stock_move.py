# Copyright 2020 Camptocamp (https://www.camptocamp.com)
# Copyright 2020 Jacques-Etienne Baudoux (BCIM) <je@bcim.be>
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from collections import namedtuple

from odoo import api, models
from odoo.tools import groupby


class StockMove(models.Model):
    _inherit = "stock.move"

    @api.model
    def _prepare_merge_moves_distinct_fields(self):
        # Prevent merging moves of different stock references. The moves of
        # a transfer shared by several orders then stay apart, which allows to
        # cancel a SO without canceling the moves of the other SO.
        return super()._prepare_merge_moves_distinct_fields() + ["reference_ids"]

    def _assign_picking(self):
        result = super(
            StockMove, self.with_context(picking_no_overwrite_partner_origin=1)
        )._assign_picking()
        return result

    def _assign_picking_post_process(self, new=False):
        moves_by_picking = groupby(self, key=lambda m: m.picking_id)
        for picking, imoves in moves_by_picking:
            moves = self.browse(m.id for m in imoves)
            if picking._is_merged_by_assignation(moves):
                picking._update_merged_origin()
                moves._on_assign_picking_message_link()
        # Ensure sale.order.picking_ids is properly read to ensure
        # action_confirm is called.
        # The m2m relation from stock.picking to sale.order is a stored
        # computed field with depends but the reverse relation is not defined
        # as computed, so we need to flush the stored computed field so that
        # any read from sale.order will fetch the right value.
        self.picking_id.flush_recordset(["sale_ids"])
        res = super()._assign_picking_post_process(new=new)
        return res

    def _on_assign_picking_message_link(self):
        sales = self.sale_line_id.order_id
        if sales:
            self.picking_id.message_post_with_source(
                "mail.message_origin_link",
                render_values={"self": self.picking_id, "origin": sales, "edit": True},
                subtype_xmlid="mail.mt_note",
            )

    def _get_grouping_move_type(self):
        """Shipping policy of the move.

        By default it is the one of the sale order, then the one of the
        operation type. Override to customize this behavior.
        """
        self.ensure_one()
        sale_order = self.sale_line_id.order_id[:1]
        return sale_order.picking_policy or self.picking_type_id.move_type or "direct"

    def _get_grouping_carrier(self):
        """Carrier of the move, taken from its stock references."""
        self.ensure_one()
        return self.reference_ids.carrier_id[:1]

    def _is_grouping_disabled(self):
        self.ensure_one()
        return (
            not self.picking_type_id.group_pickings
            or self.partner_id.disable_picking_grouping
            or (
                not self.picking_type_id.group_pickings_one
                and self._get_grouping_move_type() == "one"
            )
        )

    def _search_picking_for_assignation_domain(self):
        domain = super()._search_picking_for_assignation_domain()
        if self._is_grouping_disabled():
            return domain

        # The transfer is not searched on the references of the move, so the
        # moves of several orders can share one
        domain = [leaf for leaf in domain if leaf[0] not in ("reference_ids",)]
        return domain + self._assign_picking_group_domain()

    # TODO: this part and everything related to generic grouping
    # should be split into `stock_picking_group_by` module.
    def _assign_picking_group_domain(self):
        domain = [
            # same partner
            ("partner_id", "=", self.partner_id.id),
            # don't search on the stock references
        ]
        domain += self._domain_search_picking_handle_move_type()
        # same carrier only for outgoing transfers
        if self.picking_type_id.code == "outgoing":
            domain += [
                ("carrier_id", "=", self._get_grouping_carrier().id),
            ]
        if excluded_picking := self.env.context.get("_assign_picking_excluded"):
            # we are in the context of the creation of a backorder:
            # don't consider the current move's picking
            domain.append(("id", "!=", excluded_picking.id))
        return domain

    def _domain_search_picking_handle_move_type(self):
        """Hook to handle the move type.

        By default the move type is taken from the sale order.
        Override to customize this behavior.
        """
        return [("move_type", "=", self._get_grouping_move_type())]

    def _key_assign_picking(self):
        return (
            self.partner_id,
            self._get_grouping_carrier(),
            PickingPolicy(id=self._get_grouping_move_type()),
        ) + super()._key_assign_picking()


PickingPolicy = namedtuple("PickingPolicy", ["id"])
