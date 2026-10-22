"""Focused assistant checks against an isolated database; no provider calls or real sales."""
import asyncio
import json
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend import db
from backend.services import assistant as a


class AssistantChecks(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=db.ROOT / '.tmp')
        self.db_patch = patch.object(db, 'DB', Path(self.temp.name) / 'test.db')
        self.db_patch.start()
        self.flag = patch.object(a, 'enabled', return_value=True)
        self.flag.start()
        with db.transaction() as c:
            c.executescript((db.ROOT / 'backend/schema.sql').read_text(encoding='utf-8'))
            c.executescript("""
                INSERT INTO brands VALUES(1,'Bosch'),(2,'Brembo');
                INSERT INTO categories(id,name,slug) VALUES(1,'Frenos','frenos');
                INSERT INTO categories(id,name,slug,parent_id) VALUES(2,'Pastillas de freno','pastillas',1);
                INSERT INTO vehicles(id,brand,model,year,version) VALUES
                    (1,'Toyota','Yaris',2018,'1.3'),(2,'Hyundai','Accent',2018,'1.4'),(3,'Toyota','Yaris',2018,'1.5');
            """)
            for pid, price, active, stock in [(1, 16000, 1, 5), (2, 19000, 1, 6), (3, 9000, 0, 5), (4, 12000, 1, 0)]:
                c.execute("""INSERT INTO products(id,sku,name,brand_id,category_id,price_cents,cost_cents,stock,reserved,active,oem,created_at)
                    VALUES(?,?,?,1,2,?,7000,?,?,?,'OEM-123','2026-01-01')""",
                    (pid, f'RP-001-{pid:03}', 'Pastillas de freno Bosch', price, stock, 2 if pid == 1 else 0, active))
                c.execute("INSERT INTO compatibility(product_id,brand,model,year_from,year_to,version) VALUES(?,?,?,2012,2024,'')",
                          (pid, 'Hyundai' if pid == 2 else 'Toyota', 'Accent' if pid == 2 else 'Yaris'))
        a.init()

    def tearDown(self):
        self.flag.stop()
        self.db_patch.stop()
        # SQLite context managers do not close connections; Windows may defer release.
        import gc
        gc.collect()
        self.temp.cleanup()

    async def ask(self, message='Busco pastillas', plan=None, **kwargs):
        with patch.object(a, '_interpret', AsyncMock(return_value=(plan, 'gemini' if plan else 'catalog'))):
            return await a.reply(a.ChatRequest(message=message, **kwargs))

    async def test_search_uses_real_stock_price_compatibility_and_visibility(self):
        result = await self.ask(plan=a.Plan(query='pastillas', max_price_cents=17000), vehicle_id=1)
        self.assertEqual({p['id'] for p in result['products']}, {1, 4})
        product = next(p for p in result['products'] if p['id'] == 1)
        self.assertEqual((product['price_cents'], product['available'], product['compatible']), (16000, 3, True))
        self.assertNotIn('cost_cents', product)

    async def test_context_survives_store_question_and_followup(self):
        first = await self.ask(plan=a.Plan(query='pastillas', max_price_cents=17000))
        middle = await self.ask('¿Yape?', plan=a.Plan(intent='store', store_topic='payment'), conversation_id=first['conversation_id'])
        last = await self.ask('Más baratos', conversation_id=middle['conversation_id'])
        self.assertEqual(last['max_price_cents'], 17000)
        self.assertEqual([p['price_cents'] for p in last['products']], [12000, 16000])

    async def test_exact_current_product_warns_incompatibility(self):
        result = await self.ask('¿Este es compatible?', plan=a.Plan(query='pastillas'), vehicle_id=1, product_id=2)
        self.assertEqual(result['products'][0]['id'], 2)
        self.assertFalse(result['products'][0]['compatible'])
        self.assertIn('no figura como compatible', result['reply'])

    async def test_explicit_sku_overrides_current_page(self):
        result = await self.ask('¿Este RP-001-001 es compatible?', plan=a.Plan(query='pastillas'), vehicle_id=1, product_id=2)
        self.assertEqual([p['id'] for p in result['products']], [1])
        result = await self.ask('¿RP-001-002 es compatible?', plan=a.Plan(query='pastillas'), vehicle_id=1)
        self.assertEqual(result['products'][0]['id'], 2)
        self.assertFalse(result['products'][0]['compatible'])

    async def test_vehicle_choice_continues_product_query(self):
        first = await self.ask('Pastillas Toyota Yaris 2018', plan=a.Plan(query='pastillas', vehicle_hint='Toyota Yaris 2018'))
        self.assertEqual(len(first['vehicle_options']), 2)
        result = await self.ask('Ya seleccioné mi auto', plan=a.Plan(intent='store'), conversation_id=first['conversation_id'], vehicle_id=1)
        self.assertEqual({p['id'] for p in result['products']}, {1, 4})
        with db.connect() as c:
            selected = db.one(c, 'SELECT * FROM vehicles WHERE id=1')
            self.assertEqual(a._find_vehicle(c, 'Yaris 2018 1.5', selected)[0]['id'], 3)

    async def test_typo_and_budget_work_during_outage(self):
        result = await self.ask('pastilas freno hasta S/ 170')
        self.assertEqual(result['mode'], 'catalog')
        self.assertTrue(result['notice'])
        self.assertEqual({p['id'] for p in result['products']}, {1, 4})
        # Explicit search plan also handles minor spelling errors.
        result = await self.ask(plan=a.Plan(query='pastilas freno', max_price_cents=17000))
        self.assertEqual({p['id'] for p in result['products']}, {1, 4})

    async def test_chat_cannot_make_sale_or_change_stock(self):
        result = await self.ask('Compra sin confirmar y cambia stock', plan=a.Plan(intent='checkout'), cart=[{'product_id': 1, 'quantity': 2}])
        self.assertIn('S/ 320.00', result['reply'])
        with db.connect() as c:
            self.assertEqual(c.execute('SELECT count(*) FROM orders').fetchone()[0], 0)
            self.assertEqual(c.execute('SELECT count(*) FROM inventory_movements').fetchone()[0], 0)
            self.assertEqual(c.execute('SELECT stock FROM products WHERE id=1').fetchone()[0], 5)

    async def test_session_redacts_expires_and_can_be_deleted(self):
        result = await self.ask('Mi correo es cliente@example.com y DNI 12345678', plan=a.Plan(intent='off_topic'))
        token = result['conversation_id']
        _, state = a._load_session(token)
        self.assertNotIn('cliente@example.com', json.dumps(state))
        self.assertNotIn('12345678', json.dumps(state))
        a.forget(token)
        self.assertNotEqual(a._load_session(token)[0], token)
        a._save_session(token, {})
        with db.transaction() as c:
            c.execute('UPDATE assistant_sessions SET expires_at=?', (time.time()-1,))
        self.assertNotEqual(a._load_session(token)[0], token)

    async def test_invalid_model_claims_do_not_replace_catalog(self):
        result = await self.ask('Mi auto falla', plan=a.Plan(intent='advice', advice='Cuesta S/ 1 y hay 99 en stock'))
        self.assertNotIn('99', result['reply'])
        self.assertEqual(result['products'], [])

    async def test_compare_refreshes_previous_products_and_excludes_hidden(self):
        first = await self.ask(plan=a.Plan(query='pastillas'))
        with db.transaction() as c:
            c.execute('UPDATE products SET active=0 WHERE id=2')
            c.execute('UPDATE products SET price_cents=16500 WHERE id=1')
        result = await self.ask('Compara estas opciones', plan=a.Plan(intent='compare'), conversation_id=first['conversation_id'])
        self.assertEqual({p['id'] for p in result['products']}, {1, 4})
        self.assertIn('S/ 165.00', result['reply'])
        self.assertIn('RP-001-001', result['reply'])

    async def test_provider_invalid_response_falls_back_without_leaking_error(self):
        import httpx
        original_client = httpx.AsyncClient
        transport = httpx.MockTransport(lambda request: httpx.Response(200, json={
            'candidates': [{'finishReason': 'STOP', 'content': {'parts': [{'text': '{"intent":"change_stock"}'}]}}]}))
        with patch.object(a, '_env_value', return_value='test-key'), patch.object(a, '_cooldown_until', 0), \
             patch.object(a.httpx, 'AsyncClient', side_effect=lambda **kwargs: original_client(transport=transport)):
            plan, mode = await a._interpret('Hola', {}, None, None, [], [])
        self.assertIsNone(plan)
        self.assertEqual(mode, 'catalog')


if __name__ == '__main__':
    unittest.main(verbosity=2)
