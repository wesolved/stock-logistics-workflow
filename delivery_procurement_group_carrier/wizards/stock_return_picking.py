# Copyright 2020 Camptocamp (https://www.camptocamp.com)
# Copyright 2020-2021 Jacques-Etienne Baudoux (BCIM) <je@bcim.be>
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

from odoo import Command, models


class StockReturnPicking(models.TransientModel):
    _inherit = "stock.return.picking.line"

    def _prepare_move_default_values(self, new_picking):
        vals = super()._prepare_move_default_values(new_picking)
        # A return gets its own reference, without carrier, so changing the
        # carrier of the return does not change the one of the delivery
        reference = new_picking.reference_ids
        if not reference:
            reference_vals = {"name": new_picking.name, "carrier_id": False}
            if self.move_id.reference_ids:
                reference = self.move_id.reference_ids[:1].copy(
                    dict(reference_vals, move_ids=[])
                )
            else:
                reference = self.env["stock.reference"].create(reference_vals)
        vals["reference_ids"] = [Command.set(reference.ids)]
        return vals
