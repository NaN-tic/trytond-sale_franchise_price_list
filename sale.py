# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
from trytond.model import fields
from trytond.pool import PoolMeta

__all__ = ['Sale']

class Sale(metaclass=PoolMeta):
    __name__ = 'sale.sale'

    @fields.depends('franchise')
    def on_change_franchise(self):
        super(Sale, self).on_change_franchise()
        if self.franchise and self.franchise.price_list:
            self.price_list = self.franchise.price_list
