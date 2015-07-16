# The COPYRIGHT file at the top level of this repository contains the full
# copyright notices and license terms.
from trytond.pool import Pool
from .price_list import *


def register():
    Pool.register(
        Franchise,
        FranchisePriceList,
        PriceList,
        PriceListLine,
        UpdateFranchisePriceListStart,
        UpdateFranchisePriceListEnd,
        module='sale_franchise_price_list', type_='model')
    Pool.register(
        OpenFranchisePriceList,
        UpdateFranchisePriceList,
        module='sale_franchise_price_list', type_='wizard')
