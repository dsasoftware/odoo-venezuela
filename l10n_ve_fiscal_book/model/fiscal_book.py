#!/usr/bin/python
# -*- encoding: utf-8 -*-
###########################################################################
#    Module Writen to OpenERP, Open Source Management Solution
#    Copyright (C) OpenERP Venezuela (<http://openerp.com.ve>).
#    All Rights Reserved
###############Credits######################################################
#    Coded by: Humberto Arocha           <hbto@vauxoo.com>
#    Planified by: Humberto Arocha & Nhomar Hernandez
#    Audited by: Humberto Arocha           <hbto@vauxoo.com>
#############################################################################
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
##############################################################################
from  openerp.osv import orm, fields
from tools.translate import _
import decimal_precision as dp

class fiscal_book(orm.Model):

    def _get_amount_total(self,cr,uid,ids,name,args,context=None):
        context = context or {}
        res = {}
        for adj in self.browse(cr,uid,ids,context):
            res[adj.id] = {
                'amount_total': 0.0,
                'amount_untaxed_n_total' : 0.0,
                'amount_with_vat_n_total': 0.0,
                'amount_untaxed_i_total' : 0.0,
                'amount_with_vat_i_total': 0.0,
                'uncredit_fiscal_total'  : 0.0,
                'amount_with_vat_total'  : 0.0,
                'amount_base_total'  : 0.0,
                'amount_percent_total'  : 0.0,
            }
            for line in adj.abl_ids:
                res[adj.id]['amount_total'] += line.amount
                res[adj.id]['amount_untaxed_n_total'] += line.amount_untaxed_n
                res[adj.id]['amount_with_vat_n_total'] += line.amount_with_vat_n
                res[adj.id]['amount_untaxed_i_total'] += line.amount_untaxed_i
                res[adj.id]['amount_with_vat_i_total'] += line.amount_with_vat_i
                res[adj.id]['uncredit_fiscal_total'] += line.uncredit_fiscal
                res[adj.id]['amount_with_vat_total'] += line.amount_with_vat
            res[adj.id]['amount_base_total'] += adj.vat_general_i+ \
                    adj.vat_general_add_i+adj.vat_reduced_i+adj.vat_general_n+\
                    adj.vat_general_add_n+adj.vat_reduced_n+adj.adjustment+ \
                    adj.no_grav+adj.sale_export
            res[adj.id]['amount_percent_total'] += adj.vat_general_icf+ \
                    adj.vat_general_add_icf+adj.vat_reduced_icf+ \
                    adj.vat_general_ncf + adj.vat_general_add_ncf + \
                    adj.vat_reduced_ncf+adj.adjustment_cf+adj.sale_export_cf
        return res

    def _get_type(self, cr, uid, context=None):
        context = context or {}
        return context.get('type', 'purchase')

    def _get_invoice_ids(self, cr, uid, ids, context=None):
        """
        It returns ids from open and paid invoices regarding to the type and 
        period of the fiscal book.
        """
        context = context or {}
        fb_brw = self.browse(cr, uid, ids, context=context)[0]
        inv_type = fb_brw.type == 'sale' \
                   and ['out_invoice', 'out_refund'] \
                   or ['in_invoice', 'in_refund']
        #~ pull invoice data
        inv_obj = self.pool.get('account.invoice')
        inv_ids = inv_obj.search(cr, uid, 
            ['|', ('state', '=', 'open'), ('state', '=', 'paid'),
             '|', ('period_id', '=', fb_brw.period_id.id),
             '|', ('type','=', inv_type[0]), ('type','=', inv_type[1])],
             context=context)
        return inv_ids

    def _set_book_line_ranks(self, cr, uid, ids, context=None):
        """
        It assigns ranks value of the book lines sorted by the date invoiced.
        """
        context = context or {}
        fb_brw = self.browse(cr, uid, ids, context=context)[0]
        fbl_obj = self.pool.get('fiscal.book.lines')
        fbl_ids = fbl_obj.search(cr, uid, [('fb_id', '=', fb_brw.id)],
                                 order='get_date_invoiced', context=context)
        fbl_brw = fbl_obj.browse(cr, uid, fbl_ids, context=context)
        my_rank = 0
        for book_line in fbl_brw:
            fbl_obj.write(cr, uid, book_line.id, {'rank': my_rank},
                          context=context)
            my_rank = my_rank + 1

    def update_book(self, cr, uid, ids, context=None):
        """
        It Generate and Fill book lines pulling the data from invoices.
        """
        context = context or {}
        fb_brw = self.browse(cr, uid, ids, context=context)[0]
        fbl_obj = self.pool.get('fiscal.book.lines')
        fblt_obj = self.pool.get('fiscal.book.lines.taxes')
        awil_obj = self.pool.get('account.wh.iva.line')
        inv_obj = self.pool.get('account.invoice')
        #~ relate inv to book
        inv_ids = self._get_invoice_ids(cr, uid, ids, context=context)
        inv_obj.write(cr, uid, inv_ids, {'fb_id' : fb_brw.id }, context=context)
        #~ update process
        for inv_id in inv_ids:
            fbl_id = fbl_obj._update_book_line(cr, uid, ids, inv_id, fb_brw.id, context=context)
            fblt_obj._update_book_line_taxes(cr, uid, ids, fbl_id, inv_id, context=context)
            awil_obj._update_wh_iva_lines(cr, uid, ids, inv_id, fb_brw.id, context=context)
        #~ remove old relations and deletion.
        for book_line in fb_brw.fbl_ids:
            #~ Delete book.lines from invoices that are now cancel or draft, or have change its period.
            if book_line.invoice_id.id not in inv_ids:
                fbl_obj.unlink(cr, uid, book_line.id, context=context)
            #~ TODO: unlink invoices to this book line.
            #~ TODO: Delete book.line.taxes associated.
            #~ TODO: unlink old wh lines to this book.
        #~ Re-assing lines rank
        self._set_book_line_ranks(cr, uid, ids, context=context)
        return True

    def get_book_line(self, cr, uid, ids, inv_id, context=None):
        """
        It returns the book line associated to the given invoice, 
        if it dosent have one return False.
        """
        context = context or {}
        fb_brw = self.browse(cr, uid, ids, context=context)[0]
        for book_line in fb_brw.fbl_ids:
            if inv_id is book_line.invoice_id.id:
                return book_line
        return False

    _description = "Venezuela's Sale & Purchase Fiscal Books"
    _name='fiscal.book'
    _inherit = ['mail.thread']
    _columns={
        'name':fields.char('Description', size=256, required=True),
        'company_id':fields.many2one('res.company','Company',
            help='Company',required=True),
        'period_id':fields.many2one('account.period','Period',
            help="Book's Fiscal Period",required=True),
        'state': fields.selection([('draft','Getting Ready'),
            ('open','Approved by Manager'),('done','Seniat Submitted')],
            string='Status', required=True),
        'type': fields.selection([('sale','Sale Book'),
            ('purchase','Purchase Book')],
            help='Select Sale for Customers and Purchase for Suppliers',
            string='Book Type', required=True),
        'base_amount':fields.float('Taxable Amount',help='Amount used as Taxing Base'),
        'tax_amount':fields.float('Taxed Amount',help='Taxed Amount on Taxing Base'),
        'fbl_ids':fields.one2many('fiscal.book.lines', 'fb_id', 'Book Lines',
            help='Lines being recorded in a Fiscal Book'),
        'fbt_ids':fields.one2many('fiscal.book.taxes', 'fb_id', 'Tax Lines',
            help='Taxes being recorded in a Fiscal Book'),
        'invoice_ids':fields.one2many('account.invoice', 'fb_id', 'Invoices',
            help='Invoices being recorded in a Fiscal Book'),
        'iwdl_ids':fields.one2many('account.wh.iva.line', 'fb_id', 'Vat Withholdings',
            help='Vat Withholdings being recorded in a Fiscal Book'),
        'abl_ids':fields.one2many('adjustment.book.line', 'fb_id', 'Adjustment Lines',
            help='Adjustment Lines being recorded in a Fiscal Book'),
        'note': fields.text('Note',required=True),
        'amount_total':fields.function(_get_amount_total,multi='all',method=True, 
            digits_compute=dp.get_precision('Account'),
            string='Amount Total Withholding VAT',readonly=True,
            help="Amount Total for adjustment book of invoice"),
        'amount_untaxed_n_total':fields.function(_get_amount_total,multi='all',
            method=True, digits_compute=dp.get_precision('Account'),
            string='Amount Untaxed National',readonly=True,
            help="Amount Total Untaxed for adjustment book of nacional operations"),
        'amount_with_vat_n_total':fields.function(_get_amount_total,multi='all',
            method=True, digits_compute=dp.get_precision('Account'),
            string='Amount Withheld National',readonly=True,
            help="Amount Total Withheld for adjustment book of national operations"),
        'amount_untaxed_i_total':fields.function(_get_amount_total,multi='all',
            method=True, digits_compute=dp.get_precision('Account'),
            string='Amount Untaxed International',readonly=True,
            help="Amount Total Untaxed for adjustment book of internacional operations"),
        'amount_with_vat_i_total':fields.function(_get_amount_total,multi='all',
            method=True, digits_compute=dp.get_precision('Account'),
            string='Amount Withheld International',readonly=True,
            help="Amount Total Withheld for adjustment book of international operations"),
        'uncredit_fiscal_total':fields.function(_get_amount_total,multi='all',
            method=True, digits_compute=dp.get_precision('Account'),
            string='Sin derecho a credito fiscal',readonly=True,
            help="Sin derecho a credito fiscal"),
        'amount_with_vat_total':fields.function(_get_amount_total,multi='all',
            method=True, digits_compute=dp.get_precision('Account'),
            string='Amount Withholding VAT Total',readonly=True,
            help="Amount Total Withholding VAT for adjustment book"),
        'no_grav': fields.float('Compras/Ventas no Gravadas y/o SDCF',  
                digits_compute=dp.get_precision('Account'),
                help="Compras/Ventas no gravadas y/o sin derecho a credito "\
                        "fiscal/ Ventas Internas no grabadas"),
        'vat_general_i': fields.float('Alicuota general',  
                digits_compute=dp.get_precision('Account'), 
                help="Importaciones gravadas por alicuota general"),
        'vat_general_add_i':fields.float('Alicuota general + Alicuota adicional',  
                digits_compute=dp.get_precision('Account'),
                help="Importaciones gravadas por alicuota general mas alicuota adicional"),
        'vat_reduced_i': fields.float('Alicuota Reducida',  
                digits_compute=dp.get_precision('Account'),
                help="Importaciones gravadas por alicuota reducida"),
        'vat_general_n': fields.float('Alicuota general',  
                digits_compute=dp.get_precision('Account'),
                help="Compras gravadas por alicuota general/Ventas internas "\
                        "gravadas por alicuota general"),
        'vat_general_add_n': fields.float('Alicuota general + Alicuota adicional',  
                digits_compute=dp.get_precision('Account'),
                help="Compras/Ventas internas gravadas por alicuota general "\
                        "mas alicuota adicional"),
        'vat_reduced_n': fields.float('Alicuota Reducida',  
                digits_compute=dp.get_precision('Account'),
                help="Compras/Ventas Internas gravadas por alicuota reducida"),
        'adjustment': fields.float('Ajustes',  
                digits_compute=dp.get_precision('Account'),
                help="Ajustes a los creditos/debitos fiscales de los periodos anteriores"),
        'vat_general_icf': fields.float('Alicuota general',  
                digits_compute=dp.get_precision('Account'), 
                help="Importaciones gravadas por alicuota general"),
        'vat_general_add_icf': fields.float('Alicuota general + Alicuota adicional',  
                digits_compute=dp.get_precision('Account'),
                help="Importaciones gravadas por alicuota general mas alicuota adicional"),
        'vat_reduced_icf': fields.float('Alicuota Reducida',  
                digits_compute=dp.get_precision('Account'),
                help="Importaciones gravadas por alicuota reducida"),
        'vat_general_ncf': fields.float('Alicuota general',  
                digits_compute=dp.get_precision('Account'),
                help="Compras gravadas por alicuota general/Ventas internas "\
                        "gravadas por alicuota general"),
        'vat_general_add_ncf': fields.float('Alicuota general + Alicuota adicional',  
                digits_compute=dp.get_precision('Account'),
                help="Compras/Ventas internas gravadas por alicuota general "\
                        "mas alicuota adicional"),
        'vat_reduced_ncf': fields.float('Alicuota Reducida',  
                digits_compute=dp.get_precision('Account'),
                help="Compras/Ventas Internas gravadas por alicuota reducida"),
        'adjustment_cf': fields.float('Ajustes',  
                digits_compute=dp.get_precision('Account'),
                help="Ajustes a los creditos/debitos fiscales de los periodos anteriores"),
        'amount_base_total':fields.function(_get_amount_total,multi='all',
                method=True, digits_compute=dp.get_precision('Account'),
                string='Total Base Imponible',readonly=True,
                help="TOTAL COMPRAS DEL PERIODO/TOTAL VENTAS PARA EFECTOS DE DETERMINACION"),
        'amount_percent_total':fields.function(_get_amount_total,multi='all',
                method=True, digits_compute=dp.get_precision('Account'),
                string='Total % Fiscal',readonly=True,help="TOTALCREDITOS FISCALES "\
                "DEL PERIODO/TOTAL DEBITOS FISCALES PARA EFECTOS DE DETERMINACION"),
        'sale_export':fields.float('Ventas de Exportacion',  
                digits_compute=dp.get_precision('Account'),
                help="Ventas de Exportacion"),
        'sale_export_cf':fields.float('Ventas de Exportacion',  
                digits_compute=dp.get_precision('Account'),
                help="Ventas de Exportacion"),
    }

    _defaults = {
        'state': 'draft',
        'type': _get_type,
        'company_id': lambda s,c,u,ctx: \
            s.pool.get('res.users').browse(c,u,u,context=ctx).company_id.id,
    }

    _sql_constraints = [
        ('period_type_company_uniq', 'unique (period_id,type,company_id)', 
            'The period and type combination must be unique!'),
    ]
