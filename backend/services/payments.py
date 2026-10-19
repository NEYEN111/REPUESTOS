from typing import Protocol
from backend.db import transaction,one,now
from backend.services.orders import transition,expire

class PaymentProvider(Protocol):
    def submit(self,order_id:int,voucher:str,user_id:int|None=None): ...
    def verify(self,order_id:int,accepted:bool,user_id:int,note:str=''): ...
class SimulatedPaymentProvider:
    def submit(self,order_id,voucher,user_id=None):
        with transaction() as c:
            expire(c);o=one(c,'SELECT * FROM orders WHERE id=?',(order_id,))
            if not o or o['status']!='pendiente de pago': raise ValueError('Este pedido no admite un nuevo pago.')
            if o['payment_method'] not in ['Pago en tienda','Tarjeta simulada'] and not voucher: raise ValueError('Adjunta la captura o constancia de pago.')
            c.execute("UPDATE payments SET voucher=?,status='por verificar',note='' WHERE order_id=?",(voucher,order_id))
            transition(c,o,'pago por verificar',user_id,note='Pago enviado para verificación.')
    def verify(self,order_id,accepted,user_id,note=''):
        with transaction() as c:
            expire(c);o=one(c,'SELECT * FROM orders WHERE id=?',(order_id,))
            if not o or o['status']!='pago por verificar': raise ValueError('El pago ya fue atendido o venció.')
            if not accepted and not note.strip(): raise ValueError('Indica el motivo del rechazo.')
            c.execute('UPDATE payments SET status=?,verified_by=?,verified_at=?,note=? WHERE order_id=?',('confirmado' if accepted else 'rechazado',user_id,now(),note,order_id))
            transition(c,o,'pagado' if accepted else 'pendiente de pago',user_id,note=note or 'Pago confirmado por administración.')
provider:PaymentProvider=SimulatedPaymentProvider()
