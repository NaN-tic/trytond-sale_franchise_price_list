# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
from trytond.model import fields
from trytond.pool import PoolMeta

__all__ = ['Sale']
__metaclass__ = PoolMeta


class Sale:
    __name__ = 'sale.sale'

    @fields.depends('franchise')
    def on_change_franchise(self):
        changes = super(Sale, self).on_change_franchise()
        if self.franchise and self.franchise.price_list:
            changes['price_list'] = self.franchise.price_list.id
            changes['price_list.rec_name'] = self.franchise.price_list.rec_name
        return changes