class fiscal_book_lines(orm.Model):

    _description = "Venezuela's Sale & Purchase Fiscal Book Lines"
    _name='fiscal.book.lines'
    _rec_name='rank'
    _order = 'rank'
    _columns={
        'rank':fields.integer('Line Position', required=True),
        'fb_id':fields.many2one('fiscal.book','Fiscal Book',
            help='Fiscal Book where this line is related to'),
        'invoice_id':fields.many2one('account.invoice','Invoice',
            help='Invoice related to this book line.'),
        'iwdl_id':fields.many2one('account.wh.iva.line','Vat Withholding',
            help='Fiscal Book where this line is related to'),
        'get_date_imported': fields.date(string='Imported Date', help=''),
        'get_date_invoiced': fields.date(string='Invoiced Date', help=''),
        'get_t_doc': fields.char(size=128, string='Doc. Type', help=''),
        'get_partner_vat': fields.char(size=128, string='Partner vat', 
            help=''),
        'get_partner_name': fields.char(string='Partner Name', help=''),
        'get_reference': fields.char(string='Invoice number', help=''),
        'get_number': fields.char(string='Control number', help=''),
        'get_doc': fields.char(string='Trans. Type', help=''),
        'get_debit_affected': fields.char(string='Affected Debit Notes', 
            help=''),
        'get_credit_affected': fields.char(string='Affected Credit Notes', 
            help=''),
        'get_parent': fields.char(string='Affected Document', help=''),
        'fblt_ids': fields.one2many('fiscal.book.lines.taxes', 'fbl_id', 
            'Tax Lines',
            help='Tax Lines being recorded in a Fiscal Book'),
    }

    def _update_book_line(self, cr, uid, ids, inv_id, fb_id, context=None):
        """
        It updates the fiscal book lines values or create then in instead, and
        returns the book line id.
        """
        context = context or {}
        my_rank= 0

        fb_obj = self.pool.get('fiscal.book')

        inv_obj = self.pool.get('account.invoice')
        inv_brw = inv_obj.browse(cr, uid, inv_id, context=context)
        values = {
            'fb_id': fb_id,
            'get_credit_affected': inv_brw.get_credit_affected,
            'get_date_imported': inv_brw.get_date_imported and \
                inv_brw.get_date_imported or False, 
            'get_date_invoiced': inv_brw.get_date_invoiced and \
                inv_brw.get_date_invoiced or False,
            'get_debit_affected': inv_brw.get_debit_affected, 
            'get_doc' : inv_brw.get_doc, 
            'get_number': inv_brw.get_number,
            'get_parent': inv_brw.get_parent, 
            'get_partner_name': inv_brw.get_partner_name, 
            'get_partner_vat': inv_brw.get_partner_vat, 
            'get_reference': inv_brw.get_reference, 
            'get_t_doc': inv_brw.get_t_doc
        }
        book_line = fb_obj.get_book_line(cr, uid, ids, inv_brw.id, context=context)
        if book_line:
            self.write(cr, uid, [book_line.id], values, context=context)
        else:
            values['invoice_id']= inv_brw.id
            values['rank']= my_rank
            my_rank = my_rank + 1
            new_book_line_id = self.create(cr, uid, values, context=context)
            book_line = self.browse(cr, uid, new_book_line_id, context=context)
        
        return book_line.id


class fiscal_book_lines_taxes(orm.Model):

    _name='fiscal.book.lines.taxes'
    _rec_name='ait_id'
    _columns={
        'ait_id':fields.many2one('account.invoice.tax','Invoice Taxes'),
        'fbl_id':fields.many2one('fiscal.book.lines','Fiscal Book Lines',
            help='Fiscal Book Lines where this line is related to'),
    }

    def _update_book_line_taxes(self, cr, uid, ids, book_line_id, inv_id, context=None):
        """
        It updates the fiscal book lines taxes.
        """
        context = context or {}
        inv_obj = self.pool.get('account.invoice')
        inv_brw = inv_obj.browse(cr, uid, inv_id, context=context)
        if inv_brw.tax_line:
            for tax_to_update in inv_brw.tax_line:
                values = {
                    'ait_id' : tax_to_update.id,
                    'fbl_id' : book_line_id,
                }
                if not self.search(cr, uid, [ ('ait_id','=', values['ait_id']), ('fbl_id','=', values['fbl_id']) ], context=context):                
                    self.create(cr, uid, values, context=context)

class fiscal_book_taxes(orm.Model):

    _description = "Venezuela's Sale & Purchase Fiscal Book Taxes"
    _name='fiscal.book.taxes'
    _columns={
        'name':fields.char('Description', size=256, required=True),
        'fb_id':fields.many2one('fiscal.book','Fiscal Book',
            help='Fiscal Book where this line is related to'),
        'base_amount':fields.float('Taxable Amount',help='Amount used as Taxing Base'),
        'tax_amount':fields.float('Taxed Amount',help='Taxed Amount on Taxing Base'),
    }

class adjustment_book_line(orm.Model):
    
    _name='adjustment.book.line'
    _columns={
        'date_accounting': fields.date('Date Accounting', required=True,
            help="Date accounting for adjustment book"),
        'date_admin': fields.date('Date Administrative',required=True, 
            help="Date administrative for adjustment book"),
        'vat':fields.char('Vat', size=10,required=True,
            help="Vat of partner for adjustment book"),
        'partner':fields.char('Partner', size=256,required=True,
            help="Partner for adjustment book"),
        'invoice_number':fields.char('Invoice Number', size=256,required=True,
            help="Invoice number for adjustment book"),
        'control_number':fields.char('Invoice Control', size=256,required=True,
            help="Invoice control for adjustment book"),        
        'amount':fields.float('Amount Document at Withholding VAT', 
            digits_compute=dp.get_precision('Account'),required=True,
            help="Amount document for adjustment book"),
        'type_doc': fields.selection([
            ('F','Invoice'),('ND', 'Debit Note'),('NC', 'Credit Note'),],
            'Document Type', select=True, required=True, 
            help="Type of Document for adjustment book: "\
                    " -Invoice(F),-Debit Note(dn),-Credit Note(cn)"),
        'doc_affected':fields.char('Affected Document', size=256,required=True,
            help="Affected Document for adjustment book"),
        'uncredit_fiscal':fields.float('Sin derecho a Credito Fiscal', 
            digits_compute=dp.get_precision('Account'),required=True,
            help="Sin derechoa credito fiscal"),
        'amount_untaxed_n': fields.float('Amount Untaxed', 
            digits_compute=dp.get_precision('Account'),required=True,
            help="Amount untaxed for national operations"),
        'percent_with_vat_n': fields.float('% Withholding VAT', 
            digits_compute=dp.get_precision('Account'),required=True,
            help="Percent(%) VAT for national operations"),
        'amount_with_vat_n': fields.float('Amount Withholding VAT', 
            digits_compute=dp.get_precision('Account'),required=True,
            help="Percent(%) VAT for national operations"),
        'amount_untaxed_i': fields.float('Amount Untaxed', 
            digits_compute=dp.get_precision('Account'),required=True,
            help="Amount untaxed for international operations"),
        'percent_with_vat_i': fields.float('% Withholding VAT', 
            digits_compute=dp.get_precision('Account'),required=True,
            help="Percent(%) VAT for international operations"),
        'amount_with_vat_i': fields.float('Amount Withholding VAT', 
            digits_compute=dp.get_precision('Account'),required=True,
            help="Amount withholding VAT for international operations"),
        'amount_with_vat': fields.float('Amount Withholding VAT Total', 
            digits_compute=dp.get_precision('Account'),required=True,
            help="Amount withheld VAT total"),
        'voucher': fields.char('Voucher Withholding VAT', size=256,
            required=True,help="Voucher Withholding VAT"),
        'fb_id':fields.many2one('fiscal.book','Fiscal Book',
            help='Fiscal Book where this line is related to'),
    }
    _rec_rame = 'partner'
    
